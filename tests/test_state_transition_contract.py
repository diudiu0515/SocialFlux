import unittest
from copy import deepcopy

from environment.factory import ModelEnvironmentFactory
from environment.state_transition_contract import (
    STATE_TRANSITION_STANDARD_V3,
    STATE_V3_BEHAVIORAL_EVIDENCE_RUNTIME_REVISION,
    STATE_V3_CAUSAL_RUNTIME_REVISION,
    STATE_V3_DECISION_CONTINUITY_RUNTIME_REVISION,
    STATE_V3_DIRECTIONAL_EVIDENCE_RUNTIME_REVISION,
    STATE_V3_ENVIRONMENT_OWNED_RUNTIME_REVISION,
    STATE_V3_EVENT_DRIVEN_RUNTIME_REVISION,
    STATE_V3_SLOW_RECALL_RUNTIME_REVISION,
    STATE_V3_SLOW_AUDIT_RUNTIME_REVISION,
    STATE_V3_SLOW_FIRST_RUNTIME_REVISION,
    STATE_V3_SEMANTIC_EVENT_RUNTIME_REVISION,
    STATE_V3_CONTRASTIVE_EVENT_RUNTIME_REVISION,
    STATE_V3_FEATURE_CONSISTENT_RUNTIME_REVISION,
    STATE_V3_EARLY_OPPORTUNITY_RUNTIME_REVISION,
    STATE_V3_NATURAL_RUNTIME_REVISION,
    STATE_V3_RUNTIME_REVISION,
    STATE_V3_STABLE_ENVIRONMENT_OWNED_RUNTIME_REVISION,
    STATE_V3_STATE_JUDGMENT_PRIMARY_CALIBRATION_PROFILE,
    STATE_V3_STATE_JUDGMENT_PRIMARY_RUNTIME_REVISION,
    STATE_V3_STAGE_ORDER,
    validate_state_transition_environment_config,
    validate_state_v3_scenario,
)


def state_v3_scenario():
    selected = {
        "emotion": ["anxiety", "frustration", "hope"],
        "behavioral_disposition": ["decision_readiness", "evidence_seeking"],
        "relationship": ["perceived_responsiveness", "trust"],
        "consequence_risk": ["goal_failure_risk", "decision_error_risk"],
    }
    paths = [
        f"{family}.{variable}"
        for family, variables in selected.items()
        for variable in variables
    ]
    values = [3, 4, 5, 6, 7, 4, 5, 6, 7]
    initial = {}
    rationale = {}
    for family, variables in selected.items():
        initial[family] = {}
        rationale[family] = {}
        for variable in variables:
            path = f"{family}.{variable}"
            initial[family][variable] = values[paths.index(path)]
            rationale[family][variable] = f"Grounded S0 rationale for {path}."
    return {
        "scenario_id": "S_V3",
        "state_contract_version": "socialflux_state_v2",
        "state_ontology_version": "socialflux_state_ontology_v3",
        "selected_state_variables": selected,
        "target_state_ids": paths[:3] + [paths[3], paths[5], paths[7]],
        "initial_state": initial,
        "initialization_notes": {
            "rationale": rationale,
            "state_transition_plan": {
                path: {
                    "increase_evidence": f"new evidence increasing {path}",
                    "decrease_evidence": f"new evidence decreasing {path}",
                }
                for path in paths
            },
        },
    }


def state_v3_environment():
    return {
        "state_transition_standard": STATE_TRANSITION_STANDARD_V3,
        "appraisal_prompt_id": "environment_appraisal_v15",
        "response_prompt_id": "environment_response_v26",
        "state_calibration_profile": "evidence_independent_hysteretic_v3",
        "horizon_mode": "natural_max_20",
        "minimum_natural_turns": 20,
    }


def state_v3_1_environment():
    value = state_v3_environment()
    value["state_transition_runtime_revision"] = STATE_V3_RUNTIME_REVISION
    value["response_prompt_id"] = "environment_response_v27"
    return value


def state_v3_2_environment():
    value = state_v3_1_environment()
    value["state_transition_runtime_revision"] = (
        STATE_V3_NATURAL_RUNTIME_REVISION
    )
    value["minimum_natural_turns"] = 10
    return value


