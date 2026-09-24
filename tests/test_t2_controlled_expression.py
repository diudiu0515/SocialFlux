import json
import unittest
from copy import deepcopy
from pathlib import Path

from environment.env import StatefulEnvironment
from environment.response_generator import ModelResponseGenerator
from scripts.build_t2_expression_dev_pairs import (
    supported_t2_candidates,
    validate_answer,
)
from tests.support import ContextualTestUpdater


SCENARIO = json.loads(
    Path("data/gpt50/experiment/scenario/scenarios/scenario_001/scenario_001.json").read_text(
        encoding="utf-8"
    )
)

BEHAVIOR = {
    "facial_expression": "短暂微笑，神情仍克制",
    "gaze": "保持稳定注视",
    "speech_style": "措辞礼貌而简短",
    "prosody": "语速平稳，句尾略收紧",
    "behavioral_cues": ["回答前短暂停顿"],
}


class ExpressionResponseDouble:
    horizon_mode = "fixed_20"
    provenance = {"provider": "test-double", "prompt_id": "environment_response_v25"}

    def generate(self, context):
        controlled = context["controlled_observation"]
        return {
            "response_text": controlled["current_response"],
            "expression_intent": "在不暴露保留意见的情况下维持当前合作。",
            "observable_behavior": deepcopy(controlled["observable_expression"]),
            "ledger_events": [],
            "consequential_claims": [],
            "reply_obligation": None,
            "ledger_event_normalizations": [],
        }


class T2ControlledExpressionTest(unittest.TestCase):
    def _context(self, controlled):
        return {
            "scenario": SCENARIO,
            "action": {"text": "我建议先按现有安排推进。"},
            "history": [],
            "interaction_ledger": {},
            "longitudinal_context": {},
            "turn_id": 3,
            "controlled_observation": controlled,
        }

    def test_v25_keeps_intent_private_and_copies_controlled_ending_exactly(self):
        controlled = {
            "current_response": "好，我们先按这个安排推进。",
            "observable_expression": deepcopy(BEHAVIOR),
            "media": [],
        }
        generator = ModelResponseGenerator(
            None,
            prompt_id="environment_response_v25",
            validation_profile="hard_only",
            horizon_mode="natural_max_20",
        )
        normalized = generator._validate_structured_response(
            {
                "response_text": controlled["current_response"],
                "expression_intent": "为维持合作而克制尚未解决的不满。",
                "observable_behavior": deepcopy(BEHAVIOR),
                "ledger_events": [],
            "consequential_claims": [],
            "reply_obligation": None,
            },
            self._context(controlled),
        )
        self.assertEqual(normalized["response_text"], controlled["current_response"])
        self.assertEqual(normalized["observable_behavior"], BEHAVIOR)
        self.assertIn("克制", normalized["expression_intent"])

    def test_v25_deterministically_binds_controlled_visible_fields(self):
        controlled = {
            "current_response": "好，我们先按这个安排推进。",
            "observable_expression": deepcopy(BEHAVIOR),
            "media": [],
        }
        changed = deepcopy(BEHAVIOR)
        changed["prosody"] = "语气轻快"
        generator = ModelResponseGenerator(
            None,
            prompt_id="environment_response_v25",
            validation_profile="hard_only",
            horizon_mode="natural_max_20",
        )
        normalized = generator._validate_structured_response(
            {
                "response_text": "模型生成了近似但不同的台词。",
                "expression_intent": "真诚接受当前安排。",
                "observable_behavior": changed,
                "ledger_events": [],
            "consequential_claims": [],
            "reply_obligation": None,
            },
            self._context(controlled),
        )
        self.assertEqual(normalized["response_text"], controlled["current_response"])
        self.assertEqual(
            normalized["observable_behavior"], controlled["observable_expression"]
        )

    def test_environment_logs_private_intent_but_exposes_only_behavior(self):
        controlled = {
            "current_response": "好，我们先按这个安排推进。",
            "observable_expression": deepcopy(BEHAVIOR),
            "media": [],
        }
        environment = StatefulEnvironment(
            deepcopy(SCENARIO),
            state_updater=ContextualTestUpdater(SCENARIO),
            response_generator=ExpressionResponseDouble(),
        )
        environment.reset(episode_id="t2-controlled-test")
        observation, log = environment.step(
            {"text": "我建议先按现有安排推进。"},
            controlled_observation=controlled,
        )
        self.assertEqual(observation["current_response"], controlled["current_response"])
        self.assertEqual(observation["observable_expression"], BEHAVIOR)
        self.assertNotIn("expression_intent", observation)
        self.assertIn("维持当前合作", log["response_expression_intent"])
        self.assertEqual(log["response_observable_behavior"], BEHAVIOR)

    def test_controlled_retry_never_requests_a_different_response_text(self):
        guidance = ModelResponseGenerator._structured_retry_guidance({
            "controlled_observation": {
                "current_response": "好，我们先按这个安排推进。",
                "observable_expression": deepcopy(BEHAVIOR),
            }
        })
        self.assertIn("byte-for-byte", guidance)
        self.assertIn("Do not paraphrase", guidance)
        self.assertNotIn("materially different response_text", guidance)

    def test_hard_only_rejects_exact_cross_speaker_copy(self):
        generator = ModelResponseGenerator(
            None,
            prompt_id="environment_response_v25",
            validation_profile="hard_only",
            horizon_mode="natural_max_20",
        )
        utterance = "我们可以接受暂定表述，但必须在初报中明确列出技术复核的优先级。"
        passed, reason = generator._validate_candidate_for_profile(
            utterance,
            {
                "action": {"text": utterance},
                "interaction_ledger": {},
                "longitudinal_context": {"segment": {}, "public_timeline": []},
                "scenario": {},
                "history": [],
            },
        )
        self.assertFalse(passed)
        self.assertIn("verbatim echo", reason)


if __name__ == "__main__":
    unittest.main()
