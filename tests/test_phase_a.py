import unittest

from environment.delta_mapper import apply_semantic_deltas
from environment.env import StatefulEnvironment
from evaluation.environment_validity import validate_controlled_policies
from offline.rollout_builders import build_t2_pairs, build_t3_candidates
from policies.controlled import ControlledPolicy
from rollout.runner import RolloutRunner


SCENARIO = {
    "scenario_id": "mvp_001",
    "background": "A student asks an advisor to revisit a decision.",
    "environment_agent": {
        "persona": {"name": "Advisor", "patience": 0.6},
        "explicit_goal": "keep the work moving",
        "hidden_intention": "avoid admitting a mistake",
    },
    "evaluated_agent_role": {"character_id": "STUDENT", "name": "Student"},
    "initial_state": {
        "emotion": {"anger": 3, "anxiety": 4},
        "relationship": {"trust": 7, "hostility": 2},
    },
    "initial_dynamics": {"escalation_risk": 2, "negotiation_open": 5},
    "action_effects": {
        "repair": {
            "state_delta": {
                "emotion": {"anger": "moderate_decrease", "anxiety": "mild_decrease"},
                "relationship": {"trust": "mild_increase", "hostility": "moderate_decrease"},
            },
            "interaction_dynamics_delta": {
                "escalation_risk": "moderate_decrease", "negotiation_open": "mild_increase"
            },
        },
        "escalate": {
            "state_delta": {
                "emotion": {"anger": "strong_increase", "anxiety": "mild_increase"},
                "relationship": {"trust": "strong_decrease", "hostility": "strong_increase"},
            },
            "interaction_dynamics_delta": {
                "escalation_risk": "strong_increase", "negotiation_open": "moderate_decrease"
            },
        },
    },
    "response_templates": {"default": "我会根据当前情况继续回应。"},
    "max_turns": 5,
}


class PhaseATest(unittest.TestCase):
    def test_delta_mapping_and_bounds(self):
        state, delta = apply_semantic_deltas(
            {"emotion": {"anger": 0}},
            {"emotion": {"anger": "strong_decrease"}},
        )
        self.assertEqual(state["emotion"]["anger"], 0)
        self.assertEqual(delta["emotion"]["anger"], 0)

    def test_rollout_has_private_transition_and_public_observation(self):
        runner = RolloutRunner(lambda: StatefulEnvironment(SCENARIO))
        trajectory = runner.run(
            ControlledPolicy("repair", [{"action_id": "repair", "text": "repair"}]),
            max_turns=1,
        )
        turn = trajectory["turns"][0]
        self.assertNotIn("state_after", turn["observation"])
        self.assertIn("state_after", turn)
        self.assertEqual(turn["state_after"]["emotion"]["anger"], 1)

    def test_same_frozen_initialization_for_policies(self):
        runner = RolloutRunner(lambda: StatefulEnvironment(SCENARIO))
        trajectories = runner.run_many([
            ControlledPolicy("repair", [{"action_id": "repair", "text": "repair"}]),
            ControlledPolicy("escalate", [{"action_id": "escalate", "text": "escalate"}]),
        ], max_turns=1)
        self.assertEqual(trajectories[0]["initial_state"], trajectories[1]["initial_state"])
        self.assertEqual(trajectories[0]["initial_dynamics"], trajectories[1]["initial_dynamics"])


    def test_t2_requires_different_public_history(self):
        runner = RolloutRunner(lambda: StatefulEnvironment(SCENARIO))
        left = runner.run(
            ControlledPolicy("repair", [{"action_id": "repair", "text": "same"}]),
            max_turns=1,
        )
        right = runner.run(
            ControlledPolicy("escalate", [{"action_id": "escalate", "text": "different"}]),
            max_turns=1,
        )
        left["turns"][0]["observation"]["current_response"] = "shared"
        right["turns"][0]["observation"]["current_response"] = "shared"
        pairs = build_t2_pairs([left, right])
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["input"]["shared_current_observation"]["current_response"], "shared")

    def test_t3_horizon_gate(self):
        with self.assertRaises(ValueError):
            build_t3_candidates(
                {"trajectory_id": "x", "turn_id": 1, "observation": {}},
                [],
                delayed_horizon=4,
            )
        item = build_t3_candidates(
            {"trajectory_id": "x", "turn_id": 1, "observation": {}},
            [],
            delayed_horizon=5,
        )
        self.assertEqual(item["target_spec"]["delayed_horizon"], 5)

    def test_validation_scorecard(self):
        runner = RolloutRunner(lambda: StatefulEnvironment(SCENARIO))
        trajectory = runner.run(
            ControlledPolicy("escalate", [{"action_id": "escalate", "text": "escalate"}]),
            max_turns=1,
        )
        report = validate_controlled_policies(
            [trajectory], {"escalate": {"emotion.anger": 1}}
        )
        self.assertTrue(report["escalate"]["passed"])


if __name__ == "__main__":
    unittest.main()
