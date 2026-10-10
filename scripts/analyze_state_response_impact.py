#!/usr/bin/env python3
"""Summarize fixed-sample state/response reruns without model judging.

The report deliberately separates observable response differences from causal
attribution.  A full rollout is a feedback process: once one response differs,
later policy actions and all later responses may diverge as well.
"""

from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.state_v3_metrics import state_v3_trajectory_metrics


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text(value) -> str:
    if isinstance(value, dict):
        return str(value.get("text", ""))
    return str(value or "")


def mean(values):
    return sum(values) / len(values) if values else None


def response_metrics(trajectory):
    turns = trajectory.get("turns", [])
    responses = [text(turn.get("environment_response")) for turn in turns]
    changed_turns = []
    opportunity_active = []
    opportunity_shutdown = []
    for turn in turns:
        numeric = turn.get("numeric_state_delta") or {}
        changed = any(
            float(delta or 0) != 0
            for family in numeric.values()
            for delta in (family.values() if isinstance(family, dict) else [])
        )
        if changed:
            changed_turns.append(turn.get("turn_id"))
        opportunity = turn.get("state_transition_opportunity") or {}
        if opportunity.get("active"):
            opportunity_active.append({
                "turn_id": turn.get("turn_id"),
                "reason": opportunity.get("reason"),
                "eligible_slow_paths": opportunity.get("eligible_slow_paths", []),
                "policy_action": text(turn.get("policy_action")),
                "environment_response": text(turn.get("environment_response")),
            })
        elif opportunity:
            opportunity_shutdown.append({
                "turn_id": turn.get("turn_id"),
                "reason": opportunity.get("reason"),
            })
    count = len(turns)
    retry_count = sum(len(turn.get("response_request_retry_diagnostics") or []) for turn in turns)
    return {
        "turn_count": count,
        "mean_response_characters": mean([len(item) for item in responses]),
        "question_turn_rate": (
            sum("?" in item or "？" in item for item in responses) / count
            if count else None
        ),
        "consequential_claims_per_turn": (
            sum(len(turn.get("response_consequential_claims") or []) for turn in turns) / count
            if count else None
        ),
        "ledger_events_per_turn": (
            sum(len(turn.get("environment_response_ledger_events") or []) for turn in turns) / count
            if count else None
        ),
        "response_validation_retries_per_turn": retry_count / count if count else None,
        "state_changed_turn_count": len(changed_turns),
        "state_changed_turns": changed_turns,
        "opportunity_active_turns": opportunity_active,
        "opportunity_shutdown_turns": opportunity_shutdown,
    }


def aligned_comparison(baseline, rerun):
    baseline_turns = baseline.get("turns", [])
    rerun_turns = rerun.get("turns", [])
    count = min(len(baseline_turns), len(rerun_turns))
    response_similarity = []
    policy_similarity = []
    response_exact = 0
    policy_exact = 0
    for index in range(count):
        baseline_response = text(baseline_turns[index].get("environment_response"))
        rerun_response = text(rerun_turns[index].get("environment_response"))
        baseline_action = text(baseline_turns[index].get("policy_action"))
        rerun_action = text(rerun_turns[index].get("policy_action"))
        response_similarity.append(
            SequenceMatcher(None, baseline_response, rerun_response).ratio()
        )
        policy_similarity.append(
            SequenceMatcher(None, baseline_action, rerun_action).ratio()
        )
        response_exact += baseline_response == rerun_response
        policy_exact += baseline_action == rerun_action
    mean_response_similarity = mean(response_similarity)
    return {
        "aligned_turn_count": count,
        "mean_turn_aligned_response_character_similarity": mean_response_similarity,
        "mean_turn_aligned_policy_character_similarity": mean(policy_similarity),
        "exact_response_turn_rate": response_exact / count if count else None,
        "exact_policy_turn_rate": policy_exact / count if count else None,
        "response_surface_divergence_band": (
            "not_evaluable"
            if mean_response_similarity is None
            else "large"
            if mean_response_similarity < 0.35
            else "moderate"
            if mean_response_similarity < 0.65
            else "small"
        ),
        "causal_interpretation": "not_identified_by_full_rollout_pair",
    }


def locate_attempt_artifact(root: Path, attempt):
    names = [attempt.get("trajectory_file"), attempt.get("partial_trajectory_file")]
    for name in names:
        if not name:
            continue
        matches = list(root.glob(f"scenario_*/**/{name}"))
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(f"ambiguous artifact {name}: {matches}")
    checkpoint = attempt.get("checkpoint_file")
    if checkpoint:
        matches = list(root.glob(f"scenario_*/{checkpoint}"))
        if len(matches) == 1:
            return matches[0]
    return None


def latest_attempts(root: Path):
    progress_path = root / "progress.json"
    progress = load(progress_path)
    latest = {}
    for attempt in progress.get("attempts", []):
        latest[attempt["scenario_id"]] = attempt
    return progress, latest


