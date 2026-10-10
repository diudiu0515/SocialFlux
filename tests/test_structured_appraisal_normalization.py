import unittest

from environment.appraisal import (
    _STATE_IMPACT_FAMILY_CAPS_BY_PROMPT,
    _validate_appraisal,
)
from environment.appraisal_normalization import (
    canonicalize_impact_lists,
    canonicalize_social_act,
)
from environment.calibration import FEATURE_NAMES
from providers.structured import _parse_json_output


class StructuredAppraisalNormalizationTest(unittest.TestCase):
    def _two_relationship_candidates(self, shared_span=False):
        features = {name: 0 for name in FEATURE_NAMES}
        features["respect_signal"] = 2
        features["cooperation_signal"] = 2
        action = "我会先公开分配依据，也愿意按约定让受影响者复核。"
        second_span = (
            "我会先公开分配依据"
            if shared_span
            else "也愿意按约定让受影响者复核"
        )
        return action, {
            "appraisal": {
                "speaker_intent": "make allocation accountable",
                "social_act": "commitment",
                "event_features": features,
                "state_impacts": [
                    {
                        "variable": "relationship.perceived_responsiveness",
                        "direction": "increase",
                        "evidence_feature": "cooperation_signal",
                        "evidence_span": "我会先公开分配依据",
                        "evidence_strength": 2,
                        "directness": "direct",
                        "new_evidence": True,
                    },
                    {
                        "variable": "relationship.perceived_fairness",
                        "direction": "increase",
                        "evidence_feature": "respect_signal",
                        "evidence_span": second_span,
                        "evidence_strength": 2,
                        "directness": "direct",
                        "new_evidence": True,
                    },
                ],
                "dynamics_impacts": [],
            },
            "evidence_turn_ids": [],
        }

    def test_v14_accepts_two_independently_grounded_relationship_candidates(self):
        action, result = self._two_relationship_candidates()
        normalized = _validate_appraisal(
            result,
            allowed_evidence_ids=[],
            state_variables={
                "relationship.perceived_responsiveness",
                "relationship.perceived_fairness",
            },
            dynamics_variables={"negotiation_open"},
            action_text=action,
            require_impact_evidence=True,
            state_impact_family_caps={"relationship": 2},
            require_distinct_family_evidence_spans=True,
        )
        self.assertEqual(len(normalized["appraisal"]["state_impacts"]), 2)

    def test_feature_consistent_profile_rejects_zero_cited_feature(self):
        action, result = self._two_relationship_candidates()
        result["appraisal"]["event_features"]["cooperation_signal"] = 0
        with self.assertRaisesRegex(ValueError, "non-zero event feature"):
            _validate_appraisal(
                result,
                allowed_evidence_ids=[],
                state_variables={
                    "relationship.perceived_responsiveness",
                    "relationship.perceived_fairness",
                },
                dynamics_variables={"negotiation_open"},
                action_text=action,
                require_impact_evidence=True,
                state_impact_family_caps={"relationship": 2},
                require_distinct_family_evidence_spans=True,
                require_nonzero_impact_features=True,
            )

    def test_v14_rejects_reused_relationship_evidence_span(self):
        action, result = self._two_relationship_candidates(shared_span=True)
        with self.assertRaisesRegex(ValueError, "distinct evidence spans"):
            _validate_appraisal(
                result,
                allowed_evidence_ids=[],
                state_variables={
                    "relationship.perceived_responsiveness",
                    "relationship.perceived_fairness",
                },
                dynamics_variables={"negotiation_open"},
                action_text=action,
                require_impact_evidence=True,
                state_impact_family_caps={"relationship": 2},
                require_distinct_family_evidence_spans=True,
            )

    def test_v13_family_cap_still_rejects_two_relationship_candidates(self):
        action, result = self._two_relationship_candidates()
        with self.assertRaisesRegex(
            ValueError, "at most 1 candidate.*relationship"
        ):
            _validate_appraisal(
                result,
                allowed_evidence_ids=[],
                state_variables={
                    "relationship.perceived_responsiveness",
                    "relationship.perceived_fairness",
                },
                dynamics_variables={"negotiation_open"},
                action_text=action,
                require_impact_evidence=True,
                state_impact_family_caps={"relationship": 1},
            )

    def test_v36_allows_multiple_same_family_candidates_and_shared_span(self):
        action, result = self._two_relationship_candidates(shared_span=True)
        result["appraisal"]["state_impacts"].append({
            "variable": "relationship.trust",
            "direction": "increase",
            "evidence_feature": "cooperation_signal",
            "evidence_span": "我会先公开分配依据",
            "evidence_strength": 2,
            "directness": "direct",
            "new_evidence": True,
        })
        prompt_id = "environment_appraisal_v36_evidence_grounded_state_interpretation"
        self.assertEqual(_STATE_IMPACT_FAMILY_CAPS_BY_PROMPT[prompt_id], {})
        normalized = _validate_appraisal(
            result,
            allowed_evidence_ids=[],
            state_variables={
                "relationship.perceived_responsiveness",
                "relationship.perceived_fairness",
                "relationship.trust",
            },
            dynamics_variables={"negotiation_open"},
            action_text=action,
            require_impact_evidence=True,
            state_impact_family_caps={},
            require_distinct_family_evidence_spans=False,
            require_nonzero_impact_features=True,
        )
        self.assertEqual(len(normalized["appraisal"]["state_impacts"]), 3)

    def test_parser_repairs_only_missing_terminal_object_close(self):
        value = _parse_json_output('{"appraisal":{"evidence_turn_ids":[]}')
        self.assertEqual(value, {"appraisal": {"evidence_turn_ids": []}})
        with self.assertRaises(Exception):
            _parse_json_output('{"a": tru}')

    def test_parser_repairs_disjoint_fields_after_premature_top_level_close(self):
        diagnostics = []
        value = _parse_json_output(
            '{"appraisal":{}},"evidence_turn_ids":["t1"]}',
            repair_diagnostics=diagnostics,
        )
        self.assertEqual(
            value,
            {"appraisal": {}, "evidence_turn_ids": ["t1"]},
        )
        self.assertEqual(
            diagnostics[0]["operation"],
            "merge_disjoint_trailing_top_level_fields",
        )
        with self.assertRaises(Exception):
            _parse_json_output('{"appraisal":{}},"appraisal":{"x":1}}')
        with self.assertRaises(Exception):
            _parse_json_output('{"appraisal":{}} trailing')

    def test_appraisal_parser_repairs_only_nonstructural_inner_quotes(self):
        raw = (
            '{"evidence_span":"不能把"正在推进"当成已经完成",'
            '"evidence_strength":2}'
        )
        with self.assertRaises(Exception):
            _parse_json_output(raw)
        diagnostics = []
        value = _parse_json_output(
            raw,
            repair_unescaped_interior_quotes=True,
            repair_diagnostics=diagnostics,
        )
        self.assertEqual(
            value["evidence_span"], '不能把"正在推进"当成已经完成'
        )
        self.assertEqual(
            diagnostics[0]["operation"],
            "escape_unescaped_interior_quotes",
        )

    def test_impact_span_rebinds_unique_typographic_quote_variant(self):
        features = {name: 0 for name in FEATURE_NAMES}
        action = "I can’t clear Amaya on this record."
        result = {
            "appraisal": {
                "speaker_intent": "refuse clearance",
                "social_act": "refusal",
                "event_features": features,
                "state_impacts": [{
                    "variable": "consequence_risk.goal_failure_risk",
                    "direction": "increase",
                    "evidence_feature": "goal_alignment",
                    "evidence_span": "I can't clear Amaya on this record",
                    "evidence_strength": 2,
                    "directness": "direct",
                    "new_evidence": True,
                }],
                "dynamics_impacts": [],
            },
            "evidence_turn_ids": [],
        }
        normalized = _validate_appraisal(
            result,
            allowed_evidence_ids=[],
            state_variables={"consequence_risk.goal_failure_risk"},
            dynamics_variables={"deadline_pressure"},
            action_text=action,
            require_impact_evidence=True,
        )
        self.assertEqual(
            normalized["appraisal"]["state_impacts"][0]["evidence_span"],
            "I can’t clear Amaya on this record",
        )

    def test_alias_paths_and_misplaced_dynamics_are_schema_normalized(self):
        value = canonicalize_impact_lists({
            "state_impacts": [
                {
                    "variable": "trust",
                    "citing_feature": "respect_signal",
                    "direction": "increase",
                    "evidence_strength": 1,
                    "directness": "direct",
                    "new_evidence": True,
                },
                {
                    "variable": "negotiation_open",
                    "citing_feature": "goal_alignment",
                    "direction": "increase",
                    "evidence_strength": 1,
                    "directness": "direct",
                    "new_evidence": True,
                },
            ],
            "dynamics_impacts": [],
        }, {"relationship.trust"}, {"negotiation_open"})
        self.assertEqual(
            value["state_impacts"][0]["variable"], "relationship.trust"
        )
        self.assertNotIn("evidence_feature", value["state_impacts"][0])
        self.assertEqual(
            value["dynamics_impacts"][0]["variable"], "negotiation_open"
        )

    def test_v12_preserves_and_validates_explicit_impact_evidence(self):
        features = {name: 0 for name in FEATURE_NAMES}
        features["cooperation_signal"] = 1
        action = "我解释原因，也提出一个可执行方案。"
        result = {
            "appraisal": {
                "speaker_intent": "explain and propose",
                "social_act": "proposal",
                "event_features": features,
                "state_impacts": [{
                    "variable": "relationship.trust",
                    "direction": "increase",
                    "evidence_feature": "cooperation_signal",
                    "evidence_span": "我解释原因",
                    "evidence_strength": 2,
                    "directness": "direct",
                    "new_evidence": True,
                }],
                "dynamics_impacts": [],
            },
            "evidence_turn_ids": [],
        }
        normalized = _validate_appraisal(
            result,
            allowed_evidence_ids=[],
            state_variables={"relationship.trust"},
            dynamics_variables={"negotiation_open"},
            action_text=action,
            require_impact_evidence=True,
        )
        impact_value = normalized["appraisal"]["state_impacts"][0]
        self.assertEqual(
            impact_value["evidence_feature"], "cooperation_signal"
        )
        self.assertEqual(impact_value["evidence_span"], "我解释原因")

        result["appraisal"]["state_impacts"][0]["evidence_span"] = "并不存在的原话"
        with self.assertRaisesRegex(ValueError, "exact latest-action substring"):
            _validate_appraisal(
                result,
                allowed_evidence_ids=[],
                state_variables={"relationship.trust"},
                dynamics_variables={"negotiation_open"},
                action_text=action,
                require_impact_evidence=True,
            )

    def test_v12_rejects_two_candidates_from_one_non_emotion_family(self):
        features = {name: 0 for name in FEATURE_NAMES}
        features["cooperation_signal"] = 2
        action = "我愿意一起核对，也会继续查证。"
        result = {
            "appraisal": {
                "speaker_intent": "cooperate and verify",
                "social_act": "proposal",
                "event_features": features,
                "state_impacts": [
                    {
                        "variable": (
                            "behavioral_disposition.cooperation_readiness"
                        ),
                        "direction": "increase",
                        "evidence_feature": "cooperation_signal",
                        "evidence_span": "我愿意一起核对",
                        "evidence_strength": 2,
                        "directness": "direct",
                        "new_evidence": True,
                    },
                    {
                        "variable": "behavioral_disposition.evidence_seeking",
                        "direction": "increase",
                        "evidence_feature": "cooperation_signal",
                        "evidence_span": "也会继续查证",
                        "evidence_strength": 2,
                        "directness": "direct",
                        "new_evidence": True,
                    },
                ],
                "dynamics_impacts": [],
            },
            "evidence_turn_ids": [],
        }
        with self.assertRaisesRegex(
            ValueError,
            "at most 1 candidate.*behavioral_disposition",
        ):
            _validate_appraisal(
                result,
                allowed_evidence_ids=[],
                state_variables={
                    "behavioral_disposition.cooperation_readiness",
                    "behavioral_disposition.evidence_seeking",
                },
                dynamics_variables={"negotiation_open"},
                action_text=action,
                require_impact_evidence=True,
            )

    def test_nonzero_features_may_preserve_state_with_no_candidate_impacts(self):
        features = {name: 0 for name in FEATURE_NAMES}
        features["pressure"] = 1
        result = {
            "appraisal": {
                "speaker_intent": "request clarification",
                "social_act": "request",
                "event_features": features,
                "state_impacts": [],
                "dynamics_impacts": [],
            },
            "evidence_turn_ids": [],
        }
        normalized = _validate_appraisal(
            result,
            allowed_evidence_ids=[],
            state_variables={"relationship.trust"},
            dynamics_variables={"negotiation_open"},
        )
        self.assertEqual(normalized["appraisal"]["state_impacts"], [])
        self.assertEqual(normalized["appraisal"]["dynamics_impacts"], [])

    def test_nonzero_features_cannot_silently_lose_all_candidate_impacts(self):
        features = {name: 0 for name in FEATURE_NAMES}
        features["cooperation_signal"] = 1
        result = {
            "appraisal": {
                "speaker_intent": "cooperate",
                "social_act": "delivery",
                "event_features": features,
                "state_impacts": [{
                    "direction": "increase",
                    "evidence_strength": 1,
                    "directness": "direct",
                    "new_evidence": True,
                }],
                "dynamics_impacts": [],
            },
            "evidence_turn_ids": [],
        }
        with self.assertRaisesRegex(ValueError, "valid variable path"):
            _validate_appraisal(
                result,
                allowed_evidence_ids=[],
                state_variables={"relationship.trust"},
                dynamics_variables={"negotiation_open"},
            )


    def test_appraisal_downgrades_tentative_commitment_to_proposal(self):
        features = {name: 0 for name in FEATURE_NAMES}
        action = "我明早联系医生确认用药细节。"
        result = {
            "appraisal": {
                "speaker_intent": "propose a next step",
                "social_act": "proposal",
                "event_features": features,
                "state_impacts": [],
                "dynamics_impacts": [],
                "ledger_events": [{
                    "event_type": "commitment",
                    "owner": "evaluated_agent",
                    "action_owner": "evaluated_agent",
                    "evidence_span": "我明早联系医生确认用药细节",
                    "status": "tentative",
                }],
            },
            "evidence_turn_ids": [],
        }
        normalized = _validate_appraisal(
            result,
            allowed_evidence_ids=[],
            state_variables={"relationship.trust"},
            dynamics_variables={"negotiation_open"},
            action_text=action,
            require_ledger_events=True,
            normalize_ledger_noise=True,
        )
        event = normalized["appraisal"]["ledger_events"][0]
        self.assertEqual(
            (event["event_type"], event["status"]), ("proposal", "tentative")
        )

    def test_malformed_diagnostic_claim_is_dropped_without_aborting_appraisal(self):
        features = {name: 0 for name in FEATURE_NAMES}
        action = "原始数据共享是验证它的前提。"
        diagnostics = {
            "substantive_novelty": {
                "label": "new_position", "evidence_span": action,
            },
            "consequential_claims": [{
                "span": "原始数据共享是验证它的前提",
                "impact_domains": ["action_feasibility"],
            }],
            "continuation": {
                "status": "can_close",
                "evidence_span": "",
                "after_direct_response": {
                    "status": "can_close", "evidence_span": action,
                },
            },
        }
        result = {
            "appraisal": {
                "speaker_intent": "state a prerequisite",
                "social_act": "proposal",
                "event_features": features,
                "state_impacts": [],
                "dynamics_impacts": [],
                "dialogue_diagnostics": diagnostics,
            },
            "evidence_turn_ids": [],
        }
        normalized = _validate_appraisal(
            result,
            allowed_evidence_ids=[],
            state_variables={"relationship.trust"},
            dynamics_variables={"negotiation_open"},
            action_text=action,
            require_dialogue_diagnostics=True,
            require_after_direct_response=True,
        )
        self.assertEqual(
            normalized["appraisal"]["dialogue_diagnostics"]
            ["consequential_claims"],
            [],
        )


if __name__ == "__main__":
    def test_social_act_label_variation_falls_back_conservatively(self):
        allowed = {"inform", "concession", "other"}
        self.assertEqual(canonicalize_social_act("acceptance", allowed), "concession")
        self.assertEqual(canonicalize_social_act("unexpected_label", allowed), "other")


    unittest.main()
