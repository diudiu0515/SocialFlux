import unittest

from environment.interaction_ledger import validate_semantic_ledger_events


class V2EvidenceNodeLedgerTests(unittest.TestCase):
    def test_deferred_result_statement_is_not_a_request(self):
        text = "具体评分标准和经理总结的差异需要等结果公布后才能确认"
        normalizations = []
        events = validate_semantic_ledger_events(
            [{
                "event_type": "request",
                "owner": "environment_agent",
                "action_owner": "evaluated_agent",
                "evidence_span": text,
                "status": "open",
            }],
            text,
            "environment_agent",
            drop_nonrequests=True,
            normalization_log=normalizations,
        )
        self.assertEqual(events, [])
        self.assertEqual(
            normalizations[0]["operation"], "drop_nonrequest_ledger_event"
        )

    def test_acknowledged_collective_restatement_is_not_a_new_proposal(self):
        text = "好的，先把实验日志和初稿版本记录列出来，我们可以在组会上逐项核对。"
        normalizations = []
        events = validate_semantic_ledger_events(
            [{
                "event_type": "proposal",
                "owner": "environment_agent",
                "action_owner": "collective",
                "evidence_span": "先把实验日志和初稿版本记录列出来，我们可以在组会上逐项核对",
                "status": "open",
            }],
            text,
            "environment_agent",
            drop_acceptance_events=True,
            active_proposals=[{
                "speaker": "evaluated_agent",
                "status": "open",
                "text": "我整理了实验日志和初稿版本记录，可以先列明证据，再在组会上核对。",
            }],
            normalization_log=normalizations,
        )
        self.assertEqual(events, [])
        self.assertEqual(
            normalizations[0]["operation"],
            "drop_acceptance_mislabeled_as_new_event",
        )

    def test_acknowledged_counterproposal_remains_open(self):
        text = "好的，但我建议先只核对实验日志，初稿版本以后再谈。"
        events = validate_semantic_ledger_events(
            [{
                "event_type": "proposal",
                "owner": "environment_agent",
                "action_owner": "collective",
                "evidence_span": "我建议先只核对实验日志，初稿版本以后再谈",
                "status": "open",
            }],
            text,
            "environment_agent",
            drop_acceptance_events=True,
            active_proposals=[{
                "speaker": "evaluated_agent",
                "status": "open",
                "text": "把实验日志和初稿版本一起核对。",
            }],
            normalization_log=[],
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "proposal")


if __name__ == "__main__":
    unittest.main()
