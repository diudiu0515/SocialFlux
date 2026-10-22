#!/usr/bin/env python3
"""Restore archived rollout slots only after current-contract revalidation.

This is deliberately a local recovery tool: it never invokes a provider.  A
trajectory is restored only when its scenario fingerprint still matches and
the current machine precheck passes.  The original requeue evidence remains
in progress.json and a separate restoration history is appended.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.artifacts import write_dialogues
from rollout.configuration import load_rollout_config, public_rollout_config
from rollout.manifest import write_manifest
from scripts.generate_long_rollout_pool import (
    MAX_TURNS,
    QUALITY_VERSION,
    _machine_precheck,
    _quality_fingerprint,
    _scenario_fingerprint,
)


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".restore.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _scenario_paths(scenario_root, scenario_id):
    ordinal = int(str(scenario_id).rsplit("_", 1)[1])
    directory = Path(scenario_root) / f"scenario_{ordinal:03d}"
    return directory, directory / f"scenario_{ordinal:03d}.json"


def _accepted_records(progress):
    records = {}
    for item in progress.get("attempts", []):
        if item.get("status") == "accepted":
            records[(item.get("slot_id"), item.get("trajectory_id"))] = item
    return records


def _refresh_bundle(rollout_root, scenario, scenario_directory, progress, config):
    trajectories = []
    for record in progress.get("completed_slots", {}).values():
        if record.get("scenario_id") != scenario.get("scenario_id"):
            continue
        path = Path(rollout_root) / scenario_directory / record["trajectory_file"]
        trajectories.append(json.loads(path.read_text(encoding="utf-8")))
    trajectories.sort(key=lambda item: item.get("batch_slot_id", ""))
    output = Path(rollout_root) / scenario_directory
    write_dialogues(output / "dialogues.md", scenario, trajectories)
    write_manifest(
        output / "manifest.json",
        trajectories,
        {
            "origin": "free_form_model_interaction",
            "pool_stage": config.get("pool_stage", "development"),
            "rollout_config": public_rollout_config(config),
            "max_turns": MAX_TURNS,
            "horizon_contract": "natural_end_at_or_before_max",
            "generation_status": "in_progress",
            "progress_file": "../progress.json",
            "dialogues": "dialogues.md",
            "task_review": None,
            "quality_version": QUALITY_VERSION,
            "quality_fingerprint": _quality_fingerprint(),
            "scenario_fingerprint": _scenario_fingerprint(scenario),
        },
    )


def restore_valid_requeued(rollout_root, scenario_root, *, dry_run=False):
    rollout_root = Path(rollout_root)
    scenario_root = Path(scenario_root)
    progress_path = rollout_root / "progress.json"
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    accepted = _accepted_records(progress)
    completed = progress.setdefault("completed_slots", {})
    latest_requeue = (progress.get("requeue_history") or [{}])[-1]
    affected_scenario_ids = {
        item.get("scenario_id")
        for item in latest_requeue.get("records", [])
        if item.get("scenario_id")
    }
    restored = []
    skipped = []

    for item in latest_requeue.get("records", []):
        slot_id = item.get("slot_id")
        trajectory_id = Path(item.get("archived_to", "")).stem
        attempt = accepted.get((slot_id, trajectory_id))
        if attempt is None:
            skipped.append({"slot_id": slot_id, "reason": "not_previously_accepted"})
            continue
        archived = rollout_root / item["archived_to"]
        scenario_directory, scenario_path = _scenario_paths(
            scenario_root, item["scenario_id"]
        )
        if not archived.exists() or not scenario_path.exists():
            skipped.append({"slot_id": slot_id, "reason": "artifact_missing"})
            continue
        trajectory = json.loads(archived.read_text(encoding="utf-8"))
        scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
        if trajectory.get("scenario_fingerprint") != _scenario_fingerprint(scenario):
            skipped.append({"slot_id": slot_id, "reason": "scenario_fingerprint_mismatch"})
            continue
        precheck = _machine_precheck(trajectory)
        if not precheck["passed"]:
            skipped.append({
                "slot_id": slot_id,
                "reason": precheck.get("candidate_classification", "machine_rejected"),
            })
            continue
        target = rollout_root / scenario_directory.name / archived.name
        if target.exists() and target.read_bytes() != archived.read_bytes():
            raise ValueError(f"refusing to overwrite different artifact: {target}")
        record = {
            "scenario_id": item["scenario_id"],
            "planned_policy_id": attempt.get("planned_policy_id"),
            "actual_policy_id": trajectory.get("policy_id"),
            "trajectory_id": trajectory["trajectory_id"],
            "trajectory_file": target.name,
            "turn_count": len(trajectory.get("turns", [])),
            "scenario_fingerprint": trajectory["scenario_fingerprint"],
            "accepted_at_utc": attempt.get("finished_at_utc"),
            "admission": "machine_precheck",
            "machine_precheck_passed": True,
        }
        restored.append({
            "slot_id": slot_id,
            "scenario_id": item["scenario_id"],
            "from": str(archived.relative_to(rollout_root)),
            "to": str(target.relative_to(rollout_root)),
            "turn_count": record["turn_count"],
        })
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                os.replace(archived, target)
            elif archived.exists():
                archived.unlink()
            completed[slot_id] = record

    if not dry_run:
        progress["completed_slot_count"] = len(completed)
        progress["status"] = (
            "completed"
            if len(completed) == progress.get("expected_slot_count")
            else "incomplete_retry_exhausted"
        )
        progress["updated_at_utc"] = _utc_now()
        if restored:
            progress.setdefault("restoration_history", []).append({
                "restored_at_utc": progress["updated_at_utc"],
                "contract": "current_machine_precheck_and_scenario_fingerprint",
                "restored_count": len(restored),
                "records": restored,
            })
        _atomic_json(progress_path, progress)
        config_path = Path(progress["config_path"])
        config = load_rollout_config(config_path)
        for scenario_id in sorted(affected_scenario_ids):
            scenario_directory, scenario_path = _scenario_paths(
                scenario_root, scenario_id
            )
            if not scenario_path.exists():
                continue
            scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
            _refresh_bundle(
                rollout_root, scenario, scenario_directory.name, progress, config
            )
    return {"restored": restored, "skipped": skipped, "dry_run": dry_run}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollout-root", type=Path, required=True)
    parser.add_argument("--scenario-root", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = restore_valid_requeued(
        args.rollout_root, args.scenario_root, dry_run=args.dry_run
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
