import unittest
from copy import deepcopy
from pathlib import Path
import re

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

    def test_v3_initialization_enforces_confirmed_family_counts(self):
        valid = deepcopy(self.scenario)
        valid["state_ontology_version"] = "socialflux_state_ontology_v3"
        valid["selected_state_variables"] = {
            "emotion": ["anxiety", "frustration", "hope"],
            "behavioral_disposition": ["resolve", "decision_readiness"],
            "relationship": ["trust", "perceived_responsiveness"],
            "consequence_risk": [
                "goal_failure_risk", "decision_error_risk"
            ],
        }
        valid["initial_state"] = {
            family: {variable: 5 for variable in variables}
            for family, variables in valid[
                "selected_state_variables"
            ].items()
        }
        self.assertEqual(
            len({
                f"{family}.{variable}"
                for family, variables in valid[
                    "selected_state_variables"
                ].items()
                for variable in variables
            }),
            9,
        )
        freeze_initialization(valid)

        invalid = deepcopy(valid)
        invalid["selected_state_variables"]["emotion"] = [
            "anxiety", "frustration"
        ]
        invalid["initial_state"]["emotion"] = {
            "anxiety": 5, "frustration": 5
        }
        with self.assertRaisesRegex(ValueError, "emotion must select 3-4"):
            freeze_initialization(invalid)

    def test_active_code_does_not_reference_legacy_motivation_state_family(self):
        roots = (
            "environment", "evaluation", "pipeline", "rollout", "tasks",
            "scenario_design", "scripts", "configs", "schemas", "prompts", "web",
        )
        forbidden = re.compile(r"(?:motivation)\.[A-Za-z_]")
        matches = []
        for root in roots:
            for path in Path(root).rglob("*"):
                if not path.is_file() or path.suffix not in {".py", ".json", ".md", ".html"}:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                if forbidden.search(text):
                    matches.append(str(path))
        self.assertEqual(matches, [])

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
