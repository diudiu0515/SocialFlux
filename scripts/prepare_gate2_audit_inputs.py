#!/usr/bin/env python3
"""Materialize one retained GPT50 trajectory per scenario for Gate 2 audit."""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scenario_design.catalog import discover_scenario_paths
from shared.artifacts import atomic_json as atomic


def now():
    return datetime.now(timezone.utc).isoformat()


def artifact_path(rollout_root, scenario_directory, attempt):
    filename = (
        attempt.get("trajectory_file")
        or attempt.get("partial_trajectory_file")
    )
    if not filename:
        return None
    scenario_root = rollout_root / scenario_directory
    for parent in (
        scenario_root,
        scenario_root / "rejected",
        scenario_root / "budget_truncated",
        scenario_root / "short_trajectories",
    ):
        candidate = parent / filename
        if candidate.is_file():
            return candidate
    return None


def selected_inputs(scenario_root, rollout_root):
    progress = json.loads(
        (rollout_root / "progress.json").read_text(encoding="utf-8")
    )
    completed = {
        item["scenario_id"]: item
        for item in (progress.get("completed_slots") or {}).values()
    }
    attempts_by_scenario = {}
    for attempt_index, attempt in enumerate(progress.get("attempts") or []):
        scenario_id = attempt.get("scenario_id")
        if scenario_id:
            attempts_by_scenario.setdefault(scenario_id, []).append(
                (attempt_index, attempt)
            )

    selected = []
    for scenario_path in discover_scenario_paths(scenario_root):
        scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
        scenario_id = scenario["scenario_id"]
        scenario_directory = scenario_path.parent.name
        accepted = completed.get(scenario_id)
        candidates = []
        if accepted:
            path = rollout_root / scenario_directory / accepted["trajectory_file"]
            if path.is_file():
                value = json.loads(path.read_text(encoding="utf-8"))
                candidates.append((
                    1,
                    len(value.get("turns", [])),
                    len(progress.get("attempts") or []),
                    "accepted",
                    path,
                    value,
                ))
        for attempt_index, attempt in attempts_by_scenario.get(scenario_id, []):
            path = artifact_path(rollout_root, scenario_directory, attempt)
            if path is None:
                continue
            value = json.loads(path.read_text(encoding="utf-8"))
            turn_count = len(value.get("turns", []))
            if turn_count < 1:
                continue
            candidates.append((
                int(attempt.get("status") == "accepted"),
                turn_count,
                attempt_index,
                attempt.get("status", "unknown"),
                path,
                value,
            ))
        if not candidates:
            raise ValueError(
                f"{scenario_id} has no retained trajectory with at least one turn"
            )
        accepted_priority, turn_count, _, source_status, path, trajectory = max(
            candidates,
            key=lambda item: (item[0], item[1], item[2]),
        )
        selected.append({
            "scenario_id": scenario_id,
            "scenario_directory": scenario_directory,
            "source_status": source_status,
            "source_path": path,
            "turn_count": turn_count,
            "trajectory": trajectory,
        })
    return selected


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario-root", type=Path, required=True)
    parser.add_argument("--rollout-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, default=50)
    parser.add_argument(
        "--source-status",
        choices=("all", "accepted", "machine_rejected", "generation_error"),
        default="all",
        help="materialize one explicit provenance cohort; never infer acceptance from depth",
    )
    args = parser.parse_args(argv)

    population_records = selected_inputs(
        args.scenario_root.resolve(),
        args.rollout_root.resolve(),
    )
    population_status_counts = Counter(
        item["source_status"] for item in population_records
    )
    records = [
        item for item in population_records
        if args.source_status == "all"
        or item["source_status"] == args.source_status
    ]
    if len(records) != args.expected_count:
        raise ValueError(
            f"Gate 2 audit input requires {args.expected_count} scenarios, "
            f"found {len(records)}"
        )
    manifest_records = []
    for record in records:
        trajectory = deepcopy(record["trajectory"])
        trajectory["gate2_audit_input"] = {
            "source_status": record["source_status"],
            "source_path": str(record["source_path"]),
            "turn_count": record["turn_count"],
            "retained_without_deletion": True,
        }
        target = (
            args.output_root
            / record["scenario_directory"]
            / "trajectory.json"
        )
        atomic(target, trajectory)
        manifest_records.append({
            "scenario_id": record["scenario_id"],
            "trajectory_id": trajectory.get("trajectory_id"),
            "source_status": record["source_status"],
            "turn_count": record["turn_count"],
            "source_path": str(record["source_path"]),
            "audit_path": str(target),
        })
    manifest = {
        "format": "socialflux_gate2_all_scenario_audit_inputs_v1",
        "created_at_utc": now(),
        "selection": (
            "accepted trajectory when available; otherwise the deepest retained "
            "current rejected/partial trajectory"
        ),
        "deletion_policy": "retain_all_source_artifacts",
        "scenario_count": len(manifest_records),
        "source_status_filter": args.source_status,
        "population_scenario_count": len(population_records),
        "population_source_status_counts": dict(population_status_counts),
        "source_status_counts": dict(Counter(
            item["source_status"] for item in manifest_records
        )),
        "turn_count_distribution": dict(Counter(
            item["turn_count"] for item in manifest_records
        )),
        "exact_20_turn_count": sum(
            item["turn_count"] == 20 for item in manifest_records
        ),
        "main_10_to_20_turn_count": sum(
            10 <= item["turn_count"] <= 20 for item in manifest_records
        ),
        "records": manifest_records,
    }
    atomic(args.output_root / "gate2_input_manifest.json", manifest)
    print(json.dumps({
        key: manifest[key] for key in (
            "format", "scenario_count", "source_status_counts",
            "deletion_policy",
        )
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
