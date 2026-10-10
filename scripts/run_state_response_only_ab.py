#!/usr/bin/env python3
"""Pre-register and run a response-only State-v3 paired diagnostic.

This is a diagnostic, not a Gate result. It holds action, appraisal, memory,
history, dynamics, ledger, and longitudinal context fixed. Treatment receives
the realized State-v3 state and logged opportunity; control receives S0 and no
opportunity.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import statistics
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from environment.interaction_ledger import record_evaluated_action
from environment.observation import build_public_evaluated_role
from environment.public_situation import build_public_situation
from environment.response_generator import ModelResponseGenerator
from providers.factory import build_provider, public_provider_config
from rollout.configuration import load_rollout_config


EVIDENCE = ROOT / "data/gpt50/experiment/state_v3_validation/state_response_impact_v17_evidence.json"
MANIFEST = ROOT / "data/gpt50/experiment/state_v3_validation/state_response_only_ab_v18_manifest.json"
RESULTS = ROOT / "data/gpt50/experiment/state_v3_validation/state_response_only_ab_v18_results.json"
RESPONSE_CONFIG = ROOT / "configs/gpt50_experiment/rollout.state_v3.json"
SOURCE_CONFIGS = {
    "gpt": ROOT / "configs/gpt50_experiment/rollout.state_v3.json",
    "claude": ROOT / "configs/claude150_v1/rollout.state_v3.json",
}
TRIGGER_TURNS = (8, 12, 16)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value):
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def write_json_atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def relative(path):
    return str(Path(path).resolve().relative_to(ROOT))


def scenario_path(branch, scenario_id):
    number = scenario_id.rsplit("_", 1)[-1]
    if branch == "gpt":
        base = ROOT / "data/gpt50/experiment/scenario/scenarios_state_v3"
    else:
        base = ROOT / "data/claude150_v1/scenarios_state_v3"
    return base / f"scenario_{number}" / f"scenario_{number}.json"


def turn_number(turn):
    return int(str(turn["turn_id"]).removeprefix("t"))


def common_response_context(trajectory, scenario, turn):
    number = turn_number(turn)
    ledger = record_evaluated_action(
        turn["interaction_ledger_before"],
        turn_id=number,
        action=turn["policy_action"],
        appraisal=turn["appraisal"],
        semantic_events=turn["appraisal"].get("ledger_events"),
    )
    return {
        "scenario": {
            "background": scenario["background"],
            "public_situation": build_public_situation(scenario),
            "environment_agent": scenario["environment_agent"],
            "evaluated_agent_role": build_public_evaluated_role(
                scenario["evaluated_agent_role"]
            ),
        },
        "turn_id": number,
        "action": deepcopy(turn["policy_action"]),
        "memory": deepcopy(turn["memory_view"]),
        "appraisal": deepcopy(turn["appraisal"]),
        "dynamics": deepcopy(turn["dynamics_after"]),
        "history": deepcopy(turn["environment_snapshot_before"]["history"]),
        "interaction_ledger": ledger,
        "longitudinal_context": deepcopy(
            turn["observation"]["longitudinal_context"]
        ),
    }


def prepare_manifest():
    evidence = read_json(EVIDENCE)
    response_config = load_rollout_config(RESPONSE_CONFIG)
    environment = response_config["environment"]
    response_provider = environment["response_provider"]
    if response_provider.get("model") != "claude-fable-5":
        raise ValueError("paired diagnostic requires claude-fable-5")
    snapshots = []
    sequence = 0
    for branch in ("gpt", "claude"):
        records = evidence["results"][branch]["scenarios"]
        for scenario_id in sorted(records):
            record = records[scenario_id]
            artifact_path = ROOT / record["rerun_artifact"]
            if sha256_file(artifact_path) != record["rerun_artifact_sha256"]:
                raise ValueError(f"source artifact hash changed: {artifact_path}")
            trajectory = read_json(artifact_path)
            canonical_scenario_path = scenario_path(branch, scenario_id)
            scenario = read_json(canonical_scenario_path)
            if trajectory["scenario_id"] != scenario["scenario_id"]:
                raise ValueError(f"scenario mismatch: {scenario_id}")
            turns = {turn_number(turn): turn for turn in trajectory["turns"]}
            for number in TRIGGER_TURNS:
                if number not in turns:
                    continue
                turn = turns[number]
                opportunity = turn.get("state_transition_opportunity")
                if not isinstance(opportunity, dict):
                    raise ValueError(f"missing opportunity: {scenario_id}:t{number}")
                common = common_response_context(trajectory, scenario, turn)
                snapshots.append({
                    "snapshot_id": f"{scenario_id}:t{number}",
                    "sequence": sequence + 1,
                    "branch": branch,
                    "scenario_id": scenario_id,
                    "turn_id": f"t{number}",
                    "source_artifact": relative(artifact_path),
                    "source_artifact_sha256": sha256_file(artifact_path),
                    "scenario_path": relative(canonical_scenario_path),
                    "scenario_sha256": sha256_file(canonical_scenario_path),
                    "trajectory_scenario_fingerprint": trajectory.get(
                        "scenario_fingerprint"
                    ),
                    "opportunity_active": bool(opportunity.get("active")),
                    "opportunity_reason": opportunity.get("reason"),
                    "opportunity_selected_path": opportunity.get("selected_path"),
                    "arm_order": (
                        ["treatment", "control"] if sequence % 2 == 0
                        else ["control", "treatment"]
                    ),
                    "paired_seed": 918000 + sequence,
                    "common_context_sha256": canonical_hash(common),
                    "treatment_state_sha256": canonical_hash(turn["state_after"]),
                    "control_s0_sha256": canonical_hash(trajectory["initial_state"]),
                    "treatment_opportunity_sha256": canonical_hash(opportunity),
                })
                sequence += 1
    active = sum(item["opportunity_active"] for item in snapshots)
    manifest = {
        "format": "socialflux_state_response_only_ab_manifest_v1",
        "created_at_utc": utc_now(),
        "status": "pre_registered_before_api_calls",
        "selection_was_pre_registered_before_outcome": True,
        "objective": (
            "Causally isolate the incremental response effect of realized State-v3 "
            "state plus the logged transition opportunity without rerunning policy "
            "or appraisal."
        ),
        "classification": "diagnostic_only_not_a_gate_result",
        "fixed_inputs": [
            "scenario", "turn_id", "policy_action", "memory_view", "appraisal",
            "dynamics_after", "pre_action_history", "post_action_interaction_ledger",
            "longitudinal_context",
        ],
        "arms": {
            "treatment": "realized state_after plus logged state_transition_opportunity",
            "control": "scenario initial_state (S0) with opportunity omitted",
        },
        "sampling": {
            "temperature": 0.0,
            "top_p": 1.0,
            "paired_seed": "918000 + zero-based sequence; identical across arms",
            "structured_validation_max_attempts": 4,
            "pair_order": "alternating treatment-first/control-first",
            "pair_replacement": False,
            "failed_pairs_remain_in_denominator": True,
        },
        "response_runtime": {
            "config_path": relative(RESPONSE_CONFIG),
            "config_sha256": sha256_file(RESPONSE_CONFIG),
            "provider": public_provider_config(response_provider),
            "model": response_provider.get("model"),
            "prompt_id": environment["response_prompt_id"],
            "validation_profile": environment["response_validation_profile"],
            "routing_note": (
                "Same canonical direct claude-fable-5 response route for both "
                "source-rollout groups, avoiding provider-route confounding."
            ),
        },
        "source_rollout_configs": {
            branch: {"path": relative(path), "sha256": sha256_file(path)}
            for branch, path in SOURCE_CONFIGS.items()
        },
        "denominator": len(snapshots),
        "active_opportunity_count": active,
        "shutdown_opportunity_count": len(snapshots) - active,
        "trigger_turns": list(TRIGGER_TURNS),
        "snapshots": snapshots,
        "analysis_plan": {
            "pair_success": "both arms return a validated structured response",
            "descriptive_metrics": [
                "exact response equality", "character SequenceMatcher similarity",
                "response length and question-presence switch",
                "reply-obligation and semantic-event signature switch",
                "consequential-claim signature switch", "validation retry counts",
                "active versus shutdown opportunity strata",
            ],
            "decision_policy": [
                "If fewer than 15 of 17 pairs succeed, repair response service before any full pilot.",
                "If pairs show only rewording with stable obligations/events and no state-grounded substantive shift, do not bulk-reroll existing corpora.",
                "If multiple active pairs show coherent state-grounded changes while shutdown pairs are materially steadier, run a fixed 10 GPT-context plus 10 Claude-context full-rollout pilot before deciding corpus-wide reroll.",
            ],
            "attribution_guard": (
                "This estimates an upper-bound S0-versus-realized-state response "
                "effect, not downstream closed-loop policy effects."
            ),
            "human_review": "pending; no model judgment may be reported as human review",
        },
        "result_path": relative(RESULTS),
    }
    if len(snapshots) != 17 or active != 13:
        raise ValueError(f"denominator changed: snapshots={len(snapshots)}, active={active}")
    write_json_atomic(MANIFEST, manifest)
    return manifest


def validate_manifest(manifest):
    if manifest.get("status") != "pre_registered_before_api_calls":
        raise ValueError("manifest is not pre-registered")
    runtime = manifest["response_runtime"]
    if sha256_file(ROOT / runtime["config_path"]) != runtime["config_sha256"]:
        raise ValueError("response config hash changed")
    for branch, item in manifest["source_rollout_configs"].items():
        if sha256_file(ROOT / item["path"]) != item["sha256"]:
            raise ValueError(f"source config hash changed: {branch}")
    for snapshot in manifest["snapshots"]:
        if sha256_file(ROOT / snapshot["source_artifact"]) != snapshot["source_artifact_sha256"]:
            raise ValueError(f"artifact changed: {snapshot['snapshot_id']}")
        if sha256_file(ROOT / snapshot["scenario_path"]) != snapshot["scenario_sha256"]:
            raise ValueError(f"scenario changed: {snapshot['snapshot_id']}")


def arm_context(snapshot, arm):
    trajectory = read_json(ROOT / snapshot["source_artifact"])
    scenario = read_json(ROOT / snapshot["scenario_path"])
    number = int(snapshot["turn_id"].removeprefix("t"))
    turn = next(item for item in trajectory["turns"] if turn_number(item) == number)
    context = common_response_context(trajectory, scenario, turn)
    if canonical_hash(context) != snapshot["common_context_sha256"]:
        raise ValueError(f"common context changed: {snapshot['snapshot_id']}")
    if arm == "treatment":
        context["state"] = deepcopy(turn["state_after"])
        context["state_transition_opportunity"] = deepcopy(
            turn["state_transition_opportunity"]
        )
    elif arm == "control":
        context["state"] = deepcopy(trajectory["initial_state"])
    else:
        raise ValueError(f"unknown arm: {arm}")
    return context


def run_arm(snapshot, arm, environment):
    provider = build_provider(environment["response_provider"])
    generator = ModelResponseGenerator(
        provider,
        {"temperature": 0.0, "top_p": 1.0, "seed": snapshot["paired_seed"]},
        prompt_id=environment["response_prompt_id"],
        validation_profile=environment["response_validation_profile"],
        horizon_mode=environment["horizon_mode"],
        minimum_natural_turns=environment["minimum_natural_turns"],
    )
    started = utc_now()
    try:
        output = generator.generate(arm_context(snapshot, arm))
        return {
            "arm": arm, "status": "success", "started_at_utc": started,
            "finished_at_utc": utc_now(), "output": output,
            "provider_metrics": deepcopy(getattr(provider, "metrics", {})),
        }
    except Exception as exc:
        return {
            "arm": arm, "status": "error", "started_at_utc": started,
            "finished_at_utc": utc_now(), "error_type": type(exc).__name__,
            "error": str(exc),
            "provider_metrics": deepcopy(getattr(provider, "metrics", {})),
        }


def event_signature(output):
    return {
        "reply_obligation": output.get("reply_obligation"),
        "events": [
            {key: item.get(key) for key in (
                "event_type", "action_owner", "status", "assertion_mode"
            )}
            for item in output.get("ledger_events", [])
        ],
        "claims": [
            {
                "impact_domains": sorted(item.get("impact_domains", [])),
                "grounding": item.get("grounding"),
            }
            for item in output.get("consequential_claims", [])
        ],
    }


def compare_pair(arms):
    if any(arms.get(arm, {}).get("status") != "success" for arm in ("treatment", "control")):
        return {"paired_success": False}
    treatment = arms["treatment"]["output"]
    control = arms["control"]["output"]
    treatment_text = treatment["response_text"]
    control_text = control["response_text"]
    return {
        "paired_success": True,
        "exact_response_equal": treatment_text == control_text,
        "character_similarity": SequenceMatcher(None, treatment_text, control_text).ratio(),
        "treatment_characters": len(treatment_text),
        "control_characters": len(control_text),
        "question_presence_switched": (
            any(mark in treatment_text for mark in "?？")
            != any(mark in control_text for mark in "?？")
        ),
        "structured_signature_changed": event_signature(treatment) != event_signature(control),
        "treatment_signature": event_signature(treatment),
        "control_signature": event_signature(control),
        "treatment_retry_count": len(treatment.get("request_retry_diagnostics", [])),
        "control_retry_count": len(control.get("request_retry_diagnostics", [])),
    }


def run_pair(snapshot, environment):
    arms = {}
    for arm in snapshot["arm_order"]:
        arms[arm] = run_arm(snapshot, arm, environment)
    return {
        "snapshot_id": snapshot["snapshot_id"], "sequence": snapshot["sequence"],
        "branch": snapshot["branch"], "scenario_id": snapshot["scenario_id"],
        "turn_id": snapshot["turn_id"],
        "opportunity_active": snapshot["opportunity_active"],
        "opportunity_reason": snapshot["opportunity_reason"],
        "opportunity_selected_path": snapshot["opportunity_selected_path"],
        "arm_order": snapshot["arm_order"], "paired_seed": snapshot["paired_seed"],
        "arms": arms, "comparison": compare_pair(arms),
    }


def aggregate(pairs):
    successful = [pair for pair in pairs if pair["comparison"]["paired_success"]]

    def stratum(active):
        members = [pair for pair in successful if pair["opportunity_active"] is active]
        comparisons = [pair["comparison"] for pair in members]
        return {
            "denominator": sum(pair["opportunity_active"] is active for pair in pairs),
            "paired_success_count": len(members),
            "exact_response_equal_count": sum(item["exact_response_equal"] for item in comparisons),
            "mean_character_similarity": (
                statistics.mean(item["character_similarity"] for item in comparisons)
                if comparisons else None
            ),
            "structured_signature_changed_count": sum(
                item["structured_signature_changed"] for item in comparisons
            ),
            "question_presence_switched_count": sum(
                item["question_presence_switched"] for item in comparisons
            ),
        }

    return {
        "denominator": len(pairs), "paired_success_count": len(successful),
        "pair_failure_count": len(pairs) - len(successful),
        "active": stratum(True), "shutdown": stratum(False),
        "all_successful": {
            "exact_response_equal_count": sum(
                pair["comparison"]["exact_response_equal"] for pair in successful
            ),
            "mean_character_similarity": (
                statistics.mean(pair["comparison"]["character_similarity"] for pair in successful)
                if successful else None
            ),
            "structured_signature_changed_count": sum(
                pair["comparison"]["structured_signature_changed"] for pair in successful
            ),
            "question_presence_switched_count": sum(
                pair["comparison"]["question_presence_switched"] for pair in successful
            ),
            "treatment_retry_count": sum(
                pair["comparison"]["treatment_retry_count"] for pair in successful
            ),
            "control_retry_count": sum(
                pair["comparison"]["control_retry_count"] for pair in successful
            ),
        },
    }


def execute(workers):
    manifest = read_json(MANIFEST)
    validate_manifest(manifest)
    environment = load_rollout_config(
        ROOT / manifest["response_runtime"]["config_path"]
    )["environment"]
    progress = {
        "format": "socialflux_state_response_only_ab_results_v1",
        "created_at_utc": utc_now(), "updated_at_utc": utc_now(),
        "status": "running", "manifest": relative(MANIFEST),
        "manifest_sha256": sha256_file(MANIFEST),
        "selection_was_pre_registered_before_outcome": True,
        "human_review": "pending", "pairs": [],
    }
    write_json_atomic(RESULTS, progress)
    completed = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(run_pair, snapshot, environment): snapshot
            for snapshot in manifest["snapshots"]
        }
        for future in as_completed(futures):
            snapshot = futures[future]
            try:
                pair = future.result()
            except Exception as exc:
                pair = {
                    "snapshot_id": snapshot["snapshot_id"],
                    "sequence": snapshot["sequence"], "branch": snapshot["branch"],
                    "scenario_id": snapshot["scenario_id"], "turn_id": snapshot["turn_id"],
                    "opportunity_active": snapshot["opportunity_active"],
                    "opportunity_reason": snapshot["opportunity_reason"],
                    "opportunity_selected_path": snapshot["opportunity_selected_path"],
                    "pair_error_type": type(exc).__name__, "pair_error": str(exc),
                    "arms": {}, "comparison": {"paired_success": False},
                }
            completed[pair["snapshot_id"]] = pair
            progress["pairs"] = sorted(completed.values(), key=lambda item: item["sequence"])
            progress["updated_at_utc"] = utc_now()
            progress["completed_pair_count"] = len(completed)
            write_json_atomic(RESULTS, progress)
            print(
                f"[{len(completed)}/{manifest['denominator']}] {pair['snapshot_id']} "
                f"paired_success={pair['comparison']['paired_success']}", flush=True,
            )
    pairs = sorted(completed.values(), key=lambda item: item["sequence"])
    progress.update({
        "updated_at_utc": utc_now(), "status": "complete",
        "completed_pair_count": len(pairs), "pairs": pairs,
        "aggregate": aggregate(pairs),
    })
    write_json_atomic(RESULTS, progress)
    return progress


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    if args.command == "prepare":
        manifest = prepare_manifest()
        print(json.dumps({
            "manifest": relative(MANIFEST), "sha256": sha256_file(MANIFEST),
            "denominator": manifest["denominator"],
            "active": manifest["active_opportunity_count"],
            "shutdown": manifest["shutdown_opportunity_count"],
        }, ensure_ascii=False, indent=2))
    else:
        if not 1 <= args.workers <= 4:
            raise ValueError("workers must be between 1 and 4")
        result = execute(args.workers)
        print(json.dumps(result["aggregate"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
