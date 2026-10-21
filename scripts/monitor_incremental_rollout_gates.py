#!/usr/bin/env python3
"""Monitor a live rollout batch and prepare local Gate 1/2 evidence incrementally.

This process performs no provider calls. It preserves the formal human boundary:
Gate 1 and Gate 2 human fields remain pending. API-backed Gate 2 experiments
(E3-E7) are intentionally left to a fixed-cohort run.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.quality_gates import audit_scenario_gate
from scenario_design.catalog import discover_scenario_paths
from shared.artifacts import atomic_json as atomic


ROOT = Path(__file__).resolve().parents[1]
TERMINAL_PROGRESS = {
    "completed",
    "incomplete_retry_exhausted",
    "paused_provider_overload",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def project_path(path):
    path = Path(path).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def load(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def scenario_index(root):
    result = {}
    for path in discover_scenario_paths(root):
        value = load(path)
        result[value["scenario_id"]] = (path, value)
    return result


def trajectory_state_watch(trajectory):
    changed_by_family = Counter()
    selected_by_timescale = Counter()
    suppressed = Counter()
    active_opportunities = []
    slow_changes = []
    for turn in trajectory.get("turns", []):
        before = turn.get("state_before") or {}
        after = turn.get("state_after") or {}
        changed_paths = set()
        for family, values in after.items():
            if not isinstance(values, dict):
                continue
            for variable, value in values.items():
                if (before.get(family) or {}).get(variable) != value:
                    path = f"{family}.{variable}"
                    changed_paths.add(path)
                    changed_by_family[family] += 1
        for impact in (turn.get("calibration") or {}).get("state_impacts") or []:
            if impact.get("selected"):
                timescale = impact.get("timescale", "unknown")
                selected_by_timescale[timescale] += 1
                if (
                    timescale == "cross_turn_slow"
                    and impact.get("variable") in changed_paths
                ):
                    slow_changes.append({
                        "turn_id": turn.get("turn_id"),
                        "variable": impact.get("variable"),
                        "direction": impact.get("direction"),
                        "evidence_span": impact.get("evidence_span"),
                    })
            elif impact.get("suppressed_by"):
                suppressed[impact["suppressed_by"]] += 1
        opportunity = turn.get("state_transition_opportunity") or {}
        if opportunity.get("active"):
            active_opportunities.append({
                "turn_id": turn.get("turn_id"),
                "selected_path": opportunity.get("selected_path"),
                "evidence_stage": opportunity.get("evidence_stage"),
                "selection_basis": opportunity.get("selection_basis"),
            })
    return {
        "turn_count": len(trajectory.get("turns", [])),
        "ending": trajectory.get("ending"),
        "changed_by_family": dict(sorted(changed_by_family.items())),
        "all_four_families_changed": all(
            changed_by_family.get(name, 0) > 0
            for name in (
                "emotion",
                "behavioral_disposition",
                "relationship",
                "consequence_risk",
            )
        ),
        "selected_by_timescale": dict(sorted(selected_by_timescale.items())),
        "compliant_slow_change_count": len(slow_changes),
        "slow_changes": slow_changes,
        "active_opportunities": active_opportunities,
        "suppression_reasons": dict(sorted(suppressed.items())),
    }


def locate_trajectory(rollout_root, attempt):
    filename = attempt.get("trajectory_file") or attempt.get(
        "partial_trajectory_file"
    )
    if not filename:
        return None
    matches = list(rollout_root.glob(f"scenario_*/{filename}"))
    matches += list(rollout_root.glob(f"scenario_*/*/{filename}"))
    return matches[0] if matches else None


def completed_records(progress, scenarios, rollout_root):
    records = []
    for attempt in progress.get("attempts") or []:
        scenario_id = attempt.get("scenario_id")
        if not scenario_id or scenario_id not in scenarios:
            continue
        scenario_path, scenario = scenarios[scenario_id]
        gate1 = audit_scenario_gate(scenario, scenario_path, None)
        machine_gate1_failures = [
            name for name, check in gate1["checks"].items()
            if name not in {"quality_checklist", "human_approval"}
            and check["status"] in {"fail", "revise"}
        ]
        trajectory_path = locate_trajectory(rollout_root, attempt)
        trajectory = load(trajectory_path) if trajectory_path else None
        precheck = attempt.get("precheck") or {}
        record = {
            "scenario_id": scenario_id,
            "slot_id": attempt.get("slot_id"),
            "attempt": attempt.get("attempt"),
            "attempt_status": attempt.get("status"),
            "trajectory_id": attempt.get("trajectory_id")
            or attempt.get("partial_trajectory_id"),
            "trajectory_path": str(trajectory_path) if trajectory_path else None,
            "gate1": {
                "formal_status": gate1["status"],
                "human_status": "pending",
                "machine_diagnostic_passed": not machine_gate1_failures,
                "machine_diagnostic_failures": machine_gate1_failures,
            },
            "gate2": {
                "human_status": "pending",
                "machine_precheck_passed": precheck.get("passed"),
                "candidate_classification": precheck.get(
                    "candidate_classification"
                ),
                "checks": precheck.get("checks") or {},
                "state_v3_metrics": precheck.get("state_v3_metrics"),
            },
            "actual_request_counts": attempt.get("actual_request_counts") or {},
            "provider_error": (
                {
                    "type": attempt.get("error_type"),
                    "message": attempt.get("error"),
                }
                if attempt.get("status") == "generation_error"
                else None
            ),
        }
        if trajectory:
            record["state_watch"] = trajectory_state_watch(trajectory)
        records.append(record)
    return records


def live_records(rollout_root):
    records = []
    for path in sorted(rollout_root.glob("scenario_*/in_progress/*.json")):
        trajectory = load(path)
        if not trajectory:
            continue
        checkpoint_status = trajectory.get("checkpoint_status")
        if checkpoint_status in {
            "trajectory_completed",
            "generation_error",
            "machine_rejected",
        }:
            continue
        records.append({
            "scenario_id": trajectory.get("scenario_id"),
            "trajectory_id": trajectory.get("trajectory_id"),
            "checkpoint_status": checkpoint_status,
            "checkpoint_updated_at_utc": trajectory.get(
                "checkpoint_updated_at_utc"
            ),
            "path": str(path),
            "actual_request_counts": trajectory.get(
                "actual_request_counts"
            ) or {},
            "state_watch": trajectory_state_watch(trajectory),
        })
    return records


def write_status(batch_root, progress, records, live, gate2_prepare):
    attempt_counts = Counter(
        item.get("attempt_status", "unknown") for item in records
    )
    state_ready = sum(
        bool((item.get("state_watch") or {}).get("all_four_families_changed"))
        and (item.get("state_watch") or {}).get(
            "compliant_slow_change_count", 0
        ) > 0
        for item in records
    )
    payload = {
        "format": "socialflux_incremental_rollout_gates_v1",
        "updated_at_utc": now(),
        "rollout_status": progress.get("status"),
        "expected_slot_count": progress.get("expected_slot_count", 0),
        "completed_slot_count": progress.get("completed_slot_count", 0),
        "attempt_status_counts": dict(sorted(attempt_counts.items())),
        "state_ready_attempt_count": state_ready,
        "formal_human_boundary": {
            "gate1": "pending",
            "gate2": "pending",
            "machine_results_do_not_replace_human_review": True,
        },
        "gate2_prepare": gate2_prepare,
        "live": live,
        "records": records,
    }
    output = batch_root / "incremental_gates" / "status.json"
    atomic(output, payload)
    for record in records:
        key = "{}__attempt_{}".format(
            record["scenario_id"], record.get("attempt") or 0
        )
        atomic(
            batch_root / "incremental_gates" / "records" / f"{key}.json",
            record,
        )
    return payload


def prepare_gate2(batch_root, scenario_root, rollout_root, rollout_config):
    log_path = batch_root / "logs" / "incremental_gate2_prepare.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(ROOT / "scripts" / "prepare_batch_gate2.py"),
        "--batch-root", str(batch_root),
        "--scenario-root", str(scenario_root),
        "--rollout-root", str(rollout_root),
        "--rollout-config", str(rollout_config),
        "--all-scenarios",
        "--prepare-only",
    ]
    started = now()
    with log_path.open("a", encoding="utf-8") as log:
        result = subprocess.run(
            command,
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    return {
        "status": "completed" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "started_at_utc": started,
        "finished_at_utc": now(),
        "log": str(log_path),
        "network_requests_performed": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollout-root", type=Path, required=True)
    parser.add_argument("--scenario-root", type=Path, required=True)
    parser.add_argument("--rollout-config", type=Path, required=True)
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--follow", action="store_true")
    args = parser.parse_args(argv)
    if args.poll_seconds < 1:
        parser.error("--poll-seconds must be positive")

    rollout_root = project_path(args.rollout_root)
    scenario_root = project_path(args.scenario_root)
    rollout_config = project_path(args.rollout_config)
    batch_root = project_path(args.batch_root)
    scenarios = scenario_index(scenario_root)
    last_gate2_count = -1
    gate2_prepare = {"status": "not_started", "network_requests_performed": 0}

    while True:
        progress = load(rollout_root / "progress.json", {}) or {}
        records = completed_records(progress, scenarios, rollout_root)
        live = live_records(rollout_root)
        completed_count = int(progress.get("completed_slot_count", 0) or 0)
        if completed_count > 0 and completed_count != last_gate2_count:
            gate2_prepare = prepare_gate2(
                batch_root, scenario_root, rollout_root, rollout_config
            )
            last_gate2_count = completed_count
        payload = write_status(
            batch_root, progress, records, live, gate2_prepare
        )
        print(json.dumps({
            "status": payload["rollout_status"],
            "completed": payload["completed_slot_count"],
            "expected": payload["expected_slot_count"],
            "state_ready_attempts": payload["state_ready_attempt_count"],
            "live": len(live),
            "gate2_prepare": gate2_prepare["status"],
        }, ensure_ascii=False), flush=True)
        if not args.follow:
            break
        if progress.get("status") in TERMINAL_PROGRESS and not live:
            break
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
