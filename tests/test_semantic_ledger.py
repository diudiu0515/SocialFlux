import json
import unittest
from pathlib import Path

from environment.interaction_ledger import (
    initial_ledger,
    uncovered_owned_commitment_spans,
    record_environment_response,
    validate_semantic_ledger_events,
    record_evaluated_action,
)


CASES = json.loads(
    Path("tests/fixtures/semantic_ledger_short_cases.json").read_text(encoding="utf-8")
)


class SemanticLedgerShortCaseTest(unittest.TestCase):
    def test_scalar_discussion_space_is_one_item_not_characters(self):
        ledger = initial_ledger(discussion_dimensions="核对事实后共同披露")
        self.assertEqual(ledger["discussion_space"], ["核对事实后共同披露"])

    def test_whitespace_only_span_variant_is_aligned_to_exact_source(self):
        text = "你在14天内能还多少？"
        events = [{
            "event_type": "request", "owner": "evaluated_agent",
            "action_owner": "evaluated_agent",
            "evidence_span": "你在 14 天内能还多少", "status": "open",
        }]
        normalized = validate_semantic_ledger_events(
            events, text, "evaluated_agent"
        )
        self.assertEqual(normalized[0]["evidence_span"], "你在14天内能还多少")
        self.assertEqual(normalized[0]["action_owner"], "environment_agent")

    def test_claim_alias_is_reported_but_not_established(self):
        text = "目前没有实际到账。"
        events = [{
            "event_type": "inform", "owner": "environment_agent",
            "action_owner": "environment_agent", "evidence_span": text,
            "status": "reported",
        }]
        normalized = validate_semantic_ledger_events(
            events, text, "environment_agent"
        )
        self.assertEqual(normalized[0]["event_type"], "claim")
        ledger = record_environment_response(
            initial_ledger(), turn_id=1, response=text,
            latest_social_act="inform", semantic_events=normalized,
        )
        self.assertEqual(
            ledger["reported_claims"][0]["status"], "speaker_report_only"
        )
        self.assertFalse(ledger["established_facts"])

    def test_other_person_action_is_attributed_but_not_owned_commitment(self):
        text = "14天节点你必须如期到账。"
        appraisal = {"social_act": "boundary", "ledger_events": [{
            "event_type": "commitment",
            "owner": "evaluated_agent",
            "action_owner": "environment_agent",
            "evidence_span": text,
            "status": "firm",
        }]}
        ledger = record_evaluated_action(
            initial_ledger(), turn_id=1, action={"text": text},
            appraisal=appraisal, semantic_events=appraisal["ledger_events"],
        )
        self.assertFalse(ledger["commitments"])
        self.assertEqual(
            ledger["attributed_actions"][0]["status"],
            "attributed_not_owned_commitment",
        )

    def test_quote_and_owner_contract_on_saved_short_cases(self):
        for case in CASES:
            expected_owner = case.get("expected_owner") or case["events"][0]["owner"]
            with self.subTest(case=case["id"]):
                if case["valid"]:
                    self.assertEqual(
                        validate_semantic_ledger_events(
                            case["events"], case["text"], expected_owner
                        ),
                        case["events"],
                    )
                else:
                    with self.assertRaises(ValueError):
                        validate_semantic_ledger_events(
                            case["events"], case["text"], expected_owner
                        )

    def test_tentative_proposal_does_not_become_pending_commitment(self):
        case = next(item for item in CASES if item["id"] == "tentative_proposal")
        ledger = record_environment_response(
            initial_ledger(), turn_id=1, response=case["text"],
            latest_social_act="request", semantic_events=case["events"],
        )
        self.assertEqual(ledger["commitments"], [])
        self.assertEqual(ledger["active_proposals"][0]["status"], "tentative")

    def test_firm_commitment_records_amount_and_payment_stays_report_only(self):
        commitment = next(item for item in CASES if item["id"] == "firm_commitment")
        payment = next(item for item in CASES if item["id"] == "payment_report_only")
        ledger = record_environment_response(
            initial_ledger(), turn_id=1, response=commitment["text"],
            latest_social_act="request", semantic_events=commitment["events"],
        )
        self.assertEqual(ledger["commitments"][0]["status"], "pending")
        self.assertEqual(ledger["commitments"][0]["amounts"], [800.0])
        ledger = record_environment_response(
            ledger, turn_id=2, response=payment["text"],
            latest_social_act="inform", semantic_events=payment["events"],
        )
        self.assertEqual(ledger["commitments"][0]["status"], "reported_complete")
        self.assertEqual(
            ledger["commitments"][0]["completion_evidence_status"],
            "speaker_report_only",
        )

    def test_ambiguous_arrangement_is_not_recorded_as_commitment(self):
        case = next(
            item for item in CASES
            if item["id"] == "ambiguous_arrangement_not_commitment"
        )
        ledger = record_environment_response(
            initial_ledger(), turn_id=1, response=case["text"],
            latest_social_act="inform", semantic_events=case["events"],
        )
        self.assertFalse(ledger["commitments"])

    def test_question_and_challenge_social_act_aliases_are_conservative(self):
        text = (
            "当前的承诺未在21天节点履行，"
            "是否意味着我们需要重新明确经济往来的边界？"
        )
        events = [
            {
                "event_type": "challenge", "owner": "evaluated_agent",
                "action_owner": "environment_agent",
                "evidence_span": "当前的承诺未在21天节点履行",
                "status": "open",
            },
            {
                "event_type": "question", "owner": "evaluated_agent",
                "action_owner": "environment_agent",
                "evidence_span": "是否意味着我们需要重新明确经济往来的边界",
                "status": "open",
            },
        ]
        normalized = validate_semantic_ledger_events(
            events, text, "evaluated_agent"
        )
        self.assertEqual(
            [(item["event_type"], item["status"]) for item in normalized],
            [("claim", "reported"), ("request", "open")],
        )
        ledger = record_evaluated_action(
            initial_ledger(), turn_id=1, action={"text": text},
            appraisal={"social_act": "question"}, semantic_events=events,
        )
        self.assertFalse(ledger["commitments"])
        self.assertEqual(len(ledger["reported_claims"]), 1)
        self.assertEqual(ledger["latest_obligation"]["owner"], "environment_agent")


    def test_response_can_drop_nonverbatim_event_with_audit_record(self):
        text = "14天节点我尽量安排，若有变动会及时告知。"
        events = [
            {
                "event_type": "request", "owner": "environment_agent",
                "action_owner": "evaluated_agent",
                "evidence_span": "14天节点是否可行", "status": "open",
            },
            {
                "event_type": "commitment", "owner": "environment_agent",
                "action_owner": "environment_agent",
                "evidence_span": "若有变动会及时告知", "status": "conditional",
            },
        ]
        normalizations = []
        normalized = validate_semantic_ledger_events(
            events, text, "environment_agent", drop_ungrounded=True,
            normalization_log=normalizations,
        )
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["event_type"], "commitment")
        self.assertEqual(
            normalizations[0]["operation"], "drop_nonverbatim_ledger_event"
        )



    def test_response_can_drop_grounded_nonrequest_with_audit_record(self):
        text = "我尽量在20天后确定一个大致金额范围，比如500到800元之间，方便你记录。"
        events = [{
            "event_type": "request", "owner": "environment_agent",
            "action_owner": "evaluated_agent", "evidence_span": "方便你记录",
            "status": "open",
        }]
        normalizations = []
        normalized = validate_semantic_ledger_events(
            events, text, "environment_agent", drop_nonrequests=True,
            normalization_log=normalizations,
        )
        self.assertEqual(normalized, [])
        self.assertEqual(
            normalizations[0]["operation"], "drop_nonrequest_ledger_event"
        )


    def test_request_firm_owned_by_speaker_normalizes_to_commitment(self):
        text = "调解书下来了我立马微信发你"
        normalizations = []
        events = validate_semantic_ledger_events(
            [{
                "event_type": "request",
                "owner": "environment_agent",
                "action_owner": "environment_agent",
                "evidence_span": text,
                "status": "firm",
            }],
            text,
            "environment_agent",
            normalize_owned_future_requests=True,
            normalization_log=normalizations,
        )
        self.assertEqual(events[0]["event_type"], "commitment")
        self.assertEqual(events[0]["status"], "firm")
        self.assertEqual(events[0]["action_owner"], "environment_agent")
        self.assertEqual(
            normalizations[0]["reason"],
            "request_status_and_action_owner_encode_speaker_commitment",
        )

    def test_conditional_offer_status_normalizes_to_tentative_proposal(self):
        text = "分阶段方案可以接受，但你得先明确每个阶段的数据指标"
        normalizations = []
        events = validate_semantic_ledger_events(
            [{
                "event_type": "conditional_offer",
                "owner": "evaluated_agent",
                "action_owner": "evaluated_agent",
                "evidence_span": text,
                "status": "conditional",
            }],
            text,
            "evaluated_agent",
            normalization_log=normalizations,
        )
        self.assertEqual(events[0]["event_type"], "proposal")
        self.assertEqual(events[0]["status"], "tentative")
        self.assertEqual(
            normalizations[0]["operation"], "normalize_conditional_offer_status"
        )

    def test_response_downgrades_effort_language_from_commitment(self):
        text = "14天内还500元这个节点我尽量做到，但目前金额暂时无法调整。"
        events = [{
            "event_type": "commitment", "owner": "environment_agent",
            "action_owner": "environment_agent",
            "evidence_span": "14天内还500元这个节点我尽量做到",
            "status": "firm",
        }]
        normalizations = []
        normalized = validate_semantic_ledger_events(
            events, text, "environment_agent",
            normalize_tentative_commitments=True,
            normalization_log=normalizations,
        )
        self.assertEqual(normalized[0]["event_type"], "proposal")
        self.assertEqual(normalized[0]["status"], "tentative")
        self.assertEqual(
            normalizations[0]["operation"],
            "downgrade_tentative_commitment_to_proposal",
        )


    def test_response_downgrades_temporary_acceptance_from_commitment(self):
        text = "14天内还500元这个节点我暂时能接受，但金额可能需要调整。"
        events = [{
            "event_type": "commitment", "owner": "environment_agent",
            "action_owner": "environment_agent",
            "evidence_span": "14天内还500元这个节点我暂时能接受",
            "status": "conditional",
        }]
        normalizations = []
        normalized = validate_semantic_ledger_events(
            events, text, "environment_agent",
            normalize_tentative_commitments=True,
            normalization_log=normalizations,
        )
        self.assertEqual(
            (normalized[0]["event_type"], normalized[0]["status"]),
            ("proposal", "tentative"),
        )
        self.assertEqual(
            normalizations[0]["operation"],
            "downgrade_tentative_commitment_to_proposal",
        )


    def test_response_keeps_explicit_grounded_request(self):
        text = "但希望你能确保按时履行。"
        events = [{
            "event_type": "request", "owner": "environment_agent",
            "action_owner": "evaluated_agent",
            "evidence_span": "希望你能确保按时履行", "status": "open",
        }]
        normalizations = []
        normalized = validate_semantic_ledger_events(
            events, text, "environment_agent", drop_nonrequests=True,
            normalization_log=normalizations,
        )
        self.assertEqual(normalized[0]["event_type"], "request")
        self.assertEqual(normalizations, [])

    def test_response_downgrades_attempt_phrase_from_commitment(self):
        text = "14天还500元这个节点我觉得可以尝试。"
        events = [{
            "event_type": "commitment", "owner": "environment_agent",
            "action_owner": "environment_agent",
            "evidence_span": "14天还500元这个节点我觉得可以尝试",
            "status": "firm",
        }]
        normalized = validate_semantic_ledger_events(
            events, text, "environment_agent",
            normalize_tentative_commitments=True, normalization_log=[],
        )
        self.assertEqual(
            (normalized[0]["event_type"], normalized[0]["status"]),
            ("proposal", "tentative"),
        )


    def test_response_normalizes_owned_future_action_mislabeled_as_request(self):
        text = "好的，我会在14天内还500元。如果遇到问题，我会提前沟通。"
        events = [
            {
                "event_type": "commitment", "owner": "environment_agent",
                "action_owner": "environment_agent",
                "evidence_span": "我会在14天内还500元", "status": "firm",
            },
            {
                "event_type": "request", "owner": "environment_agent",
                "action_owner": "evaluated_agent",
                "evidence_span": "如果遇到问题，我会提前沟通", "status": "open",
            },
        ]
        normalizations = []
        normalized = validate_semantic_ledger_events(
            events, text, "environment_agent",
            normalize_owned_future_requests=True,
            normalization_log=normalizations,
        )
        self.assertEqual(
            (normalized[1]["event_type"], normalized[1]["status"]),
            ("commitment", "conditional"),
        )
        self.assertEqual(normalized[1]["action_owner"], "environment_agent")
        self.assertEqual(
            normalizations[0]["operation"],
            "normalize_owned_future_request_to_commitment",
        )
        self.assertEqual(
            uncovered_owned_commitment_spans(text, normalized, "environment_agent"),
            [],
        )


    def test_response_drops_acceptance_mislabeled_as_owned_commitment(self):
        text = "我接受你提议的联系方式。"
        events = [{
            "event_type": "commitment", "owner": "environment_agent",
            "action_owner": "environment_agent",
            "evidence_span": "我接受你提议的联系方式", "status": "firm",
        }]
        normalizations = []
        normalized = validate_semantic_ledger_events(
            events, text, "environment_agent",
            drop_acceptance_events=True,
            normalization_log=normalizations,
        )
        self.assertEqual(normalized, [])
        self.assertEqual(
            normalizations[0]["operation"],
            "drop_acceptance_mislabeled_as_new_event",
        )

    def test_acceptance_normalization_precedes_event_type_validation(self):
        cases = [
            (
                "我接受你提出的普通联系方式。",
                {
                    "event_type": "proposal", "owner": "evaluated_agent",
                    "action_owner": "evaluated_agent",
                    "evidence_span": "我接受你提出的普通联系方式。",
                    "status": "tentative",
                },
                [],
            ),
            (
                "我接受这个提议。",
                {
                    "event_type": "concession", "owner": "evaluated_agent",
                    "action_owner": "evaluated_agent",
                    "evidence_span": "我接受这个提议。",
                    "status": "reported",
                },
                [],
            ),
            (
                "我接受这个提议。在现有分歧未解决前，我们保持普通朋友联系。",
                {
                    "event_type": "boundary", "owner": "evaluated_agent",
                    "action_owner": "collective",
                    "evidence_span": "在现有分歧未解决前，我们保持普通朋友联系。",
                    "status": "reported",
                },
                [{
                    "speaker": "environment_agent", "status": "open",
                    "text": "在现有分歧未解决前，只保持普通朋友联系。",
                }],
            ),
        ]
        for text, event, active_proposals in cases:
            with self.subTest(event_type=event["event_type"]):
                normalizations = []
                self.assertEqual(
                    validate_semantic_ledger_events(
                        [event], text, "evaluated_agent",
                        drop_acceptance_events=True,
                        active_proposals=active_proposals,
                        normalization_log=normalizations,
                    ),
                    [],
                )
                self.assertEqual(
                    normalizations[0]["operation"],
                    "drop_acceptance_mislabeled_as_new_event",
                )


    def test_response_drops_accepted_proposal_restatement(self):
        text = "我接受这个提议。在现有分歧未解决前，我们保持普通朋友联系。"
        events = [{
            "event_type": "proposal", "owner": "environment_agent",
            "action_owner": "collective",
            "evidence_span": "在现有分歧未解决前，我们保持普通朋友联系",
            "status": "open",
        }]
        normalizations = []
        normalized = validate_semantic_ledger_events(
            events, text, "environment_agent",
            drop_acceptance_events=True,
            active_proposals=[{
                "speaker": "evaluated_agent", "status": "open",
                "text": "我们是否可以明确：在现有分歧未解决前，只保持普通朋友联系？",
            }],
            normalization_log=normalizations,
        )
        self.assertEqual(normalized, [])
        self.assertEqual(
            normalizations[0]["operation"],
            "drop_acceptance_mislabeled_as_new_event",
        )

    def test_response_keeps_counterproposal_after_acceptance(self):
        text = "我接受保持普通联系，但改为每月问候一次。"
        events = [{
            "event_type": "proposal", "owner": "environment_agent",
            "action_owner": "collective",
            "evidence_span": "改为每月问候一次", "status": "open",
        }]
        normalized = validate_semantic_ledger_events(
            events, text, "environment_agent",
            drop_acceptance_events=True,
            active_proposals=[{
                "speaker": "evaluated_agent", "status": "open",
                "text": "保持普通联系，每季度问候一次",
            }],
            normalization_log=[],
        )
        self.assertEqual(
            (normalized[0]["event_type"], normalized[0]["evidence_span"]),
            ("proposal", "改为每月问候一次"),
        )


    def test_response_detects_uncovered_definite_future_action(self):
        text = "金额可能需要根据实际情况调整，我会尽快确认。"
        events = [{
            "event_type": "proposal", "owner": "environment_agent",
            "action_owner": "environment_agent",
            "evidence_span": "金额可能需要根据实际情况调整",
            "status": "tentative",
        }]
        self.assertEqual(
            uncovered_owned_commitment_spans(text, events, "environment_agent"),
            ["我会尽快确认"],
        )


    def test_repayment_acceptance_with_owned_action_is_a_commitment(self):
        text = "我同意14天后转账300元。"
        self.assertEqual(
            uncovered_owned_commitment_spans(text, [], "environment_agent"),
            ["我同意14天后转账300元"],
        )

    def test_conditional_commitment_event_type_is_normalized(self):
        text = "如果到账延迟，我会当天告诉你。"
        normalized = validate_semantic_ledger_events([{
            "event_type": "conditional_commitment",
            "owner": "environment_agent",
            "action_owner": "environment_agent",
            "evidence_span": "如果到账延迟，我会当天告诉你",
            "status": "conditional",
        }], text, "environment_agent")
        self.assertEqual(normalized[0]["event_type"], "commitment")


    def test_explicit_pause_covers_pause_wording_not_a_new_commitment(self):
        text = "我先把这事放一放，等你那边有具体进展了再细聊。"
        events = [{
            "event_type": "pause", "owner": "environment_agent",
            "action_owner": "environment_agent",
            "evidence_span": "我先把这事放一放", "status": "explicit",
        }]
        self.assertEqual(
            uncovered_owned_commitment_spans(text, events, "environment_agent"),
            [],
        )


    def test_conditional_commitment_is_asserted_not_merely_hypothetical(self):
        text = "如果你今晚发材料，我明早审完。"
        event = {
            "event_type": "commitment",
            "owner": "evaluated_agent",
            "action_owner": "evaluated_agent",
            "evidence_span": "如果你今晚发材料，我明早审完",
            "status": "conditional",
            "assertion_mode": "asserted",
        }
        normalized = validate_semantic_ledger_events(
            [event], text, "evaluated_agent", require_assertion_mode=True,
        )
        self.assertEqual(
            (normalized[0]["event_type"], normalized[0]["status"]),
            ("commitment", "conditional"),
        )

        hypothetical = dict(event)
        hypothetical["assertion_mode"] = "hypothetical"
        normalizations = []
        self.assertEqual(
            validate_semantic_ledger_events(
                [hypothetical], text, "evaluated_agent",
                require_assertion_mode=True,
                normalization_log=normalizations,
            ),
            [],
        )
        self.assertEqual(
            normalizations[0]["operation"],
            "exclude_nonasserted_event_candidate",
        )

    def test_explicit_resolution_updates_only_the_bound_proposal_id(self):
        proposal_text = "可以先审材料，也可以先开会。"
        ledger = record_environment_response(
            initial_ledger(), turn_id=1, response=proposal_text,
            latest_social_act="proposal",
            semantic_events=[{
                "event_type": "proposal", "owner": "environment_agent",
                "action_owner": "collective", "evidence_span": "先审材料",
                "status": "open",
            }, {
                "event_type": "proposal", "owner": "environment_agent",
                "action_owner": "collective", "evidence_span": "先开会",
                "status": "open",
            }],
        )
        proposal_ids = [item["id"] for item in ledger["active_proposals"]]
        self.assertEqual(len(set(proposal_ids)), 2)
        action = "我接受先审材料的方案。"
        appraisal = {
            "social_act": "concession",
            "ledger_resolutions": [{
                "target_id": proposal_ids[0],
                "resolution": "accepted",
                "evidence_span": "我接受先审材料的方案",
            }],
        }
        updated = record_evaluated_action(
            ledger, turn_id=2, action={"text": action}, appraisal=appraisal,
            semantic_events=[],
        )
        self.assertEqual(
            [item["id"] for item in updated["active_proposals"]],
            [proposal_ids[1]],
        )
        self.assertEqual(
            updated["proposal_resolutions"][-1]["id"], proposal_ids[0]
        )
        self.assertEqual(
            updated["proposal_resolutions"][-1]["resolution_status"],
            "accepted",
        )


if __name__ == "__main__":
    unittest.main()
