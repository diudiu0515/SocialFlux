import json
from pathlib import Path
import unittest

from offline.rollout_builders import build_t1_checkpoints
from rollout.runner import RolloutRunner
from tests.support import TextPolicy, environment_factory


SCENARIO = json.loads(
    Path("data/gpt50/experiment/scenario/scenarios/scenario_001/scenario_001.json").read_text(encoding="utf-8")
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
        self.assertEqual(
            instance["input"]["target_character_id"],
            f"{SCENARIO['scenario_id']}_ENVIRONMENT_AGENT",
        )
        self.assertNotEqual(
            instance["input"]["target_character_id"],
            SCENARIO["evaluated_agent_role"]["character_id"],
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


if __name__ == "__main__":
    unittest.main()