def state_v3_2_1_environment():
    value = state_v3_2_environment()
    value["state_transition_runtime_revision"] = (
        STATE_V3_STABLE_ENVIRONMENT_OWNED_RUNTIME_REVISION
    )
    value["appraisal_prompt_id"] = (
        "environment_appraisal_v15_environment_owned"
    )
    value["state_calibration_profile"] = "evidence_causal_hysteretic_v5"
    return value


def state_v3_2_2_environment():
    value = state_v3_2_1_environment()
    value["state_transition_runtime_revision"] = (
        STATE_V3_DECISION_CONTINUITY_RUNTIME_REVISION
    )
    value["response_prompt_id"] = (
        "environment_response_v27_decision_continuity"
    )
    return value


def state_v3_2_3_environment():
    value = state_v3_2_1_environment()
    value["state_transition_runtime_revision"] = (
        STATE_V3_EVENT_DRIVEN_RUNTIME_REVISION
    )
    value["response_prompt_id"] = "environment_response_v29_event_driven"
    return value


def state_v3_2_4_environment():
    value = state_v3_2_3_environment()
    value["state_transition_runtime_revision"] = (
        STATE_V3_SLOW_RECALL_RUNTIME_REVISION
    )
    value["appraisal_prompt_id"] = (
        "environment_appraisal_v20_slow_evidence_recall"
    )
    return value


def state_v3_2_5_environment():
    value = state_v3_2_4_environment()
    value["state_transition_runtime_revision"] = (
        STATE_V3_SLOW_AUDIT_RUNTIME_REVISION
    )
    value["appraisal_prompt_id"] = (
        "environment_appraisal_v21_slow_candidate_audit"
    )
    return value


def state_v3_2_6_environment():
    value = state_v3_2_5_environment()
    value["state_transition_runtime_revision"] = (
        STATE_V3_SLOW_FIRST_RUNTIME_REVISION
    )
    value["appraisal_prompt_id"] = "environment_appraisal_v22_slow_first"
    return value


def state_v3_2_7_environment():
    value = state_v3_2_6_environment()
    value["state_transition_runtime_revision"] = (
        STATE_V3_SEMANTIC_EVENT_RUNTIME_REVISION
    )
    value["response_prompt_id"] = (
        "environment_response_v30_semantic_event_driven"
    )
    return value


def state_v3_2_8_environment():
    value = state_v3_2_7_environment()
    value["state_transition_runtime_revision"] = (
        STATE_V3_CONTRASTIVE_EVENT_RUNTIME_REVISION
    )
    value["response_prompt_id"] = (
        "environment_response_v31_contrastive_event_driven"
    )
    return value


def state_v3_2_9_environment():
    value = state_v3_2_8_environment()
    value["state_transition_runtime_revision"] = (
        STATE_V3_FEATURE_CONSISTENT_RUNTIME_REVISION
    )
    value["appraisal_prompt_id"] = (
        "environment_appraisal_v23_feature_consistent_slow_first"
    )
    return value


def state_v3_3_environment():
    value = state_v3_2_environment()
    value["state_transition_runtime_revision"] = (
        STATE_V3_EARLY_OPPORTUNITY_RUNTIME_REVISION
    )
    value["response_prompt_id"] = "environment_response_v28"
    return value


def state_v3_4_environment():
    value = state_v3_3_environment()
    value["state_transition_runtime_revision"] = (
        STATE_V3_BEHAVIORAL_EVIDENCE_RUNTIME_REVISION
    )
    value["appraisal_prompt_id"] = "environment_appraisal_v16"
    return value


def state_v3_5_environment():
    value = state_v3_4_environment()
    value["state_transition_runtime_revision"] = (
        STATE_V3_DIRECTIONAL_EVIDENCE_RUNTIME_REVISION
    )
    value["appraisal_prompt_id"] = "environment_appraisal_v17"
    value["state_calibration_profile"] = (
        "evidence_independent_directional_hysteretic_v4"
    )
    return value


def state_v3_6_environment():
    value = state_v3_5_environment()
    value["state_transition_runtime_revision"] = (
        STATE_V3_ENVIRONMENT_OWNED_RUNTIME_REVISION
    )
    value["appraisal_prompt_id"] = "environment_appraisal_v18"
    value["state_calibration_profile"] = (
        "evidence_independent_hysteretic_v3"
    )
    return value


