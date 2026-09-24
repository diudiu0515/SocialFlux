import json
import unittest
from pathlib import Path

from environment.appraisal import _validate_appraisal
from environment.ledger_events import validate_semantic_ledger_events
from environment.response_generator import ModelResponseGenerator


SCENARIO = json.loads(Path(
    "data/gpt50/experiment/scenario/scenarios/scenario_001/scenario_001.json"
).read_text(encoding="utf-8"))


class UnusedProvider:
    def complete(self, messages, **generation):
        raise AssertionError("validator unit test must not call provider")


def response_value(text, events=None, **extra):
    value = {
        "response_text": text,
        "expression_intent": "保持合作但纠正误解",
        "observable_behavior": {
            "facial_expression": "神情平静",
            "gaze": "看向对方",
            "speech_style": "直接",
            "prosody": "语速平稳",
            "behavioral_cues": [],
        },
        "ledger_events": list(events or []),
        "reply_obligation": None,
        "consequential_claims": [],
    }
    value.update(extra)
    return value


class SemanticEventContractV25Test(unittest.TestCase):
    def setUp(self):
        self.generator = ModelResponseGenerator(
            UnusedProvider(),
            prompt_id="environment_response_v25",
            validation_profile="hard_only",
            horizon_mode="natural_max_20",
        )
        self.context = {
            "scenario": SCENARIO,
            "action": {"text": "请说明你的立场。"},
            "history": [],
            "interaction_ledger": {},
            "longitudinal_context": {},
            "turn_id": 1,
        }

    def test_nonasserted_commitment_candidate_never_enters_ledger(self):
        text = "我会把所有工作归为执行，这不是我的意思。"
        event = {
            "event_type": "commitment",
            "owner": "environment_agent",
            "action_owner": "environment_agent",
            "evidence_span": text,
            "status": "firm",
            "assertion_mode": "negated",
        }
        normalizations = []
        events = validate_semantic_ledger_events(
            [event], text, "environment_agent",
            require_assertion_mode=True,
            normalization_log=normalizations,
        )
        self.assertEqual(events, [])
        self.assertEqual(
            normalizations[0]["operation"],
            "exclude_nonasserted_event_candidate",
        )

    def test_v25_does_not_reinfer_a_dropped_commitment_with_regex(self):
        text = "我会把所有工作归为执行，这不是我的意思。"
        value = response_value(text, [{
            "event_type": "commitment",
            "owner": "environment_agent",
            "action_owner": "environment_agent",
            "evidence_span": text,
            "status": "firm",
            "assertion_mode": "negated",
        }])
        result = self.generator._validate_structured_response(
            value, self.context
        )
        self.assertEqual(result["ledger_events"], [])

    def test_v25_rejects_unsupported_consequential_response_claim(self):
        text = "学院已经决定取消你的资格。"
        value = response_value(text, consequential_claims=[{
            "claim_span": text,
            "impact_domains": ["rights"],
            "grounding": "unsupported_assertion",
        }])
        with self.assertRaisesRegex(ValueError, "absent from public history"):
            self.generator._validate_structured_response(value, self.context)

    def test_v25_requires_request_event_and_obligation_to_agree(self):
        text = "把方便的时间发给我。"
        value = response_value(text, reply_obligation="evaluated_agent")
        with self.assertRaisesRegex(ValueError, "disagree"):
            self.generator._validate_structured_response(value, self.context)

    def test_v25_requires_new_specific_number_to_be_declared(self):
        text = "这个月的三千块什么时候能给我？"
        value = response_value(text, [{
            "event_type": "request",
            "owner": "environment_agent",
            "action_owner": "evaluated_agent",
            "evidence_span": text,
            "status": "open",
            "assertion_mode": "asserted",
        }], reply_obligation="evaluated_agent")
        with self.assertRaisesRegex(ValueError, "new specific number"):
            self.generator._validate_structured_response(value, self.context)

    def test_v25_keeps_declared_numeric_proposal_for_private_audit(self):
        text = "这个月先按三千块安排，是否可行？"
        claim = {
            "claim_span": "三千块安排，是否可行",
            "impact_domains": ["action_feasibility"],
            "grounding": "proposal_or_hypothetical",
        }
        value = response_value(text, [{
            "event_type": "request",
            "owner": "environment_agent",
            "action_owner": "evaluated_agent",
            "evidence_span": text,
            "status": "open",
            "assertion_mode": "asserted",
        }], reply_obligation="evaluated_agent", consequential_claims=[claim])
        result = self.generator._validate_structured_response(value, self.context)
        self.assertEqual(result["consequential_claims"], [claim])
        self.assertEqual(result["reply_obligation"], "evaluated_agent")

    def test_v25_treats_arabic_and_chinese_number_forms_as_equivalent(self):
        self.context["action"] = {"text": "5天后我把合同给你看。"}
        value = response_value("那我就等五天，再看合同。")
        result = self.generator._validate_structured_response(value, self.context)
        self.assertEqual(result["consequential_claims"], [])

    def test_v11_requires_explicit_assertion_mode(self):
        action = "我会明天回复。"
        appraisal = {
            "speaker_intent": "承诺回复",
            "social_act": "commitment",
            "event_features": {
                key: (1 if key == "commitment_signal" else 0)
                for key in (
                    "goal_alignment", "cooperation_signal", "repair_signal",
                    "pressure", "face_threat", "commitment_signal",
                    "uncertainty_reduction", "boundary_violation",
                    "respect_signal", "withdrawal_signal",
                )
            },
            "state_impacts": [],
            "dynamics_impacts": [],
            "ledger_events": [{
                "event_type": "commitment",
                "owner": "evaluated_agent",
                "action_owner": "evaluated_agent",
                "evidence_span": action,
                "status": "firm",
            }],
            "dialogue_diagnostics": {
                "substantive_novelty": {
                    "label": "new_decision", "evidence_span": action,
                },
                "consequential_claims": [],
                "continuation": {
                    "status": "can_close", "evidence_span": action,
                    "after_direct_response": {
                        "status": "can_close", "evidence_span": action,
                        "resolved_live_questions": [],
                        "remaining_live_questions": [],
                    },
                },
            },
        }
        with self.assertRaisesRegex(ValueError, "assertion_mode"):
            _validate_appraisal(
                {"appraisal": appraisal, "evidence_turn_ids": []},
                [], set(), set(), action_text=action,
                require_dialogue_diagnostics=True,
                require_after_direct_response=True,
                require_ledger_events=True,
                require_assertion_mode=True,
            )


if __name__ == "__main__":
    unittest.main()
