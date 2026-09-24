#!/usr/bin/env python3
"""Build T1/T2/T3 from Gate-3-selected trajectories."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.instance_quality import build_instance_quality_report
from evaluation.leakage import assert_no_leaks
from evaluation.review_registry import load_review_registry
from evaluation.quality_gates import audit_environment_gate, audit_scenario_gate
from evaluation.task_source_selection import (
    rank_t1_checkpoints,
    rank_t3_checkpoints,
    select_task_sources,
)
from offline.candidate_generation import ModelCandidateGenerator
from offline.rollout_builders import (
    build_t1_checkpoints,
    build_t2_pairs,
    build_t3_candidates,
)
from pipeline.constants import ROLLOUT_CONFIG, SCENARIO_ROOT
from pipeline.runtime import (
    assert_fable_rollout_config,
    build_environment_factory,
    build_policy,
    iter_policy_specs,
)
from providers.factory import build_provider
from pipeline.scenarios import (
    load_scenario_records,
    load_scenarios,
    select_scenario_records,
    require_human_frozen,
)
from rollout.configuration import load_rollout_config, public_rollout_config
from rollout.counterfactual import branch_counterfactuals
from schemas.validate import validate_trajectory
from scripts.task_docs import write_task_review


def _load_existing_rollouts(rollout_dir):
    trajectories = []
    manifest_path = Path(rollout_dir) / "manifest.json"
    if not manifest_path.exists():
        return trajectories
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("format") != "socialflux_rollout_manifest_v2"
        or manifest.get("config", {}).get("origin") != "free_form_model_interaction"
    ):
        raise ValueError(f"rollout bundle is not a v2 free-form pool: {rollout_dir}")
    quality_audits = manifest.get("config", {}).get("quality_audits")
    if manifest.get("config", {}).get("pool_stage") == "formal_selected":
        if not isinstance(quality_audits, list):
            raise ValueError("formal_selected bundle requires quality_audits")
        by_id = {item.get("trajectory_id"): item for item in quality_audits}
        missing = [item for item in manifest.get("trajectory_ids", []) if item not in by_id]
        failed = [item for item, audit in by_id.items() if audit.get("passed") is not True]
        if missing or failed:
            raise ValueError(
                "formal_selected bundle contains unpassed or unaudited trajectories: "
                + ", ".join(missing + failed)
            )
    for trajectory_id in manifest.get("trajectory_ids", []):
        path = Path(rollout_dir) / f"{trajectory_id}.json"
        trajectory = json.loads(path.read_text(encoding="utf-8"))
        validate_trajectory(trajectory)
        trajectories.append(trajectory)
    return trajectories


def _load_rollout_quality_audits(rollout_dir):
    manifest_path = Path(rollout_dir) / "manifest.json"
    if not manifest_path.exists():
        return []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return manifest.get("config", {}).get("quality_audits") or []


def _write_offline(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            assert_no_leaks(record)
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_reusable_t3(
    build_root,
    scenario_id,
    trajectories,
    expected_source_id=None,
):
    if build_root is None:
        return None
    scenario_root = Path(build_root) / scenario_id
    instance_path = scenario_root / "offline" / "instances.jsonl"
    branch_path = scenario_root / "validation" / "local_action_interventions.json"
    if not instance_path.exists() or not branch_path.exists():
        return None
    instances = [
        json.loads(line)
        for line in instance_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    candidates = [
        item for item in instances
        if item.get("task_type") == "T3_counterfactual_choice_effect"
    ]
    if len(candidates) != 1:
        return None
    candidate = candidates[0]
    if not candidate.get("input", {}).get("history"):
        return None
    metadata = candidate.get("metadata", {})
    source_id = metadata.get("source_trajectory_id")
    checkpoint_id = metadata.get("checkpoint_turn_id")
    active_ids = {item["trajectory_id"] for item in trajectories}
    if (
        source_id not in active_ids
        or not checkpoint_id
        or (expected_source_id is not None and source_id != expected_source_id)
    ):
        return None
    branches = json.loads(branch_path.read_text(encoding="utf-8"))
    branches = [
        item for item in branches
        if item.get("source_trajectory_id") == source_id
        and item.get("checkpoint_turn_id") == checkpoint_id
    ]
    report = build_instance_quality_report(
        [candidate], trajectories=trajectories, interventions=branches
    )
    if report["structurally_passed"] != 1:
        return None
    return deepcopy(candidate), deepcopy(branches)


def run_scenario(
    scenario,
    scenario_path,
    output_dir,
    config,
    *,
    allow_unreviewed=False,
    rollout_root=None,
    reuse_t3_from=None,
    quality_audits=None,
    canonical_trajectory_id=None,
):
    require_human_frozen(scenario, allow_unreviewed=allow_unreviewed)
    scenario_id = scenario["scenario_id"]
    scenario_output = Path(output_dir) / scenario_id
    rollout_dir = (
        Path(rollout_root) / Path(scenario_path).parent.name
        if rollout_root else Path(scenario_path).parent / "rollouts"
    )
    environment_factory = build_environment_factory(scenario, config["environment"])

    policy_lookup = {
        build_policy(spec, run_index).policy_id: (spec, run_index)
        for spec, run_index in iter_policy_specs(config)
    }
    pilot_limits = config.get("pilot_limits", {})
    trajectories = _load_existing_rollouts(rollout_dir)
    if not trajectories:
        raise ValueError(f"no Gate 3 selected trajectory found for {scenario_id}")

    quality_audits = (
        quality_audits
        if quality_audits is not None
        else _load_rollout_quality_audits(rollout_dir)
    )
    task_selection = select_task_sources(
        trajectories,
        quality_audits,
        t1_source_count=config.get("task_source_selection", {}).get("t1_sources", 3),
        canonical_trajectory_id=canonical_trajectory_id,
    )
    by_trajectory_id = {item["trajectory_id"]: item for item in trajectories}
    eligible_trajectories = [
        by_trajectory_id[identifier]
        for identifier in task_selection["eligible_trajectory_ids"]
    ]
    if len(eligible_trajectories) < 2:
        raise ValueError(f"{scenario_id} has fewer than two quality-eligible trajectories")

    t1_limit = pilot_limits.get(
        "t1",
        scenario.get("sampling_plan", {}).get("t1_max", 5),
    )
    t1_source_trajectories = [
        by_trajectory_id[identifier]
        for identifier in task_selection["t1_source_ids"]
    ]
    t1_candidates = []
    for checkpoint in rank_t1_checkpoints(
        t1_source_trajectories,
        task_selection["scores"]["t1"],
    )[:t1_limit]:
        candidate = build_t1_checkpoints(
            checkpoint["trajectory"],
            scenario.get("target_state_ids", []),
        )[checkpoint["turn_index"]]
        candidate["metadata"]["selection_method"] = (
            "task_specific_quality_plus_history_depth_and_state_information"
        )
        t1_candidates.append(candidate)

    construction = ModelCandidateGenerator(
        build_provider(config["construction"]["provider"]),
        config["construction"].get("sampling", {}),
    )
    t2_limit = pilot_limits.get(
        "t2",
        scenario.get("sampling_plan", {}).get("t2_max", 3),
    )
    t2_source_trajectories = eligible_trajectories
    if canonical_trajectory_id is not None:
        runner_up_id = next(
            identifier for identifier in task_selection["t2_source_ids_ranked"]
            if identifier != canonical_trajectory_id
        )
        t2_source_trajectories = [
            by_trajectory_id[canonical_trajectory_id],
            by_trajectory_id[runner_up_id],
        ]
    t2 = build_t2_pairs(
        t2_source_trajectories,
        construction.shared_observation,
        t2_limit,
        scenario.get("target_state_ids", []),
        same_source_model=config.get("t2_pairing") == "within_source_model",
        trajectory_quality=task_selection["scores"]["t2"],
    )

    t3_limit = pilot_limits.get(
        "t3",
        scenario.get("sampling_plan", {}).get("t3_max", 4),
    )
    t3_horizon = pilot_limits.get(
        "t3_horizon",
        scenario.get("t3_delayed_horizon", 5),
    )
    reused_t3 = _load_reusable_t3(
        reuse_t3_from,
        scenario_id,
        eligible_trajectories,
        expected_source_id=task_selection["t3_source_ids_ranked"][0],
    )
    t3_selection_attempts = []
    if reused_t3 is not None:
        reused_instance, branches = reused_t3
        t3 = [reused_instance]
        t3_selection_attempts.append({
            "source_trajectory_id": reused_instance["metadata"]["source_trajectory_id"],
            "checkpoint_turn_id": reused_instance["metadata"]["checkpoint_turn_id"],
            "status": "reused_after_full_audit",
        })
    else:
        t3 = []
        branches = []
        t3_source_trajectories = (
            [by_trajectory_id[canonical_trajectory_id]]
            if canonical_trajectory_id is not None else eligible_trajectories
        )
        for checkpoint_rank in rank_t3_checkpoints(
            t3_source_trajectories,
            task_selection["scores"]["t3"],
        ):
            if len(t3) >= t3_limit:
                break
            trajectory = checkpoint_rank["trajectory"]
            turn = checkpoint_rank["turn"]
            checkpoint_index = trajectory["turns"].index(turn)
            available_future_turns = len(trajectory["turns"]) - checkpoint_index - 1
            if available_future_turns < t3_horizon:
                t3_selection_attempts.append({
                    "source_trajectory_id": trajectory["trajectory_id"],
                    "checkpoint_turn_id": turn["turn_id"],
                    "selection_score": checkpoint_rank["selection_score"],
                    "status": "rejected_insufficient_observed_future_window",
                    "required_future_turns": t3_horizon,
                    "available_future_turns": available_future_turns,
                })
                continue
            actions = construction.candidate_actions(turn["observation"], count=3)
            checkpoint = {
                **turn,
                "trajectory_id": trajectory["trajectory_id"],
                "scenario_id": scenario_id,
            }
            candidate_instance = build_t3_candidates(
                checkpoint,
                actions,
                t3_horizon,
                scenario.get("target_state_ids", []),
            )
            candidate_instance["metadata"]["source_quality_score"] = checkpoint_rank["source_score"]
            candidate_instance["metadata"]["checkpoint_depth"] = checkpoint_rank["checkpoint_depth"]
            candidate_instance["metadata"]["selection_score"] = checkpoint_rank["selection_score"]
            spec_run = policy_lookup.get(trajectory["policy_id"])
            if spec_run is None:
                provenance = trajectory.get("policy_provenance", {})
                for candidate_spec, candidate_run in iter_policy_specs(config):
                    candidate = build_policy(candidate_spec, candidate_run)
                    if (
                        candidate.provenance.get("model") == provenance.get("model")
                        and candidate.provenance.get("sampling") == provenance.get("sampling")
                    ):
                        spec_run = (candidate_spec, candidate_run)
                        break
            if spec_run is None:
                provenance = trajectory.get("policy_provenance", {})
                model_matches = [
                    candidate_spec for candidate_spec, _ in iter_policy_specs(config)
                    if candidate_spec.get("provider", {}).get("model") == provenance.get("model")
                ]
                if model_matches:
                    reconstructed = deepcopy(model_matches[0])
                    reconstructed["policy_id"] = trajectory["policy_id"]
                    reconstructed["runs"] = 1
                    reconstructed["sampling"] = deepcopy(provenance.get("sampling", {}))
                    spec_run = (reconstructed, 0)
            if spec_run is None:
                raise ValueError(
                    f"no rollout-config policy matches trajectory {trajectory['trajectory_id']}"
                )
            spec, run_index = spec_run
            try:
                new_branches = branch_counterfactuals(
                    environment_factory,
                    turn,
                    actions,
                    lambda spec=spec, run_index=run_index: build_policy(spec, run_index),
                    t3_horizon,
                )
            except RuntimeError as exc:
                t3_selection_attempts.append({
                    "source_trajectory_id": trajectory["trajectory_id"],
                    "checkpoint_turn_id": turn["turn_id"],
                    "selection_score": checkpoint_rank["selection_score"],
                    "status": "rejected_branch_generation",
                    "reason": str(exc),
                })
                continue
            for branch in new_branches:
                branch["scenario_id"] = scenario_id
                branch["source_trajectory_id"] = trajectory["trajectory_id"]
            candidate_instance["metadata"]["counterfactual_time_windows"] = [
                {
                    "elapsed_time_start": branch["elapsed_time_start"],
                    "elapsed_time_end": branch["elapsed_time_end"],
                    "elapsed_time_delta": branch["elapsed_time_delta"],
                    "crossed_event_ids": [
                        event.get("event_id")
                        for event in branch.get("crossed_event_nodes", [])
                    ],
                }
                for branch in new_branches
            ]
            plan_hashes = {
                branch.get("external_event_plan_hash") for branch in new_branches
            }
            candidate_instance["metadata"]["external_event_plan_hash"] = (
                next(iter(plan_hashes)) if len(plan_hashes) == 1 else None
            )
            candidate_instance["metadata"]["external_conditions_matched"] = (
                len(plan_hashes) == 1
            )
            branches.extend(new_branches)
            t3.append(candidate_instance)
            t3_selection_attempts.append({
                "source_trajectory_id": trajectory["trajectory_id"],
                "checkpoint_turn_id": turn["turn_id"],
                "selection_score": checkpoint_rank["selection_score"],
                "status": "selected",
            })

    if len(t3) < t3_limit:
        raise RuntimeError(
            f"{scenario_id} could not build {t3_limit} complete T3 instances; "
            f"attempts={len(t3_selection_attempts)}"
        )

    task_selection["selected"] = {
        "t1": [
            {
                "instance_id": item["instance_id"],
                "source_trajectory_id": item["metadata"]["source_trajectory_id"],
                "checkpoint_turn_id": item["input"]["history"][-1]["turn_id"],
            }
            for item in t1_candidates
        ],
        "t2": [
            {
                "instance_id": item["instance_id"],
                "source_trajectory_ids": item["metadata"]["source_trajectory_ids"],
                "history_turn_count": len(item["input"]["history_a"]),
            }
            for item in t2
        ],
        "t3": [
            {
                "instance_id": item["instance_id"],
                "source_trajectory_id": item["metadata"]["source_trajectory_id"],
                "checkpoint_turn_id": item["metadata"]["checkpoint_turn_id"],
            }
            for item in t3
        ],
    }

    _write_offline(
        scenario_output / "offline" / "instances.jsonl",
        t1_candidates + t2 + t3,
    )
    validation_dir = scenario_output / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    (validation_dir / "local_action_interventions.json").write_text(
        json.dumps(branches, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (validation_dir / "t3_selection_attempts.json").write_text(
        json.dumps(t3_selection_attempts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_task_review(
        rollout_dir / "tasks.md",
        scenario,
        t1_candidates + t2 + t3,
        trajectories,
        branches,
        task_selection=task_selection,
    )
    bundle_manifest = json.loads(
        (rollout_dir / "manifest.json").read_text(encoding="utf-8")
    )
    bundle_stage = bundle_manifest.get("config", {}).get("pool_stage", "unknown")
    summary = {
        "scenario_id": scenario_id,
        "trajectory_count": len(trajectories),
        "trajectory_origin": "free_form_model_interaction",
        "rollout_bundle": str(rollout_dir),
        "t1": len(t1_candidates),
        "t2": len(t2),
        "t3": len(t3),
        "local_intervention_branches": len(branches),
        "t3_selection_attempt_count": len(t3_selection_attempts),
        "t3_selection_audit": str(validation_dir / "t3_selection_attempts.json"),
        "t3_reused_after_active_source_audit": reused_t3 is not None,
        "task_review": str(rollout_dir / "tasks.md"),
        "ground_truth_status": "pending_human_annotation",
        "run_scope": bundle_stage,
        "pilot_limits": deepcopy(pilot_limits) if pilot_limits else None,
        "task_source_selection": task_selection,
    }
    scenario_output.mkdir(parents=True, exist_ok=True)
    (scenario_output / "pipeline_manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pipeline tasks")
    parser.add_argument("--scenarios", type=Path, default=SCENARIO_ROOT)
    parser.add_argument("--output", type=Path, default=Path("build/tasks"))
    parser.add_argument(
        "--scenario-id",
        dest="scenario_ids",
        action="append",
        help="Run only this canonical scenario ID; repeat to select multiple scenarios.",
    )
    parser.add_argument("--rollout-config", type=Path, default=ROLLOUT_CONFIG)
    parser.add_argument("--allow-unreviewed", action="store_true")
    parser.add_argument(
        "--rollout-root",
        type=Path,
        help="Optional isolated rollout root; required for formal raw pools.",
    )
    parser.add_argument(
        "--review-registry",
        type=Path,
        help="Human-signed scenario registry required for formal_raw.",
    )
    parser.add_argument(
        "--environment-evidence",
        type=Path,
        help="Gate 2 E1-E8 evidence directory required for formal_raw.",
    )
    parser.add_argument(
        "--reuse-t3-from",
        type=Path,
        help="Reuse an existing T3 only when its source remains active and its full branch audit passes.",
    )
    parser.add_argument(
        "--gate3-report",
        type=Path,
        required=True,
        help="Formal Gate 3 report containing trajectory audits and canonical selections.",
    )
    args = parser.parse_args(argv)
    config = load_rollout_config(args.rollout_config)
    assert_fable_rollout_config(config)
    if config.get("pool_stage") in {"formal_raw", "formal_selected"} and args.rollout_root is None:
        raise ValueError("formal rollout stages require --rollout-root isolation")
    if config.get("pool_stage") == "formal_raw" and args.allow_unreviewed:
        raise ValueError("formal_raw rollout can never use --allow-unreviewed")
    if config.get("pool_stage") == "formal_raw" and args.review_registry is None:
        raise ValueError("formal_raw rollout requires --review-registry")
    if config.get("pool_stage") == "formal_raw" and args.environment_evidence is None:
        raise ValueError("formal_raw rollout requires --environment-evidence")
    records = select_scenario_records(
        load_scenario_records(args.scenarios),
        args.scenario_ids,
    )
    if config.get("pool_stage") == "formal_raw":
        registry = load_review_registry(args.review_registry)
        for scenario_path, scenario in records:
            scenario_gate = audit_scenario_gate(
                scenario, scenario_path, registry
            )
            if not scenario_gate["passed"]:
                raise ValueError(
                    f"formal_raw rollout requires passed Gate 1 for {scenario['scenario_id']}"
                )
        environment_gate = audit_environment_gate(
            [scenario for _, scenario in records], args.environment_evidence
        )
        if not environment_gate["passed"]:
            raise ValueError("formal_raw rollout requires passed Gate 2 environment evidence")
    gate3 = json.loads(args.gate3_report.read_text(encoding="utf-8"))
    if gate3.get("format") != "socialflux_formal_rollout_gate_v1":
        raise ValueError("--gate3-report must be a formal Gate 3 selection report")
    if gate3.get("research_ready") is not True:
        raise ValueError("--gate3-report is not research_ready")
    audit_by_scenario = {}
    for audit in gate3.get("trajectory_audits", []):
        audit_by_scenario.setdefault(audit.get("scenario_id"), []).append(audit)
    canonical_by_scenario = {
        scenario_id: record["selected_ids"][0]
        for scenario_id, record in gate3.get("selections", {}).items()
        if len(record.get("selected_ids", [])) == 1
    }
    expected_ids = {scenario["scenario_id"] for _, scenario in records}
    missing_ids = expected_ids - set(canonical_by_scenario)
    if missing_ids:
        raise ValueError("--gate3-report must select exactly one trajectory per scenario")
    canonical_by_scenario = {
        scenario_id: trajectory_id
        for scenario_id, trajectory_id in canonical_by_scenario.items()
        if scenario_id in expected_ids
    }

    summaries = []
    for scenario_path, scenario in records:
        summary = run_scenario(
            scenario,
            scenario_path,
            args.output,
            config,
            allow_unreviewed=args.allow_unreviewed,
            rollout_root=args.rollout_root,
            reuse_t3_from=args.reuse_t3_from,
            quality_audits=audit_by_scenario.get(scenario["scenario_id"]),
            canonical_trajectory_id=canonical_by_scenario.get(scenario["scenario_id"]),
        )
        summaries.append(summary)
        print(json.dumps({
            "progress_scenario_id": summary["scenario_id"],
            "completed": len(summaries),
            "total": len(records),
            "instances": summary["t1"] + summary["t2"] + summary["t3"],
        }, ensure_ascii=False), file=sys.stderr, flush=True)
    instances = []
    for summary in summaries:
        source = args.output / summary["scenario_id"] / "offline" / "instances.jsonl"
        if not source.exists():
            continue
        instances.extend(
            json.loads(line)
            for line in source.read_text(encoding="utf-8").splitlines()
            if line
        )
    args.output.mkdir(parents=True, exist_ok=True)
    _write_offline(args.output / "instances.jsonl", instances)
    result = {
        "format": "socialflux_pipeline_manifest_v2",
        "scenario_count": len(summaries),
        "trajectory_origin": "free_form_model_interaction",
        "totals": {
            "trajectories": sum(item["trajectory_count"] for item in summaries),
            "t1": sum(item["t1"] for item in summaries),
            "t2": sum(item["t2"] for item in summaries),
            "t3": sum(item["t3"] for item in summaries),
            "instances": len(instances),
        },
        "scenarios": summaries,
        "rollout_config": public_rollout_config(config),
        "ground_truth_status": "pending_gate_4_human_review",
    }
    (args.output / "manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
