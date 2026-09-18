import unittest

from environment.appraisal import _validate_appraisal
from environment.appraisal_normalization import (
    canonicalize_impact_lists,
    canonicalize_social_act,
)
from environment.calibration import FEATURE_NAMES
from providers.structured import _parse_json_output


class StructuredAppraisalNormalizationTest(unittest.TestCase):
    def test_parser_repairs_only_missing_terminal_object_close(self):
        value = _parse_json_output('{"appraisal":{"evidence_turn_ids":[]}')
        self.assertEqual(value, {"appraisal": {"evidence_turn_ids": []}})
        with self.assertRaises(Exception):
            _parse_json_output('{"a": tru}')

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
