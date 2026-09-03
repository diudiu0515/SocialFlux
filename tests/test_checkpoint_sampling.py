import json
from pathlib import Path
import unittest

from offline.rollout_builders import build_t1_checkpoints
from rollout.runner import RolloutRunner
from scripts.run_pipeline import _round_robin, _round_robin_turns
from tests.support import TextPolicy, environment_factory


SCENARIO = json.loads(
    Path("configs/scenarios/scenario_001/scenario_001.json").read_text(encoding="utf-8")
)


class CheckpointSamplingTest(unittest.TestCase):
    def test_t1_checkpoint_is_post_turn_and_chronologically_consistent(self):
        trajectory = RolloutRunner(environment_factory(SCENARIO)).run(
            TextPolicy("model-a", ["请解释证据。"]),
            max_turns=1,
        )
        turn = trajectory["turns"][0]
        instance = build_t1_checkpoints(trajectory)[0]
        self.assertEqual(
            instance["input"]["current_checkpoint"]["current_response"],
            turn["environment_response"],
        )
        self.assertEqual(
            instance["input"]["history"][-1]["environment_response"],
            turn["environment_response"],
        )
        self.assertEqual(turn["observation_after"]["turn_id"], 1)
        self.assertEqual(
            turn["observation"]["explicit_goal"],
            SCENARIO["evaluated_agent_role"]["explicit_goal"],
        )
        self.assertNotEqual(
            turn["observation"]["explicit_goal"],
            SCENARIO["environment_agent"]["explicit_goal"],
        )

    def test_round_robin_sampling_covers_trajectories_before_depth(self):
        self.assertEqual(_round_robin([["a1", "a2"], ["b1", "b2"]], 3), ["a1", "b1", "a2"])
        trajectories = [
            {"trajectory_id": "a", "turns": [{"turn_id": "t1"}, {"turn_id": "t2"}]},
            {"trajectory_id": "b", "turns": [{"turn_id": "t1"}, {"turn_id": "t2"}]},
        ]
        sampled = [
            (trajectory["trajectory_id"], turn["turn_id"])
            for trajectory, turn in _round_robin_turns(trajectories)
        ]
        self.assertEqual(sampled, [("a", "t1"), ("b", "t1"), ("a", "t2"), ("b", "t2")])


if __name__ == "__main__":
    unittest.main()
