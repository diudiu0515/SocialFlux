import json
import unittest
from pathlib import Path

from environment.delta_mapper import apply_semantic_deltas
from offline.rollout_builders import (
    build_t2_pairs,
    build_t3_candidates,
    retrieve_divergent_history_pairs,
)
from rollout.counterfactual import branch_counterfactuals
from rollout.runner import RolloutRunner
from tests.support import TextPolicy, environment_factory


SCENARIO = json.loads(
    Path("configs/scenarios/scenario_001/scenario_001.json").read_text(encoding="utf-8")
)


class CanonicalEnvironmentTest(unittest.TestCase):
    def test_delta_mapping_and_bounds(self):
        state, delta = apply_semantic_deltas(
            {"emotion": {"anger": 0}},
            {"emotion": {"anger": "strong_decrease"}},
        )
        self.assertEqual(state["emotion"]["anger"], 0)
        self.assertEqual(delta["emotion"]["anger"], 0)

    def test_rollout_has_private_transition_and_public_observation(self):
        trajectory = RolloutRunner(environment_factory(SCENARIO)).run(
            TextPolicy("model-a-seed-1", ["请解释现有证据。"]),
            max_turns=1,
        )
        turn = trajectory["turns"][0]
        self.assertNotIn("state_after", turn["observation"])
        self.assertIn("state_after", turn)
        self.assertNotIn("action_id", turn["policy_action"])
        self.assertEqual(
            trajectory["policy_provenance"]["sampling"]["seed"],
            1,
        )

    def test_same_environment_supports_different_free_form_model_policies(self):
        runner = RolloutRunner(environment_factory(SCENARIO))
        trajectories = runner.run_many([
            TextPolicy("model-a-seed-1", ["请解释贡献证据。"], seed=1),
            TextPolicy("model-b-seed-9", ["我会启动正式程序追究责任。"], model="model-b", seed=9),
        ], max_turns=1)
        self.assertEqual(trajectories[0]["initial_state"], trajectories[1]["initial_state"])
        self.assertNotEqual(
            trajectories[0]["turns"][0]["state_after"],
            trajectories[1]["turns"][0]["state_after"],
        )

    def test_t2_uses_natural_divergent_histories_and_exact_shared_observation(self):
        runner = RolloutRunner(environment_factory(SCENARIO))
        left = runner.run(
            TextPolicy("model-a-seed-1", ["请解释贡献证据。", "请继续解释证据。"]),
            max_turns=2,
        )
        right = runner.run(
            TextPolicy("model-b-seed-2", ["我要追究责任。", "我会启动正式程序。"], seed=2),
            max_turns=2,
        )
        candidates = retrieve_divergent_history_pairs([left, right])
        self.assertTrue(candidates)
        shared = {
            "current_response": "我们先确认彼此掌握的事实。",
            "observable_cues": [],
            "observable_expression": {},
            "media": [],
        }
        pairs = build_t2_pairs([left, right], lambda a, b: shared, 1)
        self.assertEqual(pairs[0]["input"]["shared_current_observation"], shared)
        self.assertTrue(pairs[0]["metadata"]["shared_observation_injected"])

    def test_t3_requires_free_form_actions_and_real_checkpoint(self):
        trajectory = RolloutRunner(environment_factory(SCENARIO)).run(
            TextPolicy("model-a-seed-1", ["请解释贡献证据。"]),
            max_turns=1,
        )
        turn = trajectory["turns"][0]
        checkpoint = {
            **turn,
            "trajectory_id": trajectory["trajectory_id"],
            "scenario_id": trajectory["scenario_id"],
        }
        actions = [{"text": "先核对记录。"}, {"text": "请第三方一起确认。"}]
        item = build_t3_candidates(checkpoint, actions, delayed_horizon=5)
        self.assertEqual(item["input"]["candidate_actions"], actions)
        with self.assertRaises(ValueError):
            build_t3_candidates(
                checkpoint,
                [{"text": "x", "action_id": "repair"}],
                delayed_horizon=5,
            )

    def test_local_intervention_restores_identical_checkpoint(self):
        trajectory = RolloutRunner(environment_factory(SCENARIO)).run(
            TextPolicy("model-a-seed-1", ["请先听我说明。"]),
            max_turns=1,
        )
        turn = trajectory["turns"][0]
        actions = [{"text": "请解释贡献证据。"}, {"text": "我会启动正式程序。"}]
        branches = branch_counterfactuals(
            environment_factory(SCENARIO),
            turn,
            actions,
            lambda: TextPolicy("continuation-model", ["我们继续核对事实。"]),
            delayed_horizon=5,
        )
        self.assertEqual(branches[0]["state_before"], branches[1]["state_before"])
        self.assertNotEqual(
            branches[0]["state_after_immediate"],
            branches[1]["state_after_immediate"],
        )


if __name__ == "__main__":
    unittest.main()
