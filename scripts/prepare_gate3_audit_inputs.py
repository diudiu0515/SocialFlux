#!/usr/bin/env python3
"""Materialize one retained trajectory per scenario for machine Gate 3 review."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.prepare_gate2_audit_inputs import selected_inputs
from scripts.scenario_docs import discover_scenario_paths


ROOT = Path(__file__).resolve().parents[1]


def now():
    return datetime.now(timezone.utc).isoformat()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def project_relative(path):
    return str(Path(path).resolve().relative_to(ROOT))


def attempt_index(rollout_root):
    progress = load(Path(rollout_root) / "progress.json")
    return {
        item["trajectory_id"]: item
        for item in progress.get("attempts", [])
        if item.get("trajectory_id")
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument("--scenario-root", type=Path, required=True)
    parser.add_argument("--rollout-root", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, required=True)
    args = parser.parse_args(argv)

    batch = args.batch_root.resolve()
    scenario_root = args.scenario_root.resolve()
    rollout_root = args.rollout_root.resolve()
    selected = selected_inputs(scenario_root, rollout_root)
    if len(selected) != args.expected_count:
        raise ValueError(
            f"Gate 3 input requires {args.expected_count} scenarios, "
            f"found {len(selected)}"
        )
    scenarios = {
        load(path)["scenario_id"]: path
        for path in discover_scenario_paths(scenario_root)
    }
    attempts = attempt_index(rollout_root)
    packages = []
    reviews = []
    audits = []
    human_records = []
    for ordinal, record in enumerate(selected, start=1):
        trajectory = record["trajectory"]
        trajectory_id = trajectory["trajectory_id"]
        scenario_id = record["scenario_id"]
        scenario_path = scenarios[scenario_id]
        source_path = record["source_path"]
        attempt = attempts.get(trajectory_id, {})
        package = {
            "format": "socialflux_gate3_audit_source_v1",
            "ordinal": ordinal,
            "scenario_id": scenario_id,
            "source_trajectory_id": trajectory_id,
            "source_artifact": project_relative(source_path),
            "scenario_artifact": project_relative(scenario_path),
            "turn_count": len(trajectory.get("turns", [])),
            "source_status": record["source_status"],
            "admission": "machine_gate3_audit",
            "machine_precheck": attempt.get("precheck", {}),
            "human_review": "skipped_pending_optional_audit",
        }
        target = (
            batch / "source_packages" / "shard1"
            / f"scenario_{ordinal:03d}.json"
        )
        atomic(target, package)
        packages.append(package)
        reviews.append({
            "ordinal": ordinal,
            "scenario_id": scenario_id,
            "generation_status": record["source_status"],
            "model_semantic_review": {
                "decision": "pending",
                "reviewer_type": "not_run",
            },
            "human_review": "skipped_pending_optional_audit",
            "latest_attempt": {
                "artifact_path": project_relative(source_path),
                "artifact_sha256": sha256(source_path),
                "scenario_version_matches_current": True,
                "machine_precheck": attempt.get("precheck", {}),
                "ending": trajectory.get("ending", {}),
            },
        })
        gate3 = {
            "generation_status": record["source_status"],
            "machine_precheck": attempt.get("precheck", {}),
            "model_semantic_review": {"decision": "pending"},
            "human_status": "skipped_pending_optional_audit",
            "admission": "machine_gate3_audit",
        }
        audits.append({
            "ordinal": ordinal,
            "scenario_id": scenario_id,
            "trajectory_id": trajectory_id,
            "gates": {
                "gate1": {"human_status": "pending"},
                "gate2": {"human_status": "skipped"},
                "gate3": gate3,
                "gate4": {"human_status": "pending"},
            },
        })
        human_records.append({
            "ordinal": ordinal,
            "scenario_id": scenario_id,
            "trajectory_id": trajectory_id,
            "trajectory_file": project_relative(source_path),
            "trajectory_sha256": sha256(source_path),
            "turn_count": len(trajectory.get("turns", [])),
            "machine_precheck": attempt.get("precheck", {}),
            "reviewer": "",
            "reviewed_at_utc": "",
            "decision": "pending",
            "human_attestation": False,
            "human_execution": "skipped",
            "notes": "",
        })

    atomic(batch / "source_review.json", {
        "format": "socialflux_gate3_audit_source_review_v1",
        "candidate_count": len(reviews),
        "admission": "machine_gate3_audit",
        "human_review": "skipped_pending_optional_audit",
        "candidates": reviews,
    })
    atomic(batch / "automatic_gate_audit.json", {
        "format": "socialflux_machine_gate_audit_v1",
        "warning": "Machine diagnostics are not human attestations.",
        "records": audits,
    })
    atomic(batch / "human_review" / "gate3_rollouts.json", {
        "format": "socialflux_gate3_optional_human_review_v1",
        "created_at_utc": now(),
        "population_count": len(human_records),
        "sample_count": 0,
        "sampling": "human_execution_skipped",
        "records": human_records,
    })
    atomic(batch / "source_packages" / "summary.json", {
        "format": "socialflux_gate3_audit_source_summary_v1",
        "package_count": len(packages),
        "admission": "machine_gate3_audit",
        "human_review": "skipped_pending_optional_audit",
    })
    print(json.dumps({
        "gate3_inputs": len(packages),
        "source_status_counts": {
            status: sum(item["source_status"] == status for item in packages)
            for status in sorted({item["source_status"] for item in packages})
        },
        "batch_root": str(batch),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
