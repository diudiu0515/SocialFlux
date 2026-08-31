#!/usr/bin/env python3
"""Run the dependency-free Phase-A controlled validation on a scenario JSON."""

import argparse
import json
from pathlib import Path

from environment.env import StatefulEnvironment
from evaluation.environment_validity import validate_controlled_policies
from policies.controlled import ControlledPolicy
from rollout.logger import TrajectoryLogger
from rollout.runner import RolloutRunner


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", type=Path)
    parser.add_argument("--output", type=Path, default=Path("build/rollouts"))
    parser.add_argument("--turns", type=int, default=None)
    args = parser.parse_args()
    scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
    factory = lambda: StatefulEnvironment(scenario)
    runner = RolloutRunner(factory, TrajectoryLogger(args.output))
    action_effects = scenario.get("action_effects", {})
    policies = [
        ControlledPolicy(action_id, [{"action_id": action_id, "text": action_id}])
        for action_id in action_effects
    ]
    trajectories = runner.run_many(policies, max_turns=args.turns)
    print(json.dumps({
        "trajectory_ids": [item["trajectory_id"] for item in trajectories],
        "output": str(args.output),
        "policies": [item["policy_id"] for item in trajectories],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
