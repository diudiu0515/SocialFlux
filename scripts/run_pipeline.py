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
from scripts.scenario_docs import (
    assert_document_current,
    assert_manifest_current,
    discover_scenario_paths,
)


def load_scenario_records(directory):
    directory = Path(directory)
    assert_manifest_current(directory)
    records = []
    for path in discover_scenario_paths(directory):
        assert_document_current(path)
        records.append((path, json.loads(path.read_text(encoding="utf-8"))))
    return records


def load_scenarios(directory):
    return [scenario for _, scenario in load_scenario_records(directory)]


def _prepare_rollout_directory(path):
    """Remove only known generated rollout artifacts before rebuilding."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    for candidate in path.glob("*.json"):
        candidate.unlink()
    dialogue = path / "dialogues.md"
    if dialogue.exists():
        dialogue.unlink()
    return path


def _write_dialogues(path, scenario, trajectories):
    lines = [
        f"# {scenario.get('title', scenario['scenario_id'])} — Rollout Dialogues",
        "",
        "> Generated private research artifact. Regenerate with `python -m scripts.run_pipeline`; do not edit manually.",
        "",
        f"- Scenario ID: `{scenario['scenario_id']}`",
        f"- Trajectories: `{len(trajectories)}`",
        "",
    ]
    for trajectory in trajectories:
        action_id = trajectory["policy_id"].split("__")[-1]
        lines.extend([
            f"## {action_id} — `{trajectory['policy_id']}`",
            "",
        ])
        for turn in trajectory["turns"]:
            action = turn.get("policy_action", {})
            lines.extend([
                f"### {turn['turn_id']}",
                "",
                f"**Evaluated agent:** {action.get('text', action.get('action_id', ''))}",
                "",
                f"**Environment agent:** {turn.get('environment_response', '')}",
                "",
            ])
            expression = turn.get("observable_expression", {})
            if expression:
                lines.extend([
                    f"_Expression: {expression.get('facial_expression', '—')}; "
                    f"gaze: {expression.get('gaze', '—')}; "
                    f"prosody: {expression.get('prosody', '—')}._",
                    "",
                ])
            for event in turn.get("trigger_events", []):
                lines.extend([
                    f"_Talking Head trigger: `{event.get('trigger_id', 'unknown')}`._",
                    "",
                ])
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def run_scenario(scenario, output_dir, scenario_path, max_turns=None):
    validate_scenario(scenario)
    scenario_id = scenario["scenario_id"]
    scenario_output = Path(output_dir) / scenario_id
    rollout_dir = _prepare_rollout_directory(Path(scenario_path).parent / "rollouts")
    logger = TrajectoryLogger(rollout_dir)
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
    _write_dialogues(rollout_dir / "dialogues.md", scenario, trajectories)

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

    manifest = write_manifest(rollout_dir / "manifest.json", trajectories, {
        "t1_candidates": len(t1),
        "t2_candidates": len(t2),
        "t3_candidates": len(t3),
        "delayed_horizon": scenario.get("t3_delayed_horizon", 5),
        "dialogues": "dialogues.md",
    })
    bundle_path = Path("configs/scenarios") / Path(scenario_path).parent.name
    manifest.update({
        "scenario_id": scenario_id,
        "scenario_bundle": bundle_path.as_posix(),
        "rollout_bundle": (bundle_path / "rollouts").as_posix(),
        "t1": len(t1),
        "t2": len(t2),
        "t3": len(t3),
    })
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
    summaries = [
        run_scenario(scenario, args.output, path, args.turns)
        for path, scenario in load_scenario_records(args.scenarios)
    ]
    total = {key: sum(item.get(key, 0) for item in summaries) for key in ("t1", "t2", "t3")}
    result = {
        "format": "emotree_pipeline_manifest_v1",
        "scenario_count": len(summaries),
        "totals": total,
        "scenarios": summaries,
        "ground_truth_status": "pending_human_annotation",
    }
    args.output.mkdir(parents=True, exist_ok=True)
    instances = []
    for summary in summaries:
        source = args.output / summary["scenario_id"] / "offline" / "instances.jsonl"
        if source.exists():
            instances.extend(
                json.loads(line)
                for line in source.read_text(encoding="utf-8").splitlines()
                if line
            )
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
