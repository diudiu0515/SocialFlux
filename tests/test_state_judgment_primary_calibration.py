import unittest

from environment.calibration import DeterministicStateCalibrator, FEATURE_NAMES
from environment.independent_appraisal import _validate_judgments
from environment.state_ontology import build_state_semantics


PROFILE = "state_judgment_primary_hysteretic_v7"


def scenario(*, timescales=None):
    notes = {"rationale": {}, "state_transition_plan": {}}
    if timescales:
        notes["state_timescales"] = dict(timescales)
    return {
        "environment_agent": {"persona": {}},
        "selected_state_variables": {
            "relationship": ["trust"],
        },
        "initial_state": {"relationship": {"trust": 4}},
        "initialization_notes": notes,
    }


def impact(*, direction="increase", strength=2, directness="direct",
           feature="commitment_signal", span="已验证的可靠行为"):
    return {
        "variable": "relationship.trust",
        "direction": direction,
        "evidence_feature": feature,
        "evidence_span": span,
        "evidence_strength": strength,
        "directness": directness,
        "new_evidence": True,
    }


def appraisal(item, *, feature_value=2, novelty=None, dynamics=None):
    features = {
        "goal_alignment": 0,
        "cooperation_signal": 0,
        "repair_signal": 0,
        "pressure": 0,
        "face_threat": 0,
        "commitment_signal": 0,
        "uncertainty_reduction": 0,
        "boundary_violation": 0,
        "respect_signal": 0,
        "withdrawal_signal": 0,
    }
    features[item["evidence_feature"]] = feature_value
    value = {
        "event_features": features,
        "state_impacts": [item],
        "dynamics_impacts": list(dynamics or []),
    }
    if novelty is not None:
        value["dialogue_diagnostics"] = {
            "substantive_novelty": {"label": novelty}
        }
    return value


