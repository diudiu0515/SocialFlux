import unittest

from environment.state_opportunity import (
    STATE_OPPORTUNITY_PROFILE_V2,
    STATE_OPPORTUNITY_PROFILE_V3,
    STATE_OPPORTUNITY_PROFILE_V4,
    STATE_OPPORTUNITY_PROFILE_V5,
    STATE_OPPORTUNITY_PROFILE_V6,
    STATE_OPPORTUNITY_TRIGGER_TURNS,
    STATE_OPPORTUNITY_V3_TRIGGER_TURNS,
    STATE_OPPORTUNITY_V4_TRIGGER_TURNS,
    build_state_transition_opportunity,
)


def scenario():
    return {
        "state_contract_version": "socialflux_state_v2",
        "selected_state_variables": {
            "relationship": ["perceived_responsiveness", "trust"],
        },
        "initialization_notes": {
            "rationale": {
                "relationship": {
                    "perceived_responsiveness": "Initial responsiveness rationale.",
                    "trust": "Initial trust rationale.",
                },
            },
            "state_transition_plan": {
                "relationship.perceived_responsiveness": {
                    "increase_evidence": "responsive increase example",
                    "decrease_evidence": "responsive decrease example",
                },
                "relationship.trust": {
                    "increase_evidence": "trust increase example",
                    "decrease_evidence": "trust decrease example",
                },
            },
        },
    }


