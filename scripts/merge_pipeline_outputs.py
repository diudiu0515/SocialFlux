#!/usr/bin/env python3
"""Merge independently generated pipeline shards into one canonical build."""

import argparse
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.leakage import assert_no_leaks


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def merge_pipeline_outputs(inputs, output):
    inputs = [Path(item) for item in inputs]
    output = Path(output)
    if not inputs:
        raise ValueError("at least one pipeline input is required")
    summaries = []
    configs = []
    instances = []
    seen = set()
    for source_root in inputs:
        manifest_path = source_root / "manifest.json"
        if manifest_path.exists():
            manifest = _read_json(manifest_path)
            if manifest.get("format") != "socialflux_pipeline_manifest_v2":
                raise ValueError(f"not a pipeline v2 shard: {manifest_path}")
            if manifest.get("trajectory_origin") != "free_form_model_interaction":
                raise ValueError(f"non-natural trajectory shard: {manifest_path}")
            shard_summaries = manifest.get("scenarios", [])
            if manifest.get("rollout_config"):
                configs.append(manifest["rollout_config"])
        else:
            shard_summaries = [
                _read_json(path)
                for path in sorted(source_root.glob("IA_PIPE_*/pipeline_manifest.json"))
            ]
            if not shard_summaries:
                raise ValueError(f"pipeline shard has no manifest or completed scenarios: {source_root}")
        for summary in shard_summaries:
            if summary.get("trajectory_origin") != "free_form_model_interaction":
                raise ValueError(f"non-natural scenario output in shard: {summary.get('scenario_id')}")
            scenario_id = summary["scenario_id"]
            if scenario_id in seen:
                raise ValueError(f"duplicate scenario across shards: {scenario_id}")
            seen.add(scenario_id)
            source_dir = source_root / scenario_id
            source_instances = source_dir / "offline" / "instances.jsonl"
            if not source_instances.exists():
                raise ValueError(f"missing scenario instances: {source_instances}")
            for line in source_instances.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    instance = json.loads(line)
                    assert_no_leaks(instance)
                    instances.append(instance)
            destination = output / scenario_id
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_dir, destination, dirs_exist_ok=True)
            summaries.append(summary)
    summaries.sort(key=lambda item: item["scenario_id"])
    instances.sort(key=lambda item: (item.get("story_id", ""), item.get("task_type", ""), item.get("instance_id", "")))
    output.mkdir(parents=True, exist_ok=True)
    with (output / "instances.jsonl").open("w", encoding="utf-8") as handle:
        for instance in instances:
            handle.write(json.dumps(instance, ensure_ascii=False) + "\n")
    result = {
        "format": "socialflux_pipeline_manifest_v2",
        "scenario_count": len(summaries),
        "trajectory_origin": "free_form_model_interaction",
        "totals": {
            "trajectories": sum(item["trajectory_count"] for item in summaries),
            "t1": sum(item["t1"] for item in summaries),
            "t2": sum(item["t2"] for item in summaries),
            "t3": sum(item["t3"] for item in summaries),
            "instances": len(instances),
        },
        "scenarios": summaries,
        "rollout_configs": configs,
        "ground_truth_status": "pending_human_annotation",
    }
    (output / "manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", dest="inputs", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, default=Path("build/pipeline_v2"))
    args = parser.parse_args()
    result = merge_pipeline_outputs(args.inputs, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
