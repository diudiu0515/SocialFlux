#!/usr/bin/env python3
"""Rebuild T1 instances with task-specific source/checkpoint ranking only."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.leakage import assert_no_leaks
from evaluation.task_source_selection import rank_t1_checkpoints
from offline.rollout_builders import build_t1_checkpoints


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_jsonl(path, records):
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            assert_no_leaks(record)
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline-output", type=Path, required=True)
    args = parser.parse_args()
    all_instances = []
    rebuilt = 0
    for scenario_root in sorted(args.pipeline_output.glob("IA_PIPE_*")):
        manifest_path = scenario_root / "pipeline_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        selection = manifest["task_source_selection"]
        rollout_root = Path(manifest["rollout_bundle"])
        trajectories = {}
        rollout_manifest = json.loads((rollout_root / "manifest.json").read_text(encoding="utf-8"))
        for identifier in rollout_manifest["trajectory_ids"]:
            trajectories[identifier] = json.loads(
                (rollout_root / f"{identifier}.json").read_text(encoding="utf-8")
            )
        source_trajectories = [
            trajectories[identifier] for identifier in selection["t1_source_ids"]
        ]
        old_instances = read_jsonl(scenario_root / "offline" / "instances.jsonl")
        limit = sum(item["task_type"] == "T1_state_tracking" for item in old_instances)
        target_states = next(
            item["target_spec"].get("target_state_ids", [])
            for item in old_instances if item["task_type"] == "T1_state_tracking"
        )
        t1 = []
        for checkpoint in rank_t1_checkpoints(
            source_trajectories, selection["scores"]["t1"]
        )[:limit]:
            candidate = build_t1_checkpoints(
                checkpoint["trajectory"], target_states
            )[checkpoint["turn_index"]]
            candidate["metadata"]["selection_method"] = (
                "task_specific_quality_plus_history_depth_and_state_information"
            )
            t1.append(candidate)
        others = [item for item in old_instances if item["task_type"] != "T1_state_tracking"]
        instances = t1 + others
        write_jsonl(scenario_root / "offline" / "instances.jsonl", instances)
        manifest["t1"] = len(t1)
        manifest["t1_checkpoint_selection"] = {
            "method": "source_quality_0.75_history_depth_0.15_state_information_0.10",
            "instance_ids": [item["instance_id"] for item in t1],
            "private_selection_features_exposed": False,
        }
        selected = manifest["task_source_selection"].setdefault("selected", {})
        selected["t1"] = [
            {
                "instance_id": item["instance_id"],
                "source_trajectory_id": item["metadata"]["source_trajectory_id"],
                "checkpoint_turn_id": item["input"]["history"][-1]["turn_id"],
            }
            for item in t1
        ]
        selected["t2"] = [
            {
                "instance_id": item["instance_id"],
                "source_trajectory_ids": item["metadata"]["source_trajectory_ids"],
                "history_turn_count": len(item["input"]["history_a"]),
            }
            for item in others
            if item["task_type"] == "T2_history_sensitive_merge"
        ]
        selected["t3"] = [
            {
                "instance_id": item["instance_id"],
                "source_trajectory_id": item["metadata"]["source_trajectory_id"],
                "checkpoint_turn_id": item["metadata"]["checkpoint_turn_id"],
            }
            for item in others
            if item["task_type"] == "T3_counterfactual_choice_effect"
        ]
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        all_instances.extend(instances)
        rebuilt += 1
    all_instances.sort(key=lambda item: (item["story_id"], item["task_type"], item["instance_id"]))
    write_jsonl(args.pipeline_output / "instances.jsonl", all_instances)
    print(json.dumps({"rebuilt_scenarios": rebuilt, "instances": len(all_instances)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
