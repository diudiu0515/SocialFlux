#!/usr/bin/env python3
"""Regenerate per-scenario natural-language task review files from canonical artifacts."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_pipeline import load_scenario_records
from scripts.task_docs import write_task_review


def jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline-output", type=Path, required=True)
    parser.add_argument("--scenarios", type=Path, default=Path("configs/scenarios"))
    args = parser.parse_args()
    records = {item["scenario_id"]: (path, item) for path, item in load_scenario_records(args.scenarios)}
    refreshed = 0
    summaries = []
    for scenario_root in sorted(args.pipeline_output.glob("IA_PIPE_*")):
        pipeline = json.loads((scenario_root / "pipeline_manifest.json").read_text(encoding="utf-8"))
        scenario_id = pipeline["scenario_id"]
        scenario_path, scenario = records[scenario_id]
        rollout_root = scenario_path.parent / "rollouts"
        manifest = json.loads((rollout_root / "manifest.json").read_text(encoding="utf-8"))
        trajectories = [
            json.loads((rollout_root / f"{identifier}.json").read_text(encoding="utf-8"))
            for identifier in manifest.get("trajectory_ids", [])
        ]
        instances = jsonl(scenario_root / "offline" / "instances.jsonl")
        branches = json.loads((scenario_root / "validation" / "local_action_interventions.json").read_text(encoding="utf-8"))
        t3_instances = [
            item for item in instances
            if item["task_type"] == "T3_counterfactual_choice_effect"
        ]
        attempts_path = scenario_root / "validation" / "t3_selection_attempts.json"
        if not attempts_path.exists() and t3_instances:
            metadata = t3_instances[0]["metadata"]
            attempts = [{
                "source_trajectory_id": metadata["source_trajectory_id"],
                "checkpoint_turn_id": metadata["checkpoint_turn_id"],
                "selection_score": metadata.get("selection_score"),
                "status": "selected_existing_build",
            }]
            attempts_path.write_text(
                json.dumps(attempts, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        attempts = (
            json.loads(attempts_path.read_text(encoding="utf-8"))
            if attempts_path.exists() else []
        )
        pipeline["t3_selection_attempt_count"] = len(attempts)
        pipeline["t3_selection_audit"] = str(attempts_path)
        (scenario_root / "pipeline_manifest.json").write_text(
            json.dumps(pipeline, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        summaries.append(pipeline)
        write_task_review(
            rollout_root / "tasks.md",
            scenario,
            instances,
            trajectories,
            branches,
            task_selection=pipeline.get("task_source_selection"),
        )
        refreshed += 1
    root_manifest_path = args.pipeline_output / "manifest.json"
    if root_manifest_path.exists():
        root_manifest = json.loads(root_manifest_path.read_text(encoding="utf-8"))
        root_manifest["scenarios"] = summaries
        root_manifest_path.write_text(
            json.dumps(root_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps({"refreshed": refreshed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