def safe_state_metrics(trajectory):
    try:
        metrics = state_v3_trajectory_metrics(trajectory)
    except Exception as exc:
        return {"evaluable": False, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "evaluable": True,
        "machine_passed": metrics["machine_passed"],
        "unchanged_state_label_rate": metrics["unchanged_state_label_rate"],
        "all_time_static_variable_rate": metrics["all_time_static_variable_rate"],
        "family_changes": metrics["family_changes"],
        "fast_changes": metrics["fast_changes"],
        "slow_changes": metrics["slow_changes"],
        "compliant_slow_changes": metrics["compliant_slow_changes"],
        "false_change_count": len(metrics["false_changes"]),
        "feature_mismatch_count": len(metrics["feature_mismatches"]),
        "duplicate_selected_span_count": len(metrics["duplicate_selected_spans"]),
        "family_cap_violation_count": len(metrics["family_cap_violations"]),
        "requirements": metrics["requirements"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = load(args.manifest)
    roots = {key: Path(value) for key, value in manifest["output_roots"].items()}
    baseline_tier = {}
    for tier, value in manifest["baseline_tiers"].items():
        for scenario_id in value["scenario_ids"]:
            baseline_tier[scenario_id] = tier

    results = {}
    status_counts = {}
    for branch, root in roots.items():
        progress, latest = latest_attempts(root)
        branch_results = {}
        for scenario_id in manifest["selected"][branch]:
            attempt = latest.get(scenario_id)
            if attempt is None:
                branch_results[scenario_id] = {"status": "not_attempted"}
                status_counts["not_attempted"] = status_counts.get("not_attempted", 0) + 1
                continue
            status = attempt["status"]
            status_counts[status] = status_counts.get(status, 0) + 1
            rerun_path = locate_attempt_artifact(root, attempt)
            record = {
                "status": status,
                "attempt": attempt.get("attempt"),
                "error_type": attempt.get("error_type"),
                "error": attempt.get("error"),
                "completed_turns_before_error": attempt.get("completed_turns_before_error"),
                "baseline_tier": baseline_tier[scenario_id],
                "rerun_artifact": str(rerun_path) if rerun_path else None,
                "rerun_artifact_sha256": sha256(rerun_path) if rerun_path else None,
            }
            if rerun_path:
                baseline_path = Path(manifest["baselines"][scenario_id]["path"])
                baseline = load(baseline_path)
                rerun = load(rerun_path)
                record.update({
                    "baseline_artifact": str(baseline_path),
                    "baseline_artifact_sha256_verified": (
                        sha256(baseline_path) == manifest["baselines"][scenario_id]["sha256"]
                    ),
                    "baseline_response_metrics": response_metrics(baseline),
                    "rerun_response_metrics": response_metrics(rerun),
                    "baseline_state_metrics": safe_state_metrics(baseline),
                    "rerun_state_metrics": safe_state_metrics(rerun),
                    "aligned_descriptive_comparison": aligned_comparison(baseline, rerun),
                })
            branch_results[scenario_id] = record
        results[branch] = {
            "progress_path": str(root / "progress.json"),
            "progress_sha256": sha256(root / "progress.json"),
            "progress_status": progress.get("status"),
            "scenarios": branch_results,
        }

    all_records = [
        record
        for branch in results.values()
        for record in branch["scenarios"].values()
        if record.get("rerun_response_metrics")
    ]
    active = sum(
        len(record["rerun_response_metrics"]["opportunity_active_turns"])
        for record in all_records
    )
    main_window = sum(
        10 <= record["rerun_response_metrics"]["turn_count"] <= 20
        for record in all_records
    )
    state_pass = sum(
        record["rerun_state_metrics"].get("machine_passed") is True
        for record in all_records
    )
    report = {
        "format": "socialflux_state_response_impact_evidence_v2",
        "manifest": str(args.manifest),
        "manifest_sha256": sha256(args.manifest),
        "selection_was_pre_registered_before_outcome": manifest[
            "selection_was_pre_registered_before_outcome"
        ],
        "denominator": len(manifest["selected"]["gpt"]) + len(manifest["selected"]["claude"]),
        "status_counts": status_counts,
        "evaluable_artifact_count": len(all_records),
        "natural_10_to_20_count": main_window,
        "state_v3_machine_pass_count": state_pass,
        "active_state_opportunity_turn_count": active,
        "results": results,
        "interpretation_limits": [
            "Turn-aligned lexical similarity is descriptive and is not semantic or human judgment.",
            "Full-rollout pairs do not isolate state causally because policy actions respond to earlier environment responses.",
            "An active opportunity log proves exposure, not that it caused the generated wording.",
            "CF150_071 and CF150_072 use older context-only baselines and are excluded from causal claims.",
            "Human qualitative review remains pending.",
        ],
        "human_review": "pending",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
