import json
import unittest
from copy import deepcopy
from pathlib import Path

from environment.observation import (
    PRIVATE_AUTHOR_FIELDS,
    PUBLIC_OBSERVATION_FIELDS,
    build_initial_policy_observation,
)
from environment.prompts import build_appraisal_prompt
from environment.response_generator import ModelResponseGenerator
from evaluation.t4_evaluation import (
    T4_TARGET_TURNS,
    assert_t4_trajectory,
    public_t4_judge_packet,
)
from rollout.runner import RolloutRunner
from tests.support import TextPolicy, environment_factory


class T4ContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = json.loads(
            Path("configs/scenarios/scenario_001/scenario_001.json").read_text(
                encoding="utf-8"
            )
        )

    def test_public_role_card_has_identity_and_goal_but_no_private_target_data(self):
        observation = build_initial_policy_observation(self.scenario)
        self.assertEqual(tuple(observation), PUBLIC_OBSERVATION_FIELDS)
        self.assertTrue(observation["role"]["role"])
        self.assertTrue(observation["role"]["explicit_goal"])
        self.assertEqual(
            observation["public_situation"]["relevant_history"],
            self.scenario["narrative_design"]["relevant_history"],
        )
        self.assertEqual(
            observation["public_situation"]["discussion_dimensions"],
            self.scenario["narrative_design"]["meaningful_choice_space"],
        )
        rendered = json.dumps(observation, ensure_ascii=False)
        self.assertNotIn(self.scenario["environment_agent"]["hidden_intention"], rendered)
        self.assertNotIn("initial_state", rendered)
        self.assertNotIn("meaningful_choice_space", rendered)
        self.assertNotIn("information_asymmetry", rendered)
        self.assertIn("hidden_intention", " ".join(PRIVATE_AUTHOR_FIELDS))


    def test_private_persona_reaches_environment_but_not_policy(self):
        scenario = deepcopy(self.scenario)
        marker = "PRIVATE_PERSONALITY_MARKER_7A91"
        scenario["environment_agent"]["persona"]["private_test_trait"] = marker
        observation = build_initial_policy_observation(scenario)
        self.assertNotIn(marker, json.dumps(observation, ensure_ascii=False))
        appraisal = build_appraisal_prompt(
            persona=scenario["environment_agent"]["persona"],
            background=scenario["background"],
            explicit_goal=scenario["environment_agent"]["explicit_goal"],
            hidden_intention=scenario["environment_agent"]["hidden_intention"],
            previous_state=scenario["initial_state"],
            previous_dynamics=scenario["initial_dynamics"],
            memory={},
            action={"text": "请说明你的决定。"},
        )
        self.assertIn(marker, appraisal)
        generator = ModelResponseGenerator(
            object(), prompt_id="environment_response_v25",
            validation_profile="hard_only",
        )
        _, messages = generator._build_request({
            "scenario": {
                "background": scenario["background"],
                "environment_agent": scenario["environment_agent"],
                "evaluated_agent_role": scenario["evaluated_agent_role"],
            },
            "history": [],
            "action": {"text": "请说明你的决定。"},
            "turn_id": 1,
        })
        self.assertIn(marker, json.dumps(messages, ensure_ascii=False))

    def test_t4_accepts_natural_ending_before_maximum_horizon(self):
        actions = [f"这是第{index}轮的新行动。" for index in range(1, 21)]
        trajectory = RolloutRunner(environment_factory(self.scenario)).run(
            TextPolicy("evaluated-test-model", actions),
            max_turns=T4_TARGET_TURNS,
        )
        assert_t4_trajectory(trajectory)
        self.assertGreaterEqual(len(trajectory["turns"]), 1)
        self.assertLessEqual(len(trajectory["turns"]), 20)
        self.assertEqual(trajectory["ending"]["turn_id"], len(trajectory["turns"]))
        self.assertIn(trajectory["ending"]["reason"], {"natural_completion", "max_turns"})

    def test_judge_packet_is_observable_and_complete(self):
        actions = [f"我在第{index}轮提出一个新信息。" for index in range(1, 21)]
        trajectory = RolloutRunner(environment_factory(self.scenario)).run(
            TextPolicy("evaluated-test-model", actions),
            max_turns=T4_TARGET_TURNS,
        )
        packet = public_t4_judge_packet(trajectory, self.scenario)
        self.assertEqual(packet["horizon_max_turns"], 20)
        self.assertEqual(packet["observed_turns"], len(trajectory["turns"]))
        self.assertEqual(len(packet["observable_trajectory"]), len(trajectory["turns"]))
        rendered = json.dumps(packet, ensure_ascii=False)
        self.assertNotIn(self.scenario["environment_agent"]["hidden_intention"], rendered)
        self.assertNotIn("state_before", rendered)


if __name__ == "__main__":
    unittest.main()