def state_v3_7_environment():
    value = state_v3_6_environment()
    value["state_transition_runtime_revision"] = STATE_V3_CAUSAL_RUNTIME_REVISION
    value["appraisal_prompt_id"] = "environment_appraisal_v19"
    value["state_calibration_profile"] = "evidence_causal_hysteretic_v5"
    return value


class StateTransitionContractTest(unittest.TestCase):
    def test_validates_complete_four_family_scenario(self):
        scenario = state_v3_scenario()
        self.assertIs(validate_state_v3_scenario(scenario), scenario)

    def test_rejects_homogeneous_s0_before_rollout(self):
        scenario = state_v3_scenario()
        for family in scenario["initial_state"].values():
            for variable in family:
                family[variable] = 5
        with self.assertRaisesRegex(ValueError, "four distinct levels"):
            validate_state_v3_scenario(scenario)

    def test_rejects_partial_v3_runtime_binding(self):
        environment = state_v3_environment()
        environment["state_calibration_profile"] = "evidence_bound_sparse_v2"
        with self.assertRaisesRegex(ValueError, "inseparable"):
            validate_state_transition_environment_config(
                environment, explicit=True
            )

    def test_rejects_legacy_response_prompt_in_v3(self):
        environment = state_v3_environment()
        environment["response_prompt_id"] = "environment_response_v25"
        with self.assertRaisesRegex(ValueError, "inseparable"):
            validate_state_transition_environment_config(
                environment, explicit=True
            )

    def test_accepts_v3_1_response_runtime(self):
        environment = state_v3_1_environment()
        self.assertEqual(
            validate_state_transition_environment_config(
                environment, explicit=True
            ),
            STATE_TRANSITION_STANDARD_V3,
        )

    def test_accepts_v3_2_natural_10_to_20_runtime(self):
        environment = state_v3_2_environment()
        self.assertEqual(
            validate_state_transition_environment_config(
                environment, explicit=True
            ),
            STATE_TRANSITION_STANDARD_V3,
        )

    def test_accepts_v3_2_1_stable_environment_owned_runtime(self):
        environment = state_v3_2_1_environment()
        self.assertEqual(
            validate_state_transition_environment_config(
                environment, explicit=True
            ),
            STATE_TRANSITION_STANDARD_V3,
        )

    def test_v3_2_1_keeps_v27_response_binding(self):
        environment = state_v3_2_1_environment()
        environment["response_prompt_id"] = "environment_response_v28"
        with self.assertRaisesRegex(ValueError, "inseparable"):
            validate_state_transition_environment_config(
                environment, explicit=True
            )

    def test_accepts_v3_2_2_decision_continuity_runtime(self):
        environment = state_v3_2_2_environment()
        self.assertEqual(
            validate_state_transition_environment_config(
                environment, explicit=True
            ),
            STATE_TRANSITION_STANDARD_V3,
        )

    def test_v3_2_2_requires_decision_continuity_response(self):
        environment = state_v3_2_2_environment()
        environment["response_prompt_id"] = "environment_response_v27"
        with self.assertRaisesRegex(ValueError, "inseparable"):
            validate_state_transition_environment_config(
                environment, explicit=True
            )

    def test_accepts_v3_2_3_event_driven_runtime(self):
        environment = state_v3_2_3_environment()
        self.assertEqual(
            validate_state_transition_environment_config(
                environment, explicit=True
            ),
            STATE_TRANSITION_STANDARD_V3,
        )

    def test_v3_2_3_requires_event_driven_response(self):
        environment = state_v3_2_3_environment()
        environment["response_prompt_id"] = (
            "environment_response_v27_decision_continuity"
        )
        with self.assertRaisesRegex(ValueError, "inseparable"):
            validate_state_transition_environment_config(
                environment, explicit=True
            )

    def test_accepts_v3_2_4_slow_recall_runtime(self):
        environment = state_v3_2_4_environment()
        self.assertEqual(
            validate_state_transition_environment_config(
                environment, explicit=True
            ),
            STATE_TRANSITION_STANDARD_V3,
        )

    def test_v3_2_4_requires_slow_recall_appraisal(self):
        environment = state_v3_2_4_environment()
        environment["appraisal_prompt_id"] = (
            "environment_appraisal_v15_environment_owned"
        )
        with self.assertRaisesRegex(ValueError, "inseparable"):
            validate_state_transition_environment_config(
                environment, explicit=True
            )

    def test_accepts_v3_2_5_slow_audit_runtime(self):
        environment = state_v3_2_5_environment()
        self.assertEqual(
            validate_state_transition_environment_config(
                environment, explicit=True
            ),
            STATE_TRANSITION_STANDARD_V3,
        )

    def test_accepts_v3_2_6_slow_first_runtime(self):
        environment = state_v3_2_6_environment()
        self.assertEqual(
            validate_state_transition_environment_config(
                environment, explicit=True
            ),
            STATE_TRANSITION_STANDARD_V3,
        )

    def test_accepts_v3_2_7_semantic_event_runtime(self):
        environment = state_v3_2_7_environment()
        self.assertEqual(
            validate_state_transition_environment_config(
                environment, explicit=True
            ),
            STATE_TRANSITION_STANDARD_V3,
        )

    def test_accepts_v3_2_8_contrastive_event_runtime(self):
        environment = state_v3_2_8_environment()
        self.assertEqual(
            validate_state_transition_environment_config(
                environment, explicit=True
            ),
            STATE_TRANSITION_STANDARD_V3,
        )

    def test_accepts_v3_2_9_feature_consistent_runtime(self):
        environment = state_v3_2_9_environment()
        self.assertEqual(
            validate_state_transition_environment_config(
                environment, explicit=True
            ),
            STATE_TRANSITION_STANDARD_V3,
        )

    def test_accepts_v3_3_early_opportunity_runtime(self):
        environment = state_v3_3_environment()
        self.assertEqual(
            validate_state_transition_environment_config(
                environment, explicit=True
            ),
            STATE_TRANSITION_STANDARD_V3,
        )

    def test_accepts_v3_4_behavioral_evidence_runtime(self):
        environment = state_v3_4_environment()
        self.assertEqual(
            validate_state_transition_environment_config(
                environment, explicit=True
            ),
            STATE_TRANSITION_STANDARD_V3,
        )

    def test_accepts_v3_5_directional_behavior_runtime(self):
        environment = state_v3_5_environment()
        self.assertEqual(
            validate_state_transition_environment_config(
                environment, explicit=True
            ),
            STATE_TRANSITION_STANDARD_V3,
        )

    def test_v3_5_rejects_v16_and_v3_calibrator(self):
        environment = state_v3_5_environment()
        environment["appraisal_prompt_id"] = "environment_appraisal_v16"
        environment["state_calibration_profile"] = (
            "evidence_independent_hysteretic_v3"
        )
        with self.assertRaisesRegex(ValueError, "inseparable"):
            validate_state_transition_environment_config(
                environment, explicit=True
            )

    def test_accepts_v3_6_environment_owned_runtime(self):
        environment = state_v3_6_environment()
        self.assertEqual(
            validate_state_transition_environment_config(
                environment, explicit=True
            ),
            STATE_TRANSITION_STANDARD_V3,
        )

    def test_v3_6_rejects_v17_directional_binding(self):
        environment = state_v3_6_environment()
        environment["appraisal_prompt_id"] = "environment_appraisal_v17"
        environment["state_calibration_profile"] = (
            "evidence_independent_directional_hysteretic_v4"
        )
        with self.assertRaisesRegex(ValueError, "inseparable"):
            validate_state_transition_environment_config(
                environment, explicit=True
            )

    def test_accepts_v3_7_causal_environment_runtime(self):
        environment = state_v3_7_environment()
        self.assertEqual(
            validate_state_transition_environment_config(
                environment, explicit=True
            ),
            STATE_TRANSITION_STANDARD_V3,
        )

    def test_v3_7_rejects_v18_and_distinct_span_calibrator(self):
        environment = state_v3_7_environment()
        environment["appraisal_prompt_id"] = "environment_appraisal_v18"
        environment["state_calibration_profile"] = (
            "evidence_independent_hysteretic_v3"
        )
        with self.assertRaisesRegex(ValueError, "inseparable"):
            validate_state_transition_environment_config(
                environment, explicit=True
            )

    def test_v3_4_rejects_v15_appraisal_prompt(self):
        environment = state_v3_4_environment()
        environment["appraisal_prompt_id"] = "environment_appraisal_v15"
        with self.assertRaisesRegex(ValueError, "inseparable"):
            validate_state_transition_environment_config(
                environment, explicit=True
            )

    def test_v3_3_rejects_v27_response_prompt(self):
        environment = state_v3_3_environment()
        environment["response_prompt_id"] = "environment_response_v27"
        with self.assertRaisesRegex(ValueError, "inseparable"):
            validate_state_transition_environment_config(
                environment, explicit=True
            )

    def test_v3_1_rejects_v26_response_prompt(self):
        environment = state_v3_1_environment()
        environment["response_prompt_id"] = "environment_response_v26"
        with self.assertRaisesRegex(ValueError, "inseparable"):
            validate_state_transition_environment_config(
                environment, explicit=True
            )

    def test_v3_2_23_binds_state_judgment_primary_calibration(self):
        environment = state_v3_2_9_environment()
        environment["state_transition_runtime_revision"] = (
            STATE_V3_STATE_JUDGMENT_PRIMARY_RUNTIME_REVISION
        )
        environment["appraisal_prompt_id"] = (
            "environment_appraisal_v36_evidence_grounded_state_interpretation"
        )
        environment["state_calibration_profile"] = (
            STATE_V3_STATE_JUDGMENT_PRIMARY_CALIBRATION_PROFILE
        )
        self.assertEqual(
            validate_state_transition_environment_config(
                environment, explicit=True
            ),
            STATE_TRANSITION_STANDARD_V3,
        )
        environment["state_calibration_profile"] = (
            "evidence_causal_slow_priority_hysteretic_v6"
        )
        with self.assertRaisesRegex(ValueError, "inseparable"):
            validate_state_transition_environment_config(
                environment, explicit=True
            )

    def test_scenario_timescale_override_is_validated_and_applied(self):
        scenario = state_v3_scenario()
        scenario["initialization_notes"]["state_timescales"] = {
            "relationship.trust": "turn_to_episode"
        }
        with self.assertRaisesRegex(ValueError, "genuinely slow"):
            validate_state_v3_scenario(scenario)

    def test_v3_factory_records_causal_stage_order(self):
        scenario = state_v3_scenario()
        environment = state_v3_environment()
        factory = ModelEnvironmentFactory(
            scenario,
            {"provider": "unused", "model": "unused"},
            appraisal_prompt_id=environment["appraisal_prompt_id"],
            response_prompt_id=environment["response_prompt_id"],
            state_calibration_profile=environment[
                "state_calibration_profile"
            ],
            state_transition_standard=environment[
                "state_transition_standard"
            ],
            horizon_mode=environment["horizon_mode"],
            minimum_natural_turns=environment["minimum_natural_turns"],
        )
        self.assertEqual(
            factory.provenance["state_transition_stage_order"],
            list(STATE_V3_STAGE_ORDER),
        )

    def test_rejects_scenario_without_slow_relationship_state(self):
        scenario = state_v3_scenario()
        scenario["selected_state_variables"]["relationship"] = [
            "perceived_responsiveness", "role_legitimacy"
        ]
        scenario["initial_state"]["relationship"] = {
            "perceived_responsiveness": 4,
            "role_legitimacy": 5,
        }
        scenario["initialization_notes"]["rationale"]["relationship"] = {
            "perceived_responsiveness": "Grounded S0 rationale.",
            "role_legitimacy": "Grounded S0 rationale.",
        }
        old_paths = {
            "relationship.perceived_responsiveness", "relationship.trust"
        }
        plan = scenario["initialization_notes"]["state_transition_plan"]
        for path in old_paths:
            plan.pop(path, None)
        for path in (
            "relationship.perceived_responsiveness",
            "relationship.role_legitimacy",
        ):
            plan[path] = {
                "increase_evidence": f"increase {path}",
                "decrease_evidence": f"decrease {path}",
            }
        scenario["target_state_ids"] = [
            path
            for path in scenario["target_state_ids"]
            if not path.startswith("relationship.")
        ] + ["relationship.perceived_responsiveness"]
        with self.assertRaisesRegex(ValueError, "genuinely slow"):
            validate_state_v3_scenario(scenario)


if __name__ == "__main__":
    unittest.main()
