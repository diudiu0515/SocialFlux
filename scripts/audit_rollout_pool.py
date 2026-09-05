#!/usr/bin/env python3
"""Audit trajectory bundles and record machine-clean pool status."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.instance_quality import audit_trajectory
from scripts.scenario_docs import discover_scenario_paths


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def audit_pool(scenario_root, output, update_manifests=False):
    records = []
    for scenario_path in discover_scenario_paths(scenario_root):
        rollout_dir = scenario_path.parent / "rollouts"
        manifest_path = rollout_dir / "manifest.json"
        manifest = load(manifest_path)
        audits = []
        for trajectory_id in manifest["trajectory_ids"]:
            trajectory = load(rollout_dir / f"{trajectory_id}.json")
            audits.append(audit_trajectory(trajectory))
        clean = all(item["passed"] for item in audits)
        record = {
            "scenario_id": load(scenario_path)["scenario_id"],
            "trajectory_count": len(audits),
            "machine_clean_count": sum(item["passed"] for item in audits),
            "machine_clean": clean,
            "trajectories": audits,
        }
        records.append(record)
        if update_manifests:
            manifest.setdefault("config", {})["clean_pool"] = {
                "status": "machine_clean" if clean else "rejected",
                "quality_gate": "distinct_text_v2",
                "passed": record["machine_clean_count"],
                "total": record["trajectory_count"],
                "human_plausibility": "pending",
            }
            dump(manifest_path, manifest)
    report = {
        "format": "socialflux_rollout_quality_v2",
        "trajectory_count": sum(item["trajectory_count"] for item in records),
        "machine_clean_count": sum(item["machine_clean_count"] for item in records),
        "all_machine_clean": all(item["machine_clean"] for item in records),
        "human_plausibility": "pending",
        "scenarios": records,
    }
    dump(output, report)
    print(json.dumps({
        "trajectory_count": report["trajectory_count"],
        "machine_clean_count": report["machine_clean_count"],
        "all_machine_clean": report["all_machine_clean"],
        "human_plausibility": report["human_plausibility"],
    }, ensure_ascii=False))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario-root", type=Path, default=Path("configs/scenarios"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("build/rollout_quality_report.json"),
    )
    parser.add_argument("--update-manifests", action="store_true")
    args = parser.parse_args()
    audit_pool(args.scenario_root, args.output, args.update_manifests)


if __name__ == "__main__":
    main()
