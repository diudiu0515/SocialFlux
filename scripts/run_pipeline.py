#!/usr/bin/env python3
"""Build the scenario -> rollout -> T1/T2/T3 candidate pipeline."""

import argparse
import json
from pathlib import Path

from environment.env import StatefulEnvironment
from evaluation.leakage import assert_no_leaks
from offline.rollout_builders import build_t1_checkpoints, build_t2_pairs, build_t3_candidates
from policies.controlled import ControlledPolicy
from rollout.counterfactual import branch_counterfactuals
from rollout.logger import TrajectoryLogger
from rollout.manifest import write_manifest
from rollout.runner import RolloutRunner
from schemas.validate import validate_scenario
from scripts.scenario_docs import assert_document_current, assert_manifest_current


def load_scenarios(directory):
    assert_manifest_current(directory)
    scenarios = []
    for path in sorted(Path(directory).glob("scenario_*.json")):
        assert_document_current(path)
        scenarios.append(json.loads(path.read_text(encoding="utf-8")))
    return scenarios


def run_scenario(scenario, output_dir, max_turns=None):
    validate_scenario(scenario)
    scenario_id = scenario["scenario_id"]
    scenario_output = Path(output_dir) / scenario_id
    logger = TrajectoryLogger(scenario_output / "rollouts")
    factory = lambda: StatefulEnvironment(scenario)
    policies = [
        ControlledPolicy(
            f"{scenario_id}__{action_id}",
            [{"action_id": action_id, "text": action_id}],
        )
        for action_id in scenario["action_effects"]
    ]
    runner = RolloutRunner(factory, logger=logger)
    trajectories = runner.run_many(policies, max_turns=max_turns)
    t1_candidates = []
    for trajectory in trajectories:
        t1_candidates.extend(build_t1_checkpoints(trajectory, scenario.get("target_state_ids", [])))
    t1 = t1_candidates[: scenario.get("sampling_plan", {}).get("t1_max", 5)]
    t2_candidates = build_t2_pairs(trajectories)
    t2 = t2_candidates[: scenario.get("sampling_plan", {}).get("t2_max", 3)]
    t3, branches = [], []
    candidates = [{"action_id": action_id, "text": action_id}
                  for action_id in scenario["action_effects"]]
    checkpoint_limit = scenario.get("sampling_plan", {}).get("t3_max", 4)
    if trajectories and trajectories[0]["turns"]:
        source = trajectories[0]
        for index, turn in enumerate(source["turns"][:checkpoint_limit]):
            checkpoint = dict(turn)
            checkpoint["trajectory_id"] = source["trajectory_id"]
            checkpoint["scenario_id"] = scenario_id
            t3.append(build_t3_candidates(
                checkpoint, candidates, scenario.get("t3_delayed_horizon", 5),
                scenario.get("target_state_ids", []),
            ))
            branches.extend(branch_counterfactuals(
                factory, source["turns"][:index], candidates,
                [candidates[0]], scenario.get("t3_delayed_horizon", 5),
            ))
    for collection in (t1, t2, t3):
        for record in collection:
            assert_no_leaks(record)
    (scenario_output / "offline").mkdir(parents=True, exist_ok=True)
    with (scenario_output / "offline" / "instances.jsonl").open("w", encoding="utf-8") as handle:
        for record in t1 + t2 + t3:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    (scenario_output / "validation").mkdir(parents=True, exist_ok=True)
    (scenario_output / "validation" / "counterfactual_effects.json").write_text(
        json.dumps(branches, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest = write_manifest(scenario_output / "rollout_manifest.json", trajectories, {
        "t1_candidates": len(t1), "t2_candidates": len(t2), "t3_candidates": len(t3),
        "delayed_horizon": scenario.get("t3_delayed_horizon", 5),
    })
    manifest.update({"scenario_id": scenario_id, "t1": len(t1), "t2": len(t2), "t3": len(t3)})
    (scenario_output / "pipeline_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", type=Path, default=Path("configs/scenarios"))
    parser.add_argument("--output", type=Path, default=Path("build/pipeline_v1"))
    parser.add_argument("--turns", type=int, default=None)
    args = parser.parse_args()
    summaries = [run_scenario(scenario, args.output, args.turns) for scenario in load_scenarios(args.scenarios)]
    total = {key: sum(item.get(key, 0) for item in summaries) for key in ("t1", "t2", "t3")}
    result = {"format": "emotree_pipeline_manifest_v1", "scenario_count": len(summaries),
              "totals": total, "scenarios": summaries,
              "ground_truth_status": "pending_human_annotation"}
    args.output.mkdir(parents=True, exist_ok=True)
    instances = []
    for summary in summaries:
        source = args.output / summary["scenario_id"] / "offline" / "instances.jsonl"
        if source.exists():
            instances.extend(json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line)
    with (args.output / "instances.jsonl").open("w", encoding="utf-8") as handle:
        for instance in instances:
            handle.write(json.dumps(instance, ensure_ascii=False) + "\n")
    result["totals"]["instances"] = len(instances)
    (args.output / "manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
