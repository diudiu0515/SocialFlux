#!/usr/bin/env python3
"""Materialize every Claude150 rollout as a downstream candidate source.

Machine gate results are copied as diagnostics. They never become human
attestations and do not remove a source from the candidate catalog.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas.validate import validate_scenario, validate_trajectory
from shared.artifacts import atomic_json as atomic


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BATCH = ROOT / "data" / "claude150_v1"


def now():
    return datetime.now(timezone.utc).isoformat()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative(path):
    return str(Path(path).resolve().relative_to(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-root", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--count", type=int, default=150)
    args = parser.parse_args(argv)
    batch = args.batch_root.resolve()
    progress_path = batch / "rollouts" / "progress.json"
    progress = load(progress_path)
    if progress.get("admission_mode") != "human_postfilter":
        raise ValueError("Claude150 sources require human_postfilter rollouts")
    completed = progress.get("completed_slots", {})
    attempts = {
        item.get("trajectory_id"): item
        for item in progress.get("attempts", [])
        if item.get("trajectory_id")
    }
    packages = []
    reviews = []
    audits = []
    human_records = []
    for ordinal in range(1, args.count + 1):
        name = f"scenario_{ordinal:03d}"
        scenario_path = batch / "scenarios" / name / f"{name}.json"
        scenario = load(scenario_path)
        validate_scenario(scenario)
        matches = [
            item for item in completed.values()
            if item.get("scenario_id") == scenario["scenario_id"]
        ]
        if len(matches) != 1:
            raise ValueError(
                f"{scenario['scenario_id']} requires exactly one completed rollout"
            )
        selected = matches[0]
        trajectory_path = (
            batch / "rollouts" / name / selected["trajectory_file"]
        )
        trajectory = load(trajectory_path)
        validate_trajectory(trajectory)
        attempt = attempts.get(trajectory["trajectory_id"])
        if attempt is None:
            raise ValueError(f"missing attempt record for {trajectory['trajectory_id']}")
        artifact = relative(trajectory_path)
        package = {
            "format": "socialflux_claude150_candidate_source_v1",
            "ordinal": ordinal,
            "scenario_id": scenario["scenario_id"],
            "source_trajectory_id": trajectory["trajectory_id"],
            "source_artifact": artifact,
            "turn_count": len(trajectory.get("turns", [])),
            "admission": "human_postfilter",
            "machine_precheck": attempt.get("precheck", {}),
            "human_review": "pending",
        }
        package_path = batch / "source_packages" / "shard1" / f"{name}.json"
        atomic(package_path, package)
        packages.append(package)
        review = {
            "ordinal": ordinal,
            "scenario_id": scenario["scenario_id"],
            "generation_status": attempt.get("status"),
            "model_semantic_review": {
                "decision": "pending",
                "reviewer_type": "not_run",
            },
            "human_review": "pending",
            "latest_attempt": {
                "artifact_path": artifact,
                "artifact_sha256": sha256(trajectory_path),
                "scenario_version_matches_current": True,
                "machine_precheck": attempt.get("precheck", {}),
                "ending": trajectory.get("ending", {}),
            },
        }
        reviews.append(review)
        gate3 = {
            "generation_status": attempt.get("status"),
            "machine_precheck": attempt.get("precheck", {}),
            "model_semantic_review": {"decision": "pending"},
            "human_status": "pending",
            "admission": "human_postfilter",
        }
        audits.append({
            "ordinal": ordinal,
            "scenario_id": scenario["scenario_id"],
            "trajectory_id": trajectory["trajectory_id"],
            "gates": {
                "gate1": {"human_status": "pending"},
                "gate2": {"human_status": "pending"},
                "gate3": gate3,
                "gate4": {"human_status": "pending"},
            },
        })
        human_records.append({
            "ordinal": ordinal,
            "scenario_id": scenario["scenario_id"],
            "trajectory_id": trajectory["trajectory_id"],
            "trajectory_file": artifact,
            "trajectory_sha256": sha256(trajectory_path),
            "turn_count": len(trajectory.get("turns", [])),
            "machine_precheck": attempt.get("precheck", {}),
            "reviewer": "",
            "reviewed_at_utc": "",
            "decision": "pending",
            "human_attestation": False,
            "ratings": {
                "speaker_ownership": None,
                "character_coherence": None,
                "state_transition_plausibility": None,
                "history_dependence": None,
                "natural_ending": None,
                "task_source_utility": None,
            },
            "notes": "",
        })
    atomic(batch / "source_review.json", {
        "format": "socialflux_claude150_source_review_v1",
        "candidate_count": len(reviews),
        "admission": "generate_all_then_human_postfilter",
        "human_review": "pending",
        "candidates": reviews,
    })
    atomic(batch / "automatic_gate_audit.json", {
        "format": "socialflux_claude150_machine_diagnostics_v1",
        "warning": "Machine diagnostics are not gate approval or human evidence.",
        "records": audits,
    })
    atomic(batch / "human_review" / "gate3_rollouts.json", {
        "format": "socialflux_claude150_gate3_review_v1",
        "created_at_utc": now(),
        "population_count": len(human_records),
        "sample_count": len(human_records),
        "sampling": "full_population",
        "records": human_records,
    })
    atomic(batch / "source_packages" / "summary.json", {
        "format": "socialflux_claude150_candidate_source_summary_v1",
        "package_count": len(packages),
        "admission": "human_postfilter",
        "human_review": "pending",
    })
    print(json.dumps({
        "sources": len(packages),
        "reviews": len(reviews),
        "human_gate3_records": len(human_records),
        "batch_root": str(batch),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
