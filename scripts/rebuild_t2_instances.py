#!/usr/bin/env python3
"""Rebuild T2 only from existing natural trajectories after quality rejection."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from offline.candidate_generation import ModelCandidateGenerator
from offline.rollout_builders import build_t2_pairs
from providers.factory import build_provider
from scripts.run_pipeline import (
    _load_existing_rollouts, _write_offline, load_rollout_config, load_scenario_records,
)
from scripts.task_docs import write_task_review


def rebuild_scenario_t2(scenario, scenario_path, pipeline_output, config):
    scenario_id = scenario["scenario_id"]
    scenario_output = Path(pipeline_output) / scenario_id
    instances_path = scenario_output / "offline" / "instances.jsonl"
    if not instances_path.exists():
        raise ValueError(f"missing pipeline instances for {scenario_id}")
    instances = [
        json.loads(line) for line in instances_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    trajectories = _load_existing_rollouts(Path(scenario_path).parent / "rollouts")
    construction = ModelCandidateGenerator(
        build_provider(config["construction"]["provider"]),
        config["construction"].get("sampling", {}),
    )
    limit = config.get("pilot_limits", {}).get(
        "t2", scenario.get("sampling_plan", {}).get("t2_max", 3)
    )
    rebuilt = build_t2_pairs(
        trajectories,
        construction.shared_observation,
        limit,
        scenario.get("target_state_ids", []),
        same_source_model=config.get("t2_pairing") == "within_source_model",
    )
    if len(rebuilt) != limit:
        raise ValueError(
            f"expected {limit} valid T2 pairs for {scenario_id}, got {len(rebuilt)}"
        )
    kept = [item for item in instances if item.get("task_type") != "T2_history_sensitive_merge"]
    updated = kept + rebuilt
    _write_offline(instances_path, updated)
    branch_path = scenario_output / "validation" / "local_action_interventions.json"
    branches = json.loads(branch_path.read_text(encoding="utf-8"))
    write_task_review(
        Path(scenario_path).parent / "rollouts" / "tasks.md",
        scenario, updated, trajectories, branches,
    )
    summary_path = scenario_output / "pipeline_manifest.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["t2"] = len(rebuilt)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"scenario_id": scenario_id, "t2": len(rebuilt)}


def rewrite_aggregate(pipeline_output):
    pipeline_output = Path(pipeline_output)
    instances = []
    for path in sorted(pipeline_output.glob("IA_PIPE_*/offline/instances.jsonl")):
        instances.extend(
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    instances.sort(key=lambda item: (item.get("story_id", ""), item.get("task_type", ""), item.get("instance_id", "")))
    _write_offline(pipeline_output / "instances.jsonl", instances)
    manifest_path = pipeline_output / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        by_id = {item["scenario_id"]: item for item in manifest.get("scenarios", [])}
        for scenario_id, summary in by_id.items():
            current_path = pipeline_output / scenario_id / "pipeline_manifest.json"
            if current_path.exists():
                by_id[scenario_id] = json.loads(current_path.read_text(encoding="utf-8"))
        summaries = sorted(by_id.values(), key=lambda item: item["scenario_id"] )
        manifest["scenarios"] = summaries
        manifest["totals"].update({
            "t1": sum(item["t1"] for item in summaries),
            "t2": sum(item["t2"] for item in summaries),
            "t3": sum(item["t3"] for item in summaries),
            "instances": len(instances),
        })
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario-id", dest="scenario_ids", action="append", required=True)
    parser.add_argument("--scenarios", type=Path, default=Path("configs/scenarios"))
    parser.add_argument("--pipeline-output", type=Path, default=Path("build/pipeline_v2"))
    parser.add_argument("--rollout-config", type=Path, required=True)
    args = parser.parse_args()
    config = load_rollout_config(args.rollout_config)
    records = {scenario["scenario_id"]: (path, scenario) for path, scenario in load_scenario_records(args.scenarios)}
    results = []
    for scenario_id in dict.fromkeys(args.scenario_ids):
        if scenario_id not in records:
            raise ValueError(f"unknown scenario ID: {scenario_id}")
        path, scenario = records[scenario_id]
        results.append(rebuild_scenario_t2(scenario, path, args.pipeline_output, config))
        rewrite_aggregate(args.pipeline_output)
    print(json.dumps({"rebuilt": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
