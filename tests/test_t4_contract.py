import json
import unittest
from copy import deepcopy
from pathlib import Path

from environment.observation import (
    PRIVATE_AUTHOR_FIELDS,
    PUBLIC_OBSERVATION_FIELDS,
    build_initial_policy_observation,
    build_public_evaluated_role,
)
from environment.prompts import build_appraisal_prompt
from environment.response_generator import ModelResponseGenerator
from evaluation.t4_evaluation import (
    T4_TARGET_TURNS,
    assert_t4_trajectory,
    public_t4_judge_packet,
)
from policies.model_policy import ModelPolicy, build_evaluated_role_card
from rollout.runner import RolloutRunner
from tests.support import TextPolicy, environment_factory


class T4ContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = json.loads(
            Path("data/gpt50/experiment/scenario/scenarios/scenario_001/scenario_001.json").read_text(
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
        self.assertNotIn("discussion_dimensions", observation["public_situation"])
        rendered = json.dumps(observation, ensure_ascii=False)
        self.assertNotIn(self.scenario["environment_agent"]["hidden_intention"], rendered)
        self.assertNotIn("initial_state", rendered)
        self.assertNotIn("meaningful_choice_space", rendered)
        for choice in self.scenario["narrative_design"]["meaningful_choice_space"]:
            self.assertNotIn(choice, rendered)
        self.assertNotIn("information_asymmetry", rendered)
        self.assertIn("hidden_intention", " ".join(PRIVATE_AUTHOR_FIELDS))

    def test_structured_role_card_uses_only_supplied_own_role_information(self):
        observation = build_initial_policy_observation(self.scenario)
        observation["role"].update({
            "known_experiences": ["上次没有及时说明进度"],
            "private_context": ["核心实验需要重跑"],
            "preferences": ["可以先交初步结果"],
            "boundaries": ["不能保证明天完成全部实验"],
            "personality_traits": ["在权威面前容易紧张"],
            "communication_tendencies": ["不喜欢直接争辩"],
        })
        card = build_evaluated_role_card(observation)
        self.assertEqual(
            card["current_task_goal"],
            observation["role"]["explicit_goal"],
        )
        self.assertEqual(
            card["known_experiences"], ["上次没有及时说明进度"]
        )
        self.assertEqual(card["private_context"], ["核心实验需要重跑"])
        self.assertEqual(
            card["preferences_and_boundaries"],
            ["可以先交初步结果", "不能保证明天完成全部实验"],
        )
        self.assertEqual(
            card["personality_and_expression"],
            ["在权威面前容易紧张", "不喜欢直接争辩"],
        )
        self.assertNotIn("hidden_intention", json.dumps(card, ensure_ascii=False))

    def test_t4_prompt_explains_goal_evidence_and_runtime_aid_boundaries(self):
        observation = build_initial_policy_observation(self.scenario)
        observation["role"]["private_context"] = ["仅被测角色知道的处境"]
        policy = ModelPolicy(
            "t4-contract-test",
            None,
            prompt_id="task_t4_action_v21",
            validation_profile="hard_only",
        )
        messages, _ = policy._build_request(observation)
        prompt = messages[1]["content"]
        self.assertIn("possible intention from observable evidence", prompt)
        self.assertIn("`explicit_goal`, which is the task objective", prompt)
        self.assertIn("there is no fixed number of challenges", prompt)
        self.assertIn("agreement about the next step", prompt)
        self.assertIn("dialogue-internal acts completed by speaking", prompt)
        self.assertIn("仅被测角色知道的处境", prompt)
        self.assertIn('"included_in_primary_t4": true', prompt)
        self.assertIn('"latest_open_proposal"', prompt)
        self.assertIn('"hidden_intention"', prompt)
        self.assertNotIn(
            self.scenario["environment_agent"]["hidden_intention"], prompt
        )

    def test_own_persona_reaches_rollout_and_t4_without_target_secrets(self):
        scenario = deepcopy(self.scenario)
        own_marker = "PUBLIC_OWN_PERSONA_MARKER_51C2"
        target_marker = "PRIVATE_TARGET_PERSONA_MARKER_8D40"
        scenario["evaluated_agent_role"]["persona"] = {
            "name": scenario["evaluated_agent_role"]["name"],
            "role": scenario["evaluated_agent_role"]["role"],
            "core_values": [own_marker, "共同负责"],
            "temperament": ["克制", "务实"],
            "communication_style": "先澄清再协商",
            "decision_style": "证据优先",
            "conflict_style": "直接说明边界",
            "boundaries": ["不把承诺当作已完成事实"],
        }
        scenario["environment_agent"]["persona"][
            "private_test_trait"
        ] = target_marker

        observation = build_initial_policy_observation(scenario)
        rendered_observation = json.dumps(observation, ensure_ascii=False)
        self.assertIn(own_marker, rendered_observation)
        self.assertNotIn(target_marker, rendered_observation)
        self.assertNotIn(
            scenario["environment_agent"]["hidden_intention"],
            rendered_observation,
        )
        card = build_evaluated_role_card(observation)
        self.assertIn(own_marker, card["self_persona"]["core_values"])

        for prompt_id in ("task_rollout_action_v1", "task_t4_action_v21"):
            policy = ModelPolicy(
                "persona-boundary-test", None, prompt_id=prompt_id,
                validation_profile="hard_only",
            )
            messages, _ = policy._build_request(observation)
            rendered_prompt = json.dumps(messages, ensure_ascii=False)
            self.assertIn(own_marker, rendered_prompt)
            self.assertNotIn(target_marker, rendered_prompt)
            self.assertNotIn(
                scenario["environment_agent"]["hidden_intention"],
                rendered_prompt,
            )

    def test_private_persona_reaches_environment_but_not_policy(self):
        scenario = deepcopy(self.scenario)
        marker = "PRIVATE_PERSONALITY_MARKER_7A91"
        public_evaluated_marker = "PUBLIC_EVALUATED_PERSONA_MARKER_94B1"
        evaluated_hidden_marker = "PRIVATE_EVALUATED_INTENTION_MARKER_2F70"
        role = scenario["evaluated_agent_role"]
        role["persona"] = {
            "name": role["name"],
            "role": role["role"],
            "core_values": [public_evaluated_marker, "可靠"],
            "temperament": ["克制", "耐心"],
            "communication_style": "先说明事实",
            "decision_style": "证据优先",
            "conflict_style": "明确边界",
            "boundaries": ["不虚构完成情况"],
        }
        role["hidden_intention"] = evaluated_hidden_marker
        evaluated_view = build_public_evaluated_role(role)
        scenario["environment_agent"]["persona"]["private_test_trait"] = marker
        observation = build_initial_policy_observation(scenario)
        self.assertNotIn(marker, json.dumps(observation, ensure_ascii=False))
        appraisal = build_appraisal_prompt(
            persona=scenario["environment_agent"]["persona"],
            background=scenario["background"],
            explicit_goal=scenario["environment_agent"]["explicit_goal"],
            hidden_intention=scenario["environment_agent"]["hidden_intention"],
            evaluated_agent=evaluated_view,
            previous_state=scenario["initial_state"],
            previous_dynamics=scenario["initial_dynamics"],
            memory={},
            action={"text": "请说明你的决定。"},
        )
        self.assertIn(marker, appraisal)
        self.assertIn(public_evaluated_marker, appraisal)
        self.assertNotIn(evaluated_hidden_marker, appraisal)
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
        rendered_environment_prompt = json.dumps(messages, ensure_ascii=False)
        self.assertIn(marker, rendered_environment_prompt)
        self.assertIn(public_evaluated_marker, rendered_environment_prompt)
        self.assertNotIn(evaluated_hidden_marker, rendered_environment_prompt)

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
