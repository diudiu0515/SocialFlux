import unittest

from environment.response_generator import ModelResponseGenerator


class V2EventBoundaryResponseTests(unittest.TestCase):
    def setUp(self):
        self.generator = object.__new__(ModelResponseGenerator)
        self.generator.validation_profile = "hard_only"
        self.generator.horizon_mode = "natural_max_20"

    def test_exact_pre_event_response_is_stale_after_public_event(self):
        candidate = "我会在两天后的对照表发布后，第一时间与你核对相关记录和评分差异。"
        passed, reason = self.generator._validate_candidate_for_profile(
            candidate,
            {
                "scenario": {},
                "action": {"text": "请明确现在的更正流程。"},
                "history": [
                    {"role": "environment_agent", "text": candidate},
                    {"role": "public_event", "text": "自查结果已经发布。"},
                ],
                "interaction_ledger": {},
                "longitudinal_context": {
                    "segment": {"segment_turn_id": 0},
                    "public_timeline": [{
                        "public": True, "text": "自查结果已经发布。"
                    }],
                },
                "turn_id": 4,
            },
        )
        self.assertFalse(passed)
        self.assertIn("public event boundary", reason)

    def test_structured_response_preserves_quote_grounded_implicit_request(self):
        text = (
            "在顺序和告知内容没定死之前，你联系当事人时不能只谈风险，"
            "得把这两点拆开讲清楚，否则我这边没法背书。"
        )
        result = self.generator._validate_structured_response(
            {
                "response_text": text,
                "ledger_events": [{
                    "event_type": "request",
                    "owner": "environment_agent",
                    "action_owner": "evaluated_agent",
                    "evidence_span": (
                        "在顺序和告知内容没定死之前，你联系当事人时不能只谈风险，"
                        "得把这两点拆开讲清楚"
                    ),
                    "status": "open",
                }],
            },
            {
                "scenario": {},
                "action": {"text": "伦理意见出来后，我们现在怎么联系当事人？"},
                "history": [],
                "interaction_ledger": {},
                "longitudinal_context": {"segment": {}, "public_timeline": []},
                "turn_id": 2,
            },
        )
        self.assertEqual(len(result["ledger_events"]), 1)
        self.assertEqual(result["ledger_events"][0]["event_type"], "request")
        self.assertEqual(
            result["ledger_events"][0]["action_owner"], "evaluated_agent"
        )

    def test_nonduplicate_answer_is_allowed_at_event_boundary(self):
        passed, reason = self.generator._validate_candidate_for_profile(
            "事实更正由我提交校准负责人，你不需要重复提交同一份记录。",
            {
                "scenario": {},
                "action": {"text": "请明确现在的更正流程。"},
                "history": [
                    {"role": "environment_agent", "text": "等自查结果出来再核对。"},
                    {"role": "public_event", "text": "自查结果已经发布。"},
                ],
                "interaction_ledger": {},
                "longitudinal_context": {
                    "segment": {"segment_turn_id": 0},
                    "public_timeline": [{
                        "public": True, "text": "自查结果已经发布。"
                    }],
                },
                "turn_id": 4,
            },
        )
        self.assertTrue(passed, reason)


if __name__ == "__main__":
    unittest.main()
