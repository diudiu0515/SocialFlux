#!/usr/bin/env python3
"""Archive retained trajectories and reopen their rollout slots."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".requeue.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def remove_manifest_reference(directory, trajectory_id):
    path = Path(directory) / "manifest.json"
    if not path.exists():
        return
    manifest = json.loads(path.read_text(encoding="utf-8"))
    remaining = [x for x in manifest.get("trajectory_ids", []) if x != trajectory_id]
    manifest["trajectory_ids"] = remaining
    manifest["trajectory_count"] = len(remaining)
    if not remaining:
        manifest["scenario_ids"] = []
        manifest["policy_ids"] = []
    manifest.setdefault("config", {})["generation_status"] = "in_progress"
    atomic_json(path, manifest)


def scenario_directory(root, scenario_id):
    ordinal = int(str(scenario_id).rsplit("_", 1)[1])
    return root / f"scenario_{ordinal:03d}"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rollout-root",
        type=Path,
        default=Path("data/gpt50/experiment/rollouts"),
    )
    parser.add_argument("--minimum-turns", type=int, default=10)
    parser.add_argument(
        "--all-completed",
        action="store_true",
        help="reopen every completed slot after a rollout-contract change",
    )
    args = parser.parse_args(argv)
    if args.minimum_turns < 1:
        raise ValueError("minimum turns must be positive")

    root = args.rollout_root.resolve()
    progress_path = root / "progress.json"
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    completed = progress.get("completed_slots", {})
    reopened = []

    for slot_id, record in list(completed.items()):
        turn_count = int(record.get("turn_count") or 0)
        if (
            not args.all_completed
            and
            turn_count >= args.minimum_turns
            and record.get("machine_precheck_passed") is True
        ):
            continue
        scenario_id = record["scenario_id"]
        directory = scenario_directory(root, scenario_id)
        source = directory / record["trajectory_file"]
        archive = directory / "requeued_short_trajectories"
        archive.mkdir(parents=True, exist_ok=True)
        target = archive / record["trajectory_file"]
        if source.exists():
            os.replace(source, target)
        elif not target.exists():
            raise FileNotFoundError(source)
        remove_manifest_reference(directory, record.get("trajectory_id"))
        progress.setdefault("attempts", []).append({
            "slot_id": slot_id,
            "scenario_id": scenario_id,
            "planned_policy_id": record.get("planned_policy_id"),
            "actual_policy_id": record.get("actual_policy_id"),
            "status": "requeued_short_trajectory",
            "finished_at_utc": utc_now(),
            "trajectory_id": record.get("trajectory_id"),
            "trajectory_file": str(target.relative_to(directory)),
            "turn_count": turn_count,
            "machine_precheck_passed": record.get(
                "machine_precheck_passed"
            ) is True,
            "reason": (
                "retained artifact is below the minimum useful trajectory "
                "contract or failed machine precheck"
            ),
        })
        reopened.append({
            "slot_id": slot_id,
            "scenario_id": scenario_id,
            "turn_count": turn_count,
            "archived_to": str(target.relative_to(root)),
        })
        del completed[slot_id]

    progress["completed_slot_count"] = len(completed)
    progress["status"] = "incomplete_requeued_short_trajectories"
    progress["updated_at_utc"] = utc_now()
    progress.setdefault("requeue_history", []).append({
        "requeued_at_utc": utc_now(),
        "minimum_turns": args.minimum_turns,
        "all_completed": args.all_completed,
        "reopened_count": len(reopened),
        "records": reopened,
    })
    atomic_json(progress_path, progress)
    print(json.dumps({
        "rollout_root": str(root),
        "reopened_count": len(reopened),
        "remaining_completed_count": len(completed),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
