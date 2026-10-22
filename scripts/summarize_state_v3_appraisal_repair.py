#!/usr/bin/env python3
"""Summarize the pre-registered State v3 appraisal repair without filtering failures."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def find_artifact(output_root, attempt):
    scenario_dir = Path(output_root) / f"scenario_{attempt['scenario_id'][-3:]}"
    filename = (
        attempt.get("trajectory_file")
        or attempt.get("partial_trajectory_file")
    )
    if filename:
        matches = list(scenario_dir.rglob(filename))
        if len(matches) == 1:
            return matches[0]
    checkpoint = attempt.get("checkpoint_file")
    if checkpoint:
        path = scenario_dir / checkpoint
        if path.is_file():
            return path
    return None


def transition_audit(trajectory):
    relationship_candidates = 0
    dual_relationship_turns = []
    slow_candidates = 0
    slow_selected = 0
    slow_suppressions = Counter()
    quote_repairs = 0
    for turn in trajectory.get("turns", []):
        relationship = [
            item
            for item in (turn.get("appraisal") or {}).get("state_impacts", [])
            if str(item.get("variable", "")).startswith("relationship.")
        ]
        relationship_candidates += len(relationship)
        if len(relationship) > 1:
            dual_relationship_turns.append(turn.get("turn_id"))
        for item in (turn.get("calibration") or {}).get("state_impacts", []):
            if item.get("timescale") != "cross_turn_slow":
                continue
            slow_candidates += 1
            if item.get("selected") is True:
                slow_selected += 1
            elif item.get("suppressed_by"):
                slow_suppressions[item["suppressed_by"]] += 1
        quote_repairs += sum(
            item.get("operation") == "escape_unescaped_interior_quotes"
            for item in turn.get("appraisal_request_retry_diagnostics", [])
            if isinstance(item, dict)
        )
    return {
        "persisted_turn_count": len(trajectory.get("turns", [])),
        "relationship_candidate_count": relationship_candidates,
        "dual_relationship_candidate_turns": dual_relationship_turns,
        "slow_candidate_count": slow_candidates,
        "slow_selected_count": slow_selected,
        "slow_suppressions": dict(sorted(slow_suppressions.items())),
        "recorded_quote_repairs": quote_repairs,
    }


def attempt_summary(output_root, attempt):
    metrics = (attempt.get("precheck") or {}).get("state_v3_metrics")
    artifact = find_artifact(output_root, attempt)
    return {
        "attempt": attempt.get("attempt"),
        "status": attempt.get("status"),
        "technical_retry": bool(attempt.get("technical_retry")),
        "quality_retry": bool(attempt.get("quality_retry")),
        "error_type": attempt.get("error_type"),
        "error": attempt.get("error"),
        "completed_turns_before_error": attempt.get(
            "completed_turns_before_error"
        ),
        "artifact": str(artifact.relative_to(ROOT)) if artifact else None,
        "artifact_sha256": sha256_file(artifact) if artifact else None,
        "state_v3_metrics": metrics,
        "transition_audit": transition_audit(load(artifact)) if artifact else None,
    }


def latest_attempts(progress):
    result = {}
    for attempt in progress.get("attempts", []):
        result[attempt["scenario_id"]] = attempt
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest", type=Path,
        default=ROOT / (
            "data/gpt50/experiment/state_v3_validation/"
            "appraisal_v14_repair_manifest.json"
        ),
    )
    parser.add_argument(
        "--baseline-root", type=Path,
        default=ROOT / (
            "data/gpt50/experiment/state_v3_validation/paired_rollouts"
        ),
    )
    parser.add_argument(
        "--repair-root", type=Path,
        default=ROOT / (
            "data/gpt50/experiment/state_v3_validation/"
            "paired_rollouts_appraisal_v14"
        ),
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / (
            "data/gpt50/experiment/state_v3_validation/"
            "appraisal_v14_repair_evidence.json"
        ),
    )
    args = parser.parse_args(argv)

    manifest = load(args.manifest)
    selected = manifest["selected"]
    baseline_progress = load(args.baseline_root / "progress.json")
    repair_progress = load(args.repair_root / "progress.json")
    baseline_latest = latest_attempts(baseline_progress)
    repair_by_scenario = {
        scenario_id: [
            attempt_summary(args.repair_root, attempt)
            for attempt in repair_progress.get("attempts", [])
            if attempt["scenario_id"] == scenario_id
        ]
        for scenario_id in selected
    }
    repair_latest = {
        scenario_id: attempts[-1] if attempts else None
        for scenario_id, attempts in repair_by_scenario.items()
    }

    rows = {}
    for scenario_id in selected:
        baseline = attempt_summary(
            args.baseline_root, baseline_latest[scenario_id]
        )
        rows[scenario_id] = {
            "baseline": baseline,
            "repair_attempts": repair_by_scenario[scenario_id],
        }

    latest_statuses = Counter(
        value["status"] for value in repair_latest.values() if value
    )
    evaluable = [
        value for value in repair_latest.values()
        if value
        and value.get("state_v3_metrics")
        and 10 <= value["state_v3_metrics"].get("turn_count", 0) <= 20
    ]
    evidence_format = (
        "socialflux_state_v3_semantics_repair_evidence_v1"
        if "semantics_repair" in str(manifest.get("format", ""))
        else "socialflux_state_v3_appraisal_repair_evidence_v1"
    )
    payload = {
        "format": evidence_format,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "selection_manifest": str(args.manifest.relative_to(ROOT)),
        "selection_manifest_sha256": sha256_file(args.manifest),
        "baseline_progress_sha256": sha256_file(
            args.baseline_root / "progress.json"
        ),
        "repair_progress_sha256": sha256_file(
            args.repair_root / "progress.json"
        ),
        "selected_count": len(selected),
        "latest_status_counts": dict(sorted(latest_statuses.items())),
        "evaluable_natural_10_to_20_count": len(evaluable),
        "machine_passed_count": sum(
            item["state_v3_metrics"].get("machine_passed") is True
            for item in evaluable
        ),
        "compliant_slow_change_count": sum(
            item["state_v3_metrics"].get("compliant_slow_changes", 0)
            for item in evaluable
        ),
        "human_review": "pending",
        "failures_retained": True,
        "scenarios": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(json.dumps({
        "output": str(args.output),
        "latest_status_counts": payload["latest_status_counts"],
        "evaluable_natural_10_to_20_count": payload["evaluable_natural_10_to_20_count"],
        "machine_passed_count": payload["machine_passed_count"],
        "human_review": payload["human_review"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