class StateTransitionOpportunityTest(unittest.TestCase):
    def test_sparse_trigger_exposes_one_optional_slow_path(self):
        value = build_state_transition_opportunity(
            scenario(), [], {}, STATE_OPPORTUNITY_TRIGGER_TURNS[0]
        )
        self.assertTrue(value["active"])
        self.assertEqual(value["selected_path"], "relationship.trust")
        self.assertEqual(value["increase_example"], "trust increase example")
        self.assertIn("optional opportunity only", value["guardrails"][0])

    def test_off_cadence_is_inactive(self):
        value = build_state_transition_opportunity(scenario(), [], {}, 7)
        self.assertFalse(value["active"])
        self.assertEqual(value["reason"], "off_sparse_trigger_cadence")

    def test_prior_slow_change_disables_later_opportunities(self):
        turns = [{
            "numeric_state_delta": {
                "relationship": {"trust": 1},
            },
        }]
        value = build_state_transition_opportunity(
            scenario(), turns, {}, STATE_OPPORTUNITY_TRIGGER_TURNS[1]
        )
        self.assertFalse(value["active"])
        self.assertEqual(value["reason"], "slow_transition_already_realized")

    def test_current_turn_slow_change_disables_opportunity(self):
        value = build_state_transition_opportunity(
            scenario(),
            [],
            {"relationship": {"trust": -1}},
            STATE_OPPORTUNITY_TRIGGER_TURNS[0],
        )
        self.assertFalse(value["active"])
        self.assertEqual(value["reason"], "slow_transition_already_realized")

    def test_v2_follows_an_unresolved_slow_evidence_strand(self):
        turns = [{
            "turn_id": "t9",
            "numeric_state_delta": {
                "relationship": {
                    "perceived_responsiveness": 1,
                    "trust": 0,
                },
            },
            "calibration": {
                "state_impacts": [{
                    "variable": "relationship.trust",
                    "direction": "increase",
                    "timescale": "cross_turn_slow",
                    "explicit_evidence": True,
                    "feature_compatible": True,
                    "new_evidence": True,
                    "calibrated_level": 1,
                    "evidence_feature": "commitment_signal",
                    "evidence_span": "first independent observation",
                }],
            },
        }]
        value = build_state_transition_opportunity(
            scenario(),
            turns,
            {},
            STATE_OPPORTUNITY_TRIGGER_TURNS[1],
            profile=STATE_OPPORTUNITY_PROFILE_V2,
        )
        self.assertTrue(value["active"])
        self.assertEqual(value["profile"], STATE_OPPORTUNITY_PROFILE_V2)
        self.assertEqual(value["selected_path"], "relationship.trust")
        self.assertEqual(value["selection_basis"], "existing_unresolved_slow_evidence")
        self.assertEqual(value["evidence_stage"], "independent_followup")
        self.assertEqual(value["prior_candidate_count"], 1)
        self.assertEqual(value["prior_candidate_turn_ids"], ["t9"])
        self.assertNotIn("prior_direction", value)
        self.assertIn("answer freely", value["followup_guidance"])

    def test_v3_offers_earlier_non_forcing_probe_for_natural_window(self):
        value = build_state_transition_opportunity(
            scenario(), [], {}, STATE_OPPORTUNITY_V3_TRIGGER_TURNS[0],
            profile=STATE_OPPORTUNITY_PROFILE_V3,
        )
        self.assertTrue(value["active"])
        self.assertEqual(value["turn_id"], 6)
        self.assertEqual(
            value["trigger_turns"],
            list(STATE_OPPORTUNITY_V3_TRIGGER_TURNS),
        )
        self.assertNotIn("state_delta", value)
        self.assertNotIn("requested_direction", value)

    def test_v2_never_creates_a_state_delta(self):
        value = build_state_transition_opportunity(
            scenario(),
            [],
            {},
            STATE_OPPORTUNITY_TRIGGER_TURNS[0],
            profile=STATE_OPPORTUNITY_PROFILE_V2,
        )
        self.assertTrue(value["active"])
        self.assertNotIn("state_delta", value)
        self.assertNotIn("requested_direction", value)
        self.assertEqual(value["evidence_stage"], "open_probe")
    def test_v4_has_two_usable_opportunities_before_natural_turn_ten(self):
        self.assertEqual(STATE_OPPORTUNITY_V4_TRIGGER_TURNS[:2], (4, 7))
        for turn_id in STATE_OPPORTUNITY_V4_TRIGGER_TURNS[:2]:
            value = build_state_transition_opportunity(
                scenario(), [], {}, turn_id,
                profile=STATE_OPPORTUNITY_PROFILE_V4,
            )
            self.assertTrue(value["active"])
            self.assertNotIn("state_delta", value)
            self.assertNotIn("requested_direction", value)

    def test_v5_is_event_driven_on_arbitrary_turns_without_selecting_direction(self):
        for turn_id in (2, 5, 9):
            value = build_state_transition_opportunity(
                scenario(), [], {}, turn_id,
                profile=STATE_OPPORTUNITY_PROFILE_V5,
            )
            self.assertTrue(value["active"])
            self.assertEqual(value["activation_mode"], "event_driven_prompt")
            self.assertEqual(value["trigger_turns"], [])
            self.assertEqual(value["evidence_stage"], "open_probe")
            self.assertNotIn("selected_path", value)
            self.assertNotIn("increase_example", value)
            self.assertNotIn("decrease_example", value)
            self.assertNotIn("requested_direction", value)
            self.assertEqual(
                [item["path"] for item in value["eligible_constructs"]],
                ["relationship.trust"],
            )

    def test_v5_reports_unresolved_evidence_without_exposing_direction(self):
        turns = [{
            "turn_id": "t3",
            "calibration": {
                "state_impacts": [{
                    "variable": "relationship.trust",
                    "direction": "decrease",
                    "timescale": "cross_turn_slow",
                    "explicit_evidence": True,
                    "feature_compatible": True,
                    "new_evidence": True,
                    "calibrated_level": 1,
                    "evidence_feature": "commitment_signal",
                    "evidence_span": "one grounded observation",
                }],
            },
        }]
        value = build_state_transition_opportunity(
            scenario(), turns, {}, 4,
            profile=STATE_OPPORTUNITY_PROFILE_V5,
        )
        self.assertEqual(value["evidence_stage"], "independent_followup")
        self.assertEqual(
            value["eligible_constructs"][0]["candidate_turn_ids"], ["t3"]
        )
        self.assertNotIn("direction", value["eligible_constructs"][0])
        self.assertNotIn("prior_direction", value)

    def test_v5_stops_prompting_after_a_realized_slow_transition(self):
        turns = [{
            "numeric_state_delta": {"relationship": {"trust": 1}},
        }]
        value = build_state_transition_opportunity(
            scenario(), turns, {}, 3,
            profile=STATE_OPPORTUNITY_PROFILE_V5,
        )
        self.assertFalse(value["active"])
        self.assertEqual(value["reason"], "slow_transition_already_realized")
        self.assertEqual(value["trigger_turns"], [])

    def test_v6_adds_direction_neutral_scenario_patterns_without_cadence(self):
        value = build_state_transition_opportunity(
            scenario(), [], {}, 3, profile=STATE_OPPORTUNITY_PROFILE_V6
        )
        self.assertTrue(value["active"])
        self.assertEqual(value["trigger_turns"], [])
        patterns = value["eligible_constructs"][0][
            "scenario_evidence_patterns"
        ]
        self.assertEqual(patterns, [
            "trust increase example", "trust decrease example"
        ])
        self.assertNotIn("selected_path", value)
        self.assertNotIn("requested_direction", value)

    def test_v4_rotates_slow_paths_when_no_candidate_was_observed(self):
        value = scenario()
        value["selected_state_variables"]["relationship"].append(
            "perceived_safety"
        )
        value["initialization_notes"]["state_transition_plan"][
            "relationship.perceived_safety"
        ] = {
            "increase_evidence": "safety increase example",
            "decrease_evidence": "safety decrease example",
        }
        first = build_state_transition_opportunity(
            value, [], {}, 4,
            profile=STATE_OPPORTUNITY_PROFILE_V4,
        )
        second = build_state_transition_opportunity(
            value, [], {}, 7,
            profile=STATE_OPPORTUNITY_PROFILE_V4,
        )
        self.assertNotEqual(first["selected_path"], second["selected_path"])



if __name__ == "__main__":
    unittest.main()
