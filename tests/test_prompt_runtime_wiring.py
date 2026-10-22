import json
from pathlib import Path
import unittest

from environment.video_requests import (
    TALKING_HEAD_PROMPT_ID,
    build_video_request,
)
from evaluation.t4_configuration import load_t4_config
from prompts.loader import render_prompt
from rollout.configuration import load_rollout_config
from tasks.T1.answering import answer_prompt as t1_prompt
from tasks.T2.answering import answer_prompt as t2_prompt
from tasks.T2.branch_authoring import branch_prompt
from tasks.T2.spec_authoring import spec_prompt
from tasks.T3.action_authoring import action_prompt as t3_action_prompt
from tasks.T3.answering import answer_prompt as t3_prompt
from tasks.extraction import extraction_prompt


class PromptRuntimeWiringTest(unittest.TestCase):
    def test_task_prompt_callers_render_manifest_prompts(self):
        scenario = {
            "scenario_id": "s1",
            "title": "测试",
            "background": "公开背景",
            "evaluated_agent_role": {
                "name": "甲", "role": "协调者", "explicit_goal": "达成安排",
            },
            "environment_agent": {
                "persona": {"name": "乙", "role": "合作者"},
            },
            "target_state_ids": ["relationship.trust"],
        }
        trajectory = {
            "turns": [{
                "turn_id": "t1",
                "policy_action": {"text": "我们先核对事实。"},
                "environment_response": "可以。",
            }],
        }
        rendered = extraction_prompt(scenario, trajectory)
        self.assertIn("T1/T3 Checkpoint Extraction v1", rendered)

        t1_instance = {
            "instance_id": "t1-i",
            "input": {"history": [{"turn_id": "t1"}]},
            "target_spec": {"target_state_ids": ["relationship.trust"]},
        }
        self.assertIn(
            "T1 Latent Social State Estimation v1",
            t1_prompt(t1_instance),
        )

        t2_instance = {
            "instance_id": "t2-i",
            "input": {
                "history_a": [{
                    "turn_id": "t1",
                    "environment_character": "我需要再确认。",
                }],
                "history_b": [{
                    "turn_id": "t1",
                    "environment_character": "我需要再确认。",
                }],
            },
            "target_spec": {"candidate_state_ids": ["relationship.trust"]},
        }
        self.assertIn(
            "T2 History-Conditioned State Comparison v1",
            t2_prompt(t2_instance),
        )
        windows = [{
            "fork_turn_id": "t1",
            "ending_turn_id": "t2",
            "prefix_turn_count": 1,
            "adapted_turn_count": 1,
        }]
        self.assertIn(
            "T2 Controlled Adaptation Specification v1",
            spec_prompt(scenario, trajectory, windows),
        )
        spec = {
            "adaptation_point": "改写分歧处理经历",
            "source_anchor_evidence": [{"turn_id": "t1", "speaker": "evaluated_agent"}],
            "history_b_direction": "采取不同澄清策略",
            "protected_facts": ["公开背景"],
        }
        source_tail = [{
            "turn_id": "t1",
            "evaluated_agent": "我们先核对事实。",
            "environment_character": "可以。",
        }]
        self.assertIn(
            "T2 Controlled History-B Authoring v1",
            branch_prompt(
                spec, scenario, [], source_tail,
                {"evaluated_agent": "继续。", "environment_character": "好。"},
            ),
        )


        checkpoint = {"history": [], "current_observation": {"turn_id": "t1"}}
        self.assertIn(
            "T3 Candidate Action Authoring v1",
            t3_action_prompt(checkpoint),
        )
        t3_instance = {
            "instance_id": "t3-i",
            "input": {
                "history": [{"turn_id": "t1"}],
                "current_observation": {"turn_id": "t1"},
                "candidate_actions": [{"text": "先澄清。"}, {"text": "暂缓。"}],
            },
            "target_spec": {"target_state_ids": ["relationship.trust"]},
        }
        self.assertIn(
            "T3 Counterfactual State Transition Prediction v1",
            t3_prompt(t3_instance),
        )

    def test_gate4_prompt_has_a_real_shared_render_path(self):
        packet = {
            "task_type": "T1_state_tracking",
            "language": "zh",
            "modality": "text",
            "input": {"history": []},
            "target_spec": {"target_state_ids": ["relationship.trust"]},
        }
        rendered = render_prompt("instance_quality_judge_v2", packet)
        self.assertIn("Blinded Instance Quality Judge v2", rendered)
        self.assertNotIn("{{payload_json}}", rendered)

    def test_t4_is_distinct_from_offline_rollout_in_both_branches(self):
        offline_prompt_ids = set()
        for path in (
            "configs/claude150_v1/rollout.json",
            "configs/gpt50_experiment/rollout.json",
        ):
            rollout = load_rollout_config(path)
            offline_prompt_ids.add(rollout["policies"][0]["prompt_id"])
        self.assertEqual(offline_prompt_ids, {"task_rollout_action_v1"})

        claude = load_t4_config("configs/claude150_v1/t4.json")
        gpt = load_t4_config("configs/gpt50_experiment/t4.json")
        self.assertEqual(
            {
                claude["evaluated_model"]["prompt_id"],
                gpt["evaluated_model"]["prompt_id"],
            },
            {"task_t4_action_v21"},
        )
        self.assertEqual(gpt["evaluated_model"]["provider"]["model"], "gpt-6-astra")
        self.assertEqual(gpt["judge"]["provider"]["model"], "gpt-6-astra")
        self.assertEqual(gpt["environment"]["provider"]["model"], "claude-fable-5")
        self.assertEqual(
            gpt["environment"]["response_provider"]["model"],
            "claude-fable-5",
        )

    def test_multimodal_config_and_prompt_are_shared(self):
        shared = json.loads(
            Path("configs/multimodal_generation.json").read_text(encoding="utf-8")
        )
        policies = []
        for path in (
            "configs/claude150_v1/rollout.state_v3.json",
            "configs/gpt50_experiment/rollout.state_v3.json",
        ):
            rollout = load_rollout_config(path)
            policies.append(rollout["environment"]["multimodal_trigger_policy"])
        self.assertEqual(policies, [shared["online"], shared["online"]])

        request = build_video_request(
            {
                "environment_agent": {
                    "persona": {"name": "Alex", "role": "collaborator"},
                },
            },
            "We can continue this conversation.",
            {
                "facial_expression": "restrained",
                "gaze": "natural eye contact",
                "speech_style": "normal pace",
                "prosody": "even",
                "behavioral_cues": ["subtle nod"],
            },
        )
        self.assertEqual(request["prompt_id"], TALKING_HEAD_PROMPT_ID)
        self.assertEqual(shared["prompt_id"], TALKING_HEAD_PROMPT_ID)
        self.assertIn("We can continue this conversation.", request["prompt"])


if __name__ == "__main__":
    unittest.main()
