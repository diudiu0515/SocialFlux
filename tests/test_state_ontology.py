import unittest

from environment.prompts import build_appraisal_prompt
from environment.state_ontology import (
    EVIDENCE_FEATURE_COMPATIBILITY,
    EVIDENCE_FEATURE_DIRECTION_RULES,
    FAMILY_RULES,
    STATE_ONTOLOGY_VERSION,
    STATE_VARIABLE_ONTOLOGY,
    build_state_semantics,
)


class StateOntologyTest(unittest.TestCase):
    def setUp(self):
        self.scenario = {
            "state_contract_version": "socialflux_state_v2",
            "selected_state_variables": {
                "emotion": ["anxiety"],
                "behavioral_disposition": ["cooperation_readiness"],
                "relationship": ["trust"],
                "consequence_risk": ["goal_failure_risk"],
            },
            "initialization_notes": {
                "rationale": {
                    "emotion": {
                        "anxiety": "The unresolved deadline supports anxiety."
                    },
                    "behavioral_disposition": (
                        "Cooperation remains conditional."
                    ),
                    "relationship": {
                        "trust": "Prior follow-through was mixed."
                    },
                    "consequence_risk": {
                        "goal_failure_risk": "A required approval is missing."
                    },
                }
            },
        }

    def test_selected_paths_receive_operational_semantics(self):
        result = build_state_semantics(self.scenario)
        self.assertEqual(len(result["variables"]), 4)
        self.assertEqual(result["ontology_version"], STATE_ONTOLOGY_VERSION)
        anxiety = result["variables"]["emotion.anxiety"]
        self.assertEqual(anxiety["timescale"], "turn_local")
        self.assertIn("pressure", anxiety["evidence_features"])
        self.assertIn("starting value only", result["interpretation"])
        self.assertEqual(
            anxiety["scenario_initialization_rationale"],
            "The unresolved deadline supports anxiety.",
        )
        self.assertEqual(
            result["variables"][
                "behavioral_disposition.cooperation_readiness"
            ]["scenario_initialization_rationale"],
            "Cooperation remains conditional.",
        )

    def test_every_ontology_entry_has_family_rule_and_evidence_directions(self):
        self.assertGreaterEqual(len(STATE_VARIABLE_ONTOLOGY), 32)
        for path, entry in STATE_VARIABLE_ONTOLOGY.items():
            family = path.split(".", 1)[0]
            self.assertIn(family, FAMILY_RULES)
            self.assertTrue(entry["definition"])
            self.assertTrue(entry["increase_evidence"])
            self.assertTrue(entry["decrease_evidence"])
            self.assertTrue(entry["non_evidence"])
            self.assertTrue(EVIDENCE_FEATURE_COMPATIBILITY[path])

    def test_disclosure_willingness_accepts_explicit_commitment_evidence(self):
        self.assertIn(
            "commitment_signal",
            EVIDENCE_FEATURE_COMPATIBILITY[
                "behavioral_disposition.disclosure_willingness"
            ],
        )

    def test_disclosure_direction_rules_reject_observed_mismatches(self):
        rules = EVIDENCE_FEATURE_DIRECTION_RULES[
            "behavioral_disposition.disclosure_willingness"
        ]
        self.assertEqual(rules["increase"]["commitment_signal"], "positive")
        self.assertNotIn("pressure", rules["increase"])
        self.assertEqual(rules["decrease"]["commitment_signal"], "negative")
        self.assertEqual(rules["decrease"]["pressure"], "positive")

    def test_turn_responsive_relationship_state_overrides_family_timescale(self):
        self.scenario["selected_state_variables"]["relationship"] = [
            "perceived_responsiveness"
        ]
        result = build_state_semantics(self.scenario)
        self.assertEqual(
            result["variables"][
                "relationship.perceived_responsiveness"
            ]["timescale"],
            "turn_to_episode",
        )

    def test_scenario_transition_plan_is_private_matching_guidance(self):
        self.scenario["initialization_notes"]["state_transition_plan"] = {
            "emotion.anxiety": {
                "increase_evidence": "A new deadline threat becomes credible.",
                "decrease_evidence": "A verified extension removes the threat.",
            }
        }
        result = build_state_semantics(self.scenario)
        self.assertEqual(
            result["variables"]["emotion.anxiety"][
                "scenario_transition_evidence"
            ]["decrease_evidence"],
            "A verified extension removes the threat.",
        )
        self.assertIn("not observed evidence", result["interpretation"])

    def test_private_appraisal_payload_contains_state_semantics(self):
        self.scenario["initialization_notes"]["state_transition_plan"] = {
            "emotion.anxiety": {
                "increase_evidence": "A new deadline threat becomes credible.",
                "decrease_evidence": "A verified extension removes the threat.",
            }
        }
        semantics = build_state_semantics(self.scenario)
        rendered = build_appraisal_prompt(
            persona={},
            background="background",
            explicit_goal="goal",
            hidden_intention="hidden",
            previous_state={
                "emotion": {"anxiety": 5},
                "behavioral_disposition": {
                    "cooperation_readiness": 5
                },
                "relationship": {"trust": 5},
                "consequence_risk": {"goal_failure_risk": 5},
            },
            previous_dynamics={"deadline_pressure": 5},
            memory={},
            action={"text": "请先核对记录。"},
            state_semantics=semantics,
            prompt_id="environment_appraisal_v12",
        )
        self.assertIn('"state_semantics"', rendered)
        self.assertIn(
            "Current level and current delta are distinct", rendered
        )
        self.assertIn(
            "The unresolved deadline supports anxiety.", rendered
        )
        self.assertIn(
            "A verified extension removes the threat.", rendered
        )


if __name__ == "__main__":
    unittest.main()