class StateJudgmentPrimaryCalibrationTest(unittest.TestCase):
    def test_decisive_state_result_is_invariant_to_dialogue_diagnostic(self):
        outputs = []
        for novelty in ("new_decision", "new_explanation", None, "none"):
            result = DeterministicStateCalibrator(
                scenario(), profile=PROFILE
            ).calibrate(
                appraisal(impact(), novelty=novelty),
                {"relationship": {"trust": 4}},
                {},
            )
            outputs.append(result["state_delta"]["relationship"]["trust"])
            self.assertFalse(
                result["calibration"]["dialogue_diagnostics_gate_enforced"]
            )
        self.assertEqual(outputs, ["moderate_increase"] * 4)

    def test_feature_is_auxiliary_not_a_second_semantic_gate(self):
        outputs = []
        for value in (2, 1, 0):
            candidate = impact(feature="uncertainty_reduction")
            result = DeterministicStateCalibrator(
                scenario(), profile=PROFILE
            ).calibrate(
                appraisal(candidate, feature_value=value),
                {"relationship": {"trust": 4}},
                {},
            )
            diagnostic = result["calibration"]["state_impacts"][0]
            outputs.append(result["state_delta"]["relationship"]["trust"])
            self.assertEqual(diagnostic["feature_role"], "auxiliary_diagnostic")
            self.assertFalse(diagnostic["feature_compatible"])
        self.assertEqual(outputs, ["moderate_increase"] * 3)

    def test_surface_duplicate_does_not_globally_veto_state_or_dynamics(self):
        dynamic = {
            "variable": "negotiation_openness",
            "direction": "increase",
            "evidence_feature": "cooperation_signal",
            "evidence_span": "继续协作",
            "evidence_strength": 1,
            "directness": "direct",
            "new_evidence": True,
        }
        value = appraisal(
            impact(), feature_value=0, novelty="none", dynamics=[dynamic]
        )
        value["event_features"]["cooperation_signal"] = 1
        result = DeterministicStateCalibrator(
            scenario(), profile=PROFILE
        ).calibrate(
            value,
            {"relationship": {"trust": 4}},
            {"negotiation_openness": 4},
            surface_duplicate_evidence_ids=["t1"],
        )
        self.assertEqual(
            result["state_delta"]["relationship"]["trust"],
            "moderate_increase",
        )
        self.assertEqual(
            result["interaction_dynamics_delta"]["negotiation_openness"],
            "mild_increase",
        )
        self.assertFalse(result["calibration"]["semantic_no_change_enforced"])

    def test_legacy_global_suppression_log_matches_actual_delta(self):
        value = appraisal(impact(), novelty="none")
        result = DeterministicStateCalibrator(
            scenario(), profile="evidence_causal_slow_priority_hysteretic_v6"
        ).calibrate(value, {"relationship": {"trust": 4}}, {})
        diagnostic = result["calibration"]["state_impacts"][0]
        self.assertEqual(
            result["state_delta"]["relationship"]["trust"], "similar"
        )
        self.assertFalse(diagnostic["selected"])
        self.assertEqual(diagnostic["final_delta"], "similar")
        self.assertEqual(diagnostic["selection_reason"], "semantic_novelty_none")

    def test_every_new_ordinary_slow_evidence_updates_immediately(self):
        calibrator = DeterministicStateCalibrator(scenario(), profile=PROFILE)
        first = calibrator.calibrate(
            appraisal(impact(strength=1, span="第一项独立证据"), feature_value=0),
            {"relationship": {"trust": 4}}, {}, current_event_id="t1",
        )
        second = calibrator.calibrate(
            appraisal(impact(strength=1, span="第二项独立证据"), feature_value=0),
            {"relationship": {"trust": 5}}, {}, current_event_id="t2",
        )
        third = calibrator.calibrate(
            appraisal(impact(strength=1, span="第三项独立证据"), feature_value=0),
            {"relationship": {"trust": 6}}, {}, current_event_id="t3",
        )
        self.assertEqual(first["state_delta"]["relationship"]["trust"], "mild_increase")
        self.assertEqual(second["state_delta"]["relationship"]["trust"], "mild_increase")
        self.assertEqual(third["state_delta"]["relationship"]["trust"], "mild_increase")
        for event_id, result in (("t1", first), ("t2", second), ("t3", third)):
            diagnostic = result["calibration"]["state_impacts"][0]
            self.assertEqual(diagnostic["slow_evidence_consumed_ids"], [event_id])
            self.assertEqual(diagnostic["slow_evidence_pending_after"], 0)
            self.assertFalse(result["calibration"]["slow_evidence_history"])
        self.assertEqual(
            third["calibration"]["slow_evidence_consumed_history"][
                "relationship.trust"
            ], ["t1", "t2", "t3"],
        )

    def test_opposite_new_evidence_also_updates_immediately(self):
        calibrator = DeterministicStateCalibrator(scenario(), profile=PROFILE)
        calibrator.calibrate(
            appraisal(impact(strength=1, span="正向一"), feature_value=0),
            {"relationship": {"trust": 4}}, {}, current_event_id="t1",
        )
        opposite = calibrator.calibrate(
            appraisal(
                impact(direction="decrease", strength=1, span="反向一"),
                feature_value=0,
            ),
            {"relationship": {"trust": 4}}, {}, current_event_id="t2",
        )
        history = opposite["calibration"]["slow_evidence_history"]
        self.assertFalse(history)
        self.assertEqual(
            opposite["state_delta"]["relationship"]["trust"], "mild_decrease"
        )
        opposite_diag = opposite["calibration"]["state_impacts"][0]
        self.assertEqual(opposite_diag["opposite_pending_cleared_ids"], [])

    def test_consumed_slow_event_cannot_be_reintroduced(self):
        calibrator = DeterministicStateCalibrator(scenario(), profile=PROFILE)
        calibrator.calibrate(
            appraisal(impact(strength=1, span="第一项独立证据"), feature_value=0),
            {"relationship": {"trust": 4}}, {}, current_event_id="t1",
        )
        calibrator.calibrate(
            appraisal(impact(strength=1, span="第二项独立证据"), feature_value=0),
            {"relationship": {"trust": 4}}, {}, current_event_id="t2",
        )
        replay = calibrator.calibrate(
            appraisal(impact(strength=1, span="第二项独立证据"), feature_value=0),
            {"relationship": {"trust": 5}}, {}, current_event_id="t2",
        )
        diagnostic = replay["calibration"]["state_impacts"][0]
        self.assertEqual(
            replay["state_delta"]["relationship"]["trust"], "similar"
        )
        self.assertEqual(
            diagnostic["selection_reason"], "slow_evidence_already_consumed"
        )
        self.assertTrue(diagnostic["slow_evidence_replayed_consumed"])
        self.assertNotIn(
            "relationship.trust:increase",
            replay["calibration"]["slow_evidence_history"],
        )
        self.assertEqual(
            replay["calibration"]["slow_evidence_consumed_history"][
                "relationship.trust"
            ],
            ["t1", "t2"],
        )

    def test_strength_changes_magnitude_not_eligibility(self):
        ordinary = DeterministicStateCalibrator(
            scenario(), profile=PROFILE
        ).calibrate(
            appraisal(impact(strength=1), feature_value=0),
            {"relationship": {"trust": 4}}, {}, current_event_id="t1",
        )
        decisive = DeterministicStateCalibrator(
            scenario(), profile=PROFILE
        ).calibrate(
            appraisal(impact(strength=2), feature_value=0),
            {"relationship": {"trust": 4}}, {}, current_event_id="t1",
        )
        self.assertEqual(
            ordinary["state_delta"]["relationship"]["trust"], "mild_increase"
        )
        self.assertEqual(
            decisive["state_delta"]["relationship"]["trust"],
            "moderate_increase",
        )
        self.assertTrue(
            ordinary["calibration"]["new_evidence_updates_immediately"]
        )
        self.assertEqual(
            ordinary["calibration"]["slow_transition_rule"],
            "any_valid_new_evidence_updates_with_minimum_delta",
        )
        self.assertTrue(
            ordinary["calibration"]["all_eligible_new_evidence_updates"]
        )

    def test_multiple_valid_variables_in_one_family_are_not_budget_vetoed(self):
        value = scenario()
        value["selected_state_variables"]["relationship"].append(
            "perceived_fairness"
        )
        value["initial_state"]["relationship"]["perceived_fairness"] = 4
        trust = impact(strength=1, span="新的可靠行为")
        fairness = {
            **impact(strength=1, span="新的公平程序"),
            "variable": "relationship.perceived_fairness",
            "evidence_feature": "respect_signal",
        }
        state_appraisal = appraisal(trust, feature_value=0)
        state_appraisal["state_impacts"].append(fairness)
        result = DeterministicStateCalibrator(
            value, profile=PROFILE
        ).calibrate(
            state_appraisal,
            {
                "relationship": {
                    "trust": 4,
                    "perceived_fairness": 4,
                },
            },
            {},
            current_event_id="t1",
        )
        self.assertEqual(
            result["state_delta"]["relationship"]["trust"], "mild_increase"
        )
        self.assertEqual(
            result["state_delta"]["relationship"]["perceived_fairness"],
            "mild_increase",
        )

    def test_indirect_new_evidence_still_gets_minimum_delta(self):
        result = DeterministicStateCalibrator(
            scenario(), profile=PROFILE
        ).calibrate(
            appraisal(
                impact(strength=1, directness="indirect"),
                feature_value=0,
            ),
            {"relationship": {"trust": 4}}, {}, current_event_id="t1",
        )
        self.assertEqual(
            result["state_delta"]["relationship"]["trust"], "mild_increase"
        )

    def test_new_ordinary_evidence_is_not_blocked_by_reinforcement_plateau(self):
        result = DeterministicStateCalibrator(
            scenario(), profile=PROFILE
        ).calibrate(
            appraisal(impact(strength=1), feature_value=0),
            {"relationship": {"trust": 6}}, {}, current_event_id="t1",
        )
        diagnostic = result["calibration"]["state_impacts"][0]
        self.assertEqual(
            result["state_delta"]["relationship"]["trust"], "mild_increase"
        )
        self.assertEqual(
            diagnostic["selection_reason"],
            "selected_valid_new_evidence_immediate",
        )

    def test_no_or_repeated_evidence_does_not_update(self):
        calibrator = DeterministicStateCalibrator(scenario(), profile=PROFILE)
        no_evidence = calibrator.calibrate(
            {
                "event_features": {name: 0 for name in FEATURE_NAMES},
                "state_impacts": [],
                "dynamics_impacts": [],
            },
            {"relationship": {"trust": 4}}, {}, current_event_id="t1",
        )
        repeated_item = impact(strength=2)
        repeated_item["new_evidence"] = False
        repeated = calibrator.calibrate(
            appraisal(repeated_item, feature_value=0),
            {"relationship": {"trust": 4}}, {}, current_event_id="t2",
        )
        self.assertEqual(
            no_evidence["state_delta"]["relationship"]["trust"], "similar"
        )
        self.assertEqual(
            repeated["state_delta"]["relationship"]["trust"], "similar"
        )
        self.assertEqual(
            repeated["calibration"]["state_impacts"][0]["selection_reason"],
            "no_calibrated_change",
        )

    def test_unmapped_auxiliary_feature_can_be_null(self):
        item = {
            "variable": "relationship.trust",
            "judgment": "decisive_new_evidence",
            "direction": "increase",
            "evidence_span": "主动披露了对自己不利的事实",
            "directness": "direct",
            "evidence_feature": None,
            "rationale": "有代价的坦诚改变了对可靠性的判断。",
        }
        diagnostics, impacts = _validate_judgments(
            [item],
            ["relationship.trust"],
            "我主动披露了对自己不利的事实。",
            {"relationship.trust": {"evidence_features": []}},
            {name: 0 for name in FEATURE_NAMES},
            "state_judgments",
        )
        self.assertEqual(
            diagnostics[0]["feature_interface_validation"],
            "unmapped_auxiliary_feature",
        )
        result = DeterministicStateCalibrator(
            scenario(), profile=PROFILE
        ).calibrate(
            {
                "event_features": {name: 0 for name in FEATURE_NAMES},
                "state_impacts": impacts,
                "dynamics_impacts": [],
            },
            {"relationship": {"trust": 4}}, {}, current_event_id="t1",
        )
        self.assertEqual(
            result["state_delta"]["relationship"]["trust"],
            "moderate_increase",
        )
        self.assertIsNone(
            result["calibration"]["state_impacts"][0]["evidence_feature"]
        )

    def test_scenario_can_override_one_variable_timescale_explicitly(self):
        value = scenario(timescales={"relationship.trust": "turn_to_episode"})
        semantics = build_state_semantics(value)["variables"]["relationship.trust"]
        self.assertEqual(semantics["timescale"], "turn_to_episode")
        self.assertEqual(semantics["timescale_source"], "scenario_override")
        result = DeterministicStateCalibrator(value, profile=PROFILE).calibrate(
            appraisal(impact(strength=1), feature_value=0),
            {"relationship": {"trust": 4}}, {}, current_event_id="t1",
        )
        self.assertEqual(
            result["state_delta"]["relationship"]["trust"], "mild_increase"
        )


if __name__ == "__main__":
    unittest.main()
