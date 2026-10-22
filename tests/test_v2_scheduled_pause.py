import unittest

from environment.longitudinal import _should_advance


class V2ScheduledPauseTests(unittest.TestCase):
    def test_directly_answered_proposal_can_pause_for_scheduled_node(self):
        should_advance, reason = _should_advance(
            {"segment_turn_id": 1, "interaction_ledger": {"latest_obligation": None}},
            {"min_turns": 1, "max_turns": 7},
            "两天后在组会核对这些记录。",
            "好的，组会上再逐项核对。",
            appraisal={"dialogue_diagnostics": {"continuation": {
                "status": "continue",
                "after_direct_response": {"status": "can_close"},
            }}},
            response_events=[],
            final_segment=False,
        )
        self.assertTrue(should_advance)
        self.assertEqual(reason, "appraisal_direct_answer_pause")

    def test_direct_answer_can_pause_with_optional_live_questions_remaining(self):
        should_advance, reason = _should_advance(
            {"segment_turn_id": 1, "interaction_ledger": {"latest_obligation": None}},
            {"min_turns": 1, "max_turns": 7},
            "对照表会列出这两项吗？",
            "是，会逐项列出。",
            appraisal={"dialogue_diagnostics": {"continuation": {
                "status": "must_answer",
                "after_direct_response": {
                    "status": "can_close",
                    "resolved_live_questions": [],
                    "remaining_live_questions": ["责任解释", "等待期间的行动"],
                },
            }}},
            response_events=[],
            final_segment=False,
        )
        self.assertTrue(should_advance)
        self.assertEqual(reason, "appraisal_direct_answer_pause")

    def test_new_counterproposal_still_blocks_scheduled_pause(self):
        should_advance, reason = _should_advance(
            {"segment_turn_id": 1, "interaction_ledger": {
                "latest_obligation": {"owner": "evaluated_agent"},
            }},
            {"min_turns": 1, "max_turns": 7},
            "两天后在组会核对这些记录。",
            "但我建议先只看实验日志。",
            appraisal={"dialogue_diagnostics": {"continuation": {
                "status": "continue",
                "after_direct_response": {"status": "can_close"},
            }}},
            response_events=[{"event_type": "proposal", "status": "open"}],
            final_segment=False,
        )
        self.assertFalse(should_advance)
        self.assertIsNone(reason)

    def test_pause_wording_cannot_close_over_a_new_reply_obligation(self):
        should_advance, reason = _should_advance(
            {"segment_turn_id": 2, "interaction_ledger": {
                "latest_obligation": {"owner": "evaluated_agent"},
            }},
            {"min_turns": 1, "max_turns": 7, "allow_explicit_pause": True},
            "到时候再说。",
            "你把方便的时间发给我，到时候拿证据说话。",
            appraisal={"dialogue_diagnostics": {"continuation": {
                "status": "can_close",
                "after_direct_response": {"status": "can_close"},
            }}},
            response_events=[{
                "event_type": "request", "status": "open",
                "action_owner": "evaluated_agent",
            }],
            final_segment=True,
        )
        self.assertFalse(should_advance)
        self.assertIsNone(reason)


if __name__ == "__main__":
    unittest.main()
