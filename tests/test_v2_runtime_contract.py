import unittest
from copy import deepcopy

from environment.calibration import DeterministicStateCalibrator
from environment.initializer import freeze_initialization
from environment.state_updater import (
    TransitionValidationError,
    apply_transition,
    validate_transition,
)


class V2RuntimeContractTest(unittest.TestCase):
    def setUp(self):
        self.scenario = {
            "state_contract_version": "socialflux_state_v2",
            "selected_state_variables": {
                "emotion": ["anxiety"],
                "behavioral_disposition": ["resolve"],
                "relationship": ["trust"],
                "consequence_risk": ["goal_failure_risk"],
            },
            "initial_state": {
                "emotion": {"anxiety": 5},
                "behavioral_disposition": {"resolve": 6},
                "relationship": {"trust": 4},
                "consequence_risk": {"goal_failure_risk": 7},
            },
            "initial_dynamics": {
                "deadline_pressure": 6,
                "information_asymmetry": 5,
            },
        }

    def test_v2_initialization_requires_exact_four_family_shape(self):
        frozen = freeze_initialization(self.scenario)
        self.assertEqual(frozen["initial_state"], self.scenario["initial_state"])

        invalid = deepcopy(self.scenario)
        del invalid["initial_state"]["consequence_risk"]
        with self.assertRaisesRegex(ValueError, "exactly the four"):
            freeze_initialization(invalid)

    def test_every_turn_assesses_every_selected_state_and_dynamic(self):
        calibrated = DeterministicStateCalibrator(self.scenario).calibrate(
            {
                "event_features": {},
                "state_impacts": [],
                "dynamics_impacts": [],
                "dialogue_diagnostics": {
                    "substantive_novelty": {"label": "none"}
                },
            },
            self.scenario["initial_state"],
            self.scenario["initial_dynamics"],
        )
        transition = {
            "appraisal": {},
            "evidence_turn_ids": [],
            **calibrated,
        }
        self.assertEqual(
            set(transition["state_delta"]),
            {
                "emotion",
                "behavioral_disposition",
                "relationship",
                "consequence_risk",
            },
        )
        validate_transition(
            transition,
            self.scenario["initial_state"],
            self.scenario["initial_dynamics"],
        )
        updated_state, updated_dynamics, _, _ = apply_transition(
            self.scenario["initial_state"],
            self.scenario["initial_dynamics"],
            transition,
        )
        self.assertEqual(updated_state, self.scenario["initial_state"])
        self.assertEqual(updated_dynamics, self.scenario["initial_dynamics"])

        del transition["state_delta"]["relationship"]
        with self.assertRaises(TransitionValidationError):
            validate_transition(
                transition,
                self.scenario["initial_state"],
                self.scenario["initial_dynamics"],
            )


if __name__ == "__main__":
    unittest.main()
