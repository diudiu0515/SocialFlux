#!/usr/bin/env python3
"""Replace only trajectories that fail the current clean-pool quality gate."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from environment.factory import ModelEnvironmentFactory
from evaluation.instance_quality import audit_trajectory
from evaluation.rollout_gate import audit_rollout, public_judge_packet
from prompts.loader import render_prompt
from providers.factory import build_provider
from providers.structured import complete_json
from rollout.logger import TrajectoryLogger
from rollout.manifest import write_manifest
from rollout.runner import RolloutRunner
from scripts.run_pipeline import (
    _policy_from_spec,
    _policy_specs,
    _write_dialogues,
    load_rollout_config,
    load_scenario_records,
    select_scenario_records,
)
from scripts.run_rollout_quality_judge import (
    deterministic_judge_sampling,
    validate as validate_quality_judgment,
    validate_model_family,
)


def _load_bundle(scenario_path):
    rollout_dir = Path(scenario_path).parent / "rollouts"
    manifest_path = rollout_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    trajectories = [
        json.loads((rollout_dir / f"{trajectory_id}.json").read_text(encoding="utf-8"))
        for trajectory_id in manifest["trajectory_ids"]
    ]
    return rollout_dir, manifest, trajectories


def _policy_lookup(config):
    result = {}
    for spec, run_index in _policy_specs(config):
        policy = _policy_from_spec(spec, run_index)
        result[policy.policy_id] = (spec, run_index)
    return result


def _replacement_policy_lookup(original_config, replacement_config):
    original = []
    for spec, run_index in _policy_specs(original_config):
        policy_id = spec["policy_id"]
        if spec.get("runs", 1) > 1:
            policy_id = f"{policy_id}__run_{run_index + 1}"
        original.append(policy_id)
    replacement = [
        (spec, run_index)
        for spec, run_index in _policy_specs(replacement_config)
    ]
    if len(original) != len(replacement):
        raise ValueError(
            "replacement rollout config must expose the same number of policy run slots"
        )
    result = dict(zip(original, replacement))
    for spec, run_index in replacement:
        policy_id = spec["policy_id"]
        if spec.get("runs", 1) > 1:
            policy_id = f"{policy_id}__run_{run_index + 1}"
        result[policy_id] = (spec, run_index)
    return result


def _seed_offset(value, offset):
    updated = deepcopy(value)
    if isinstance(updated.get("seed"), int):
        updated["seed"] += offset
    return updated


def _build_quality_judge(path, model_family):
    if path is None:
        return None
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_model_family(config["provider"].get("model"), model_family)
    provider = build_provider(config["provider"])
    sampling = config.get("sampling", {})

    def judge(trajectory, scenario):
        trajectory_id = trajectory["trajectory_id"]
        prompt = render_prompt(
            "rollout_quality_judge_v2",
            public_judge_packet(trajectory, scenario),
        )
        reset = getattr(provider, "reset", None)
        if reset:
            reset()
        return complete_json(
            provider,
            [{"role": "user", "content": prompt}],
            deterministic_judge_sampling(sampling, trajectory_id),
            lambda value: validate_quality_judgment(
                value, trajectory_id, {item["turn_id"] for item in trajectory["turns"]}
            ),
            context=f"repair candidate quality judgment {trajectory_id}",
            max_attempts=5,
        )

    return judge


def _merge_candidate_judgments(primary, secondary):
    if secondary is None:
        return primary
    evidence = {
        key: list(dict.fromkeys(
            list(primary.get("evidence", {}).get(key, []))
            + list(secondary.get("evidence", {}).get(key, []))
        ))[:3]
        for key in primary["scores"]
    }
    return {
        "trajectory_id": primary["trajectory_id"],
        "scores": {
            key: round((float(primary["scores"][key]) + float(secondary["scores"][key])) / 2, 2)
            for key in primary["scores"]
        },
        "hard_reject_reasons": sorted(
            set(primary.get("hard_reject_reasons", []))
            | set(secondary.get("hard_reject_reasons", []))
        ),
        **({"evidence": evidence} if all(evidence.values()) else {}),
        "rationale": (
            "Primary candidate prefilter: " + primary["rationale"]
            + " Secondary candidate prefilter: " + secondary["rationale"]
        ),
    }


def _generate_clean(
    scenario,
    config,
    spec,
    run_index,
    max_attempts,
    quality_judge=None,
    secondary_quality_judge=None,
    attempt_recorder=None,
):
    last_audit = None
    last_semantic_audit = None
    last_error = None
    for attempt in range(max_attempts):
        attempt_record = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "scenario_id": scenario["scenario_id"],
            "policy_id": spec["policy_id"],
            "attempt": attempt + 1,
        }
        offset = (attempt + 1) * 100_003
        environment_factory = ModelEnvironmentFactory(
            scenario,
            config["environment"]["provider"],
            _seed_offset(config["environment"].get("sampling", {}), offset),
        )
        varied_spec = deepcopy(spec)
        varied_spec["sampling"] = _seed_offset(spec.get("sampling", {}), offset)
        policy = _policy_from_spec(varied_spec, run_index)
        try:
            trajectory = RolloutRunner(environment_factory).run(
                policy,
                max_turns=config.get("pilot_limits", {}).get("rollout_turns"),
            )
        except (ValueError, OSError, TimeoutError) as exc:
            last_error = str(exc)
            attempt_record.update({"status": "generation_error", "error": last_error})
            if attempt_recorder is not None:
                attempt_recorder(attempt_record)
            continue
        attempt_record["trajectory_id"] = trajectory["trajectory_id"]
        attempt_record["observable_turns"] = [
            {
                "turn_id": turn.get("turn_id"),
                "action": turn.get("policy_action", {}).get("text", ""),
                "response": turn.get("environment_response", ""),
                "expression": turn.get("observable_expression"),
            }
            for turn in trajectory.get("turns", [])
        ]
        last_audit = audit_trajectory(trajectory)
        attempt_record["structural_audit"] = last_audit
        if not last_audit["passed"]:
            attempt_record["status"] = "structural_rejected"
            if attempt_recorder is not None:
                attempt_recorder(attempt_record)
            continue
        judgment = None
        secondary_judgment = None
        merged_judgment = None
        if quality_judge is not None:
            try:
                judgment = quality_judge(trajectory, scenario)
                if secondary_quality_judge is not None:
                    secondary_judgment = secondary_quality_judge(trajectory, scenario)
                merged_judgment = _merge_candidate_judgments(
                    judgment,
                    secondary_judgment,
                )
            except (ValueError, OSError, TimeoutError) as exc:
                last_error = str(exc)
                attempt_record.update({"status": "judge_error", "error": last_error})
                if attempt_recorder is not None:
                    attempt_recorder(attempt_record)
                continue
            last_semantic_audit = audit_rollout(
                trajectory,
                judgment=merged_judgment,
            )
            attempt_record["candidate_judgments"] = {
                "primary": judgment,
                "secondary": secondary_judgment,
                "merged": merged_judgment,
            }
            attempt_record["semantic_audit"] = last_semantic_audit
            if last_semantic_audit["status"] == "rejected":
                attempt_record["status"] = "semantic_rejected"
                if attempt_recorder is not None:
                    attempt_recorder(attempt_record)
                continue
        attempt_record["status"] = "accepted"
        if attempt_recorder is not None:
            attempt_recorder(attempt_record)
        return trajectory, attempt + 1, {
            "primary": judgment,
            "secondary": secondary_judgment,
            "merged": merged_judgment,
        }
    raise RuntimeError(
        f"could not generate a clean trajectory for {scenario['scenario_id']} / "
        f"{spec['policy_id']}: structural_audit={last_audit}; "
        f"semantic_audit={last_semantic_audit}; error={last_error}"
    )


def repair_scenario(
    scenario_path,
    scenario,
    config,
    max_attempts,
    forced_rejected_ids=None,
    quality_judge=None,
    secondary_quality_judge=None,
    attempt_recorder=None,
    policy_lookup=None,
    forced_selection_reason="four_gate_rejected",
):
    rollout_dir, manifest, trajectories = _load_bundle(scenario_path)
    lookup = policy_lookup or _policy_lookup(config)
    forced_rejected_ids = set(forced_rejected_ids or ())
    replacements = []
    repaired = []
    pending_moves = []
    for trajectory in trajectories:
        audit = audit_trajectory(trajectory)
        forced_reject = trajectory["trajectory_id"] in forced_rejected_ids
        if audit["passed"] and not forced_reject:
            repaired.append(trajectory)
            continue
        policy_id = trajectory["policy_id"]
        if policy_id not in lookup:
            raise ValueError(f"no config policy matches {policy_id}")
        replacement, attempts, candidate_judgments = _generate_clean(
            scenario,
            config,
            *lookup[policy_id],
            max_attempts,
            quality_judge,
            secondary_quality_judge,
            attempt_recorder,
        )
        TrajectoryLogger(rollout_dir).write(replacement)
        old_path = rollout_dir / f"{trajectory['trajectory_id']}.json"
        pending_moves.append(old_path)
        replacements.append({
            "old_trajectory_id": trajectory["trajectory_id"],
            "new_trajectory_id": replacement["trajectory_id"],
            "policy_id": policy_id,
            "replacement_policy_id": replacement["policy_id"],
            "attempts": attempts,
            "selection_reason": forced_selection_reason if forced_reject else "machine_structure_rejected",
            "old_audit": audit,
            "candidate_judgments": candidate_judgments,
        })
        repaired.append(replacement)
    if replacements:
        _write_dialogues(rollout_dir / "dialogues.md", scenario, repaired)
        config_record = deepcopy(manifest.get("config", {}))
        config_record["clean_pool_repair"] = {
            "quality_gate": "four_gate_or_distinct_text_v2",
            "replacement_count": len(replacements),
        }
        # Publish the new manifest before archiving old files. During a long
        # multi-replacement scenario this keeps every manifest reference valid.
        write_manifest(rollout_dir / "manifest.json", repaired, config_record)
        rejected_dir = rollout_dir / "rejected"
        rejected_dir.mkdir(exist_ok=True)
        for old_path in pending_moves:
            shutil.move(str(old_path), rejected_dir / old_path.name)
        rejected_manifest = rejected_dir / "manifest.json"
        prior = (
            json.loads(rejected_manifest.read_text(encoding="utf-8"))
            if rejected_manifest.exists()
            else []
        )
        rejected_manifest.write_text(
            json.dumps(prior + replacements, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return {
        "scenario_id": scenario["scenario_id"],
        "replacement_count": len(replacements),
        "handled_rejected_ids": sorted(forced_rejected_ids & {item["trajectory_id"] for item in trajectories}),
        "replacements": replacements,
    }


def _gate_rejected_ids(path):
    if path is None:
        return set()
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    gate = payload.get("gates", {}).get("gate_3_rollout_quality")
    if not isinstance(gate, dict) or not isinstance(gate.get("audits"), list):
        raise ValueError("gate report lacks Gate 3 trajectory audits")
    return {
        item["trajectory_id"]
        for item in gate["audits"]
        if item.get("status") == "rejected" and item.get("trajectory_id")
    }


def _archived_gate_ids(records):
    archived = set()
    for scenario_path, _ in records:
        path = Path(scenario_path).parent / "rollouts" / "rejected" / "manifest.json"
        if not path.exists():
            continue
        entries = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            raise ValueError(f"rejected manifest must be a list: {path}")
        archived.update(
            item["old_trajectory_id"]
            for item in entries
            if item.get("selection_reason") == "four_gate_rejected"
            and item.get("old_trajectory_id")
        )
    return archived


def _bundle_gate_ids(records):
    """Return active and archived trajectory IDs inside selected bundles."""
    result = set()
    for scenario_path, _ in records:
        rollout_dir = Path(scenario_path).parent / "rollouts"
        manifest = json.loads(
            (rollout_dir / "manifest.json").read_text(encoding="utf-8")
        )
        result.update(manifest.get("trajectory_ids", []))
        rejected_manifest = rollout_dir / "rejected" / "manifest.json"
        if rejected_manifest.exists():
            entries = json.loads(rejected_manifest.read_text(encoding="utf-8"))
            result.update(
                item.get("old_trajectory_id")
                for item in entries
                if item.get("old_trajectory_id")
            )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", type=Path, default=Path("configs/scenarios"))
    parser.add_argument("--rollout-config", type=Path, required=True)
    parser.add_argument("--replacement-rollout-config", type=Path)
    parser.add_argument("--gate-report", type=Path)
    parser.add_argument("--judge-provider-config", type=Path)
    parser.add_argument("--judge-model-family")
    parser.add_argument("--secondary-judge-provider-config", type=Path)
    parser.add_argument("--secondary-judge-model-family")
    parser.add_argument("--attempt-log", type=Path)
    parser.add_argument("--scenario-id", dest="scenario_ids", action="append")
    parser.add_argument("--replace-trajectory-id", dest="replacement_ids", action="append")
    parser.add_argument(
        "--forced-selection-reason",
        default="four_gate_rejected",
        choices=("four_gate_rejected", "t2_pairing_rebalance"),
    )
    parser.add_argument("--max-attempts", type=int, default=4)
    args = parser.parse_args()
    if args.max_attempts < 1:
        raise ValueError("max-attempts must be positive")
    if bool(args.judge_provider_config) != bool(args.judge_model_family):
        raise ValueError(
            "judge-provider-config and judge-model-family must be supplied together"
        )
    if bool(args.secondary_judge_provider_config) != bool(args.secondary_judge_model_family):
        raise ValueError(
            "secondary-judge-provider-config and secondary-judge-model-family "
            "must be supplied together"
        )
    if args.secondary_judge_provider_config and not args.judge_provider_config:
        raise ValueError("secondary candidate judge requires a primary candidate judge")
    original_config = load_rollout_config(args.rollout_config)
    config = (
        load_rollout_config(args.replacement_rollout_config)
        if args.replacement_rollout_config
        else original_config
    )
    policy_lookup = (
        _replacement_policy_lookup(original_config, config)
        if args.replacement_rollout_config
        else None
    )
    quality_judge = _build_quality_judge(
        args.judge_provider_config,
        args.judge_model_family,
    )
    secondary_quality_judge = _build_quality_judge(
        args.secondary_judge_provider_config,
        args.secondary_judge_model_family,
    )
    attempt_recorder = None
    if args.attempt_log is not None:
        args.attempt_log.parent.mkdir(parents=True, exist_ok=True)

        def attempt_recorder(record):
            with args.attempt_log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    records = select_scenario_records(
        load_scenario_records(args.scenarios),
        args.scenario_ids,
    )
    forced_rejected_ids = (
        _gate_rejected_ids(args.gate_report) & _bundle_gate_ids(records)
    )
    requested_replacements = set(args.replacement_ids or ())
    unknown_replacements = requested_replacements - _bundle_gate_ids(records)
    if unknown_replacements:
        raise ValueError(
            "requested replacement IDs were not found in selected bundles: "
            + ", ".join(sorted(unknown_replacements))
        )
    forced_rejected_ids.update(requested_replacements)
    archived_before_run = _archived_gate_ids(records) & forced_rejected_ids
    results = []
    for path, scenario in records:
        result = repair_scenario(
            path,
            scenario,
            config,
            args.max_attempts,
            forced_rejected_ids,
            quality_judge,
            secondary_quality_judge,
            attempt_recorder,
            policy_lookup,
            args.forced_selection_reason,
        )
        results.append(result)
        print(json.dumps({
            "progress_scenario_id": result["scenario_id"],
            "replacement_count": result["replacement_count"],
        }, ensure_ascii=False), file=sys.stderr, flush=True)
    handled = {
        trajectory_id
        for item in results
        for trajectory_id in item["handled_rejected_ids"]
    }
    missing = sorted(forced_rejected_ids - handled - archived_before_run)
    if missing:
        raise ValueError("gate report rejected IDs were not found: " + ", ".join(missing))
    print(json.dumps({
        "scenario_count": len(results),
        "gate_rejected_input_count": len(forced_rejected_ids),
        "resumed_rejected_count": len(archived_before_run),
        "replacement_count": sum(item["replacement_count"] for item in results),
        "scenarios": results,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
