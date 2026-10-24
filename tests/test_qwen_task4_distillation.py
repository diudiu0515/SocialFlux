from copy import deepcopy
import json
import unittest

from environment.calibration import FEATURE_NAMES
from scripts.prepare_qwen_task4_distillation import check_split, validate_example


class DistillationTests(unittest.TestCase):
    def fixture(self):
        payload = {"action": {"text": "The decision is pending."},
                   "state_variable_paths": ["emotion.anxiety"], "dynamics_variable_paths": [],
                   "state_semantics": {"variables": {}}, "memory": {"relevant_turn_ids": ["t1"]}}
        value = {"event_features": {k: 0 for k in FEATURE_NAMES},
                 "state_judgments": [{"variable": "emotion.anxiety", "judgment": "no_relevant_evidence",
                                      "direction": None, "directness": None, "evidence_feature": None,
                                      "evidence_span": "", "rationale": "No new state evidence."}],
                 "dynamics_judgments": [], "evidence_turn_ids": ["t1", "t2", "t1"]}
        return payload, value

    def test_source_ids_are_canonically_normalized_without_changing_judgments(self):
        payload, value = self.fixture()
        before = deepcopy(value)
        output, projection = validate_example("state", payload, json.dumps(value))
        self.assertEqual(value, before)
        self.assertEqual(output["state_judgments"], before["state_judgments"])
        self.assertEqual(output["evidence_turn_ids"], ["t1"])
        self.assertEqual(projection["source_evidence_turn_ids"], ["t1", "t2", "t1"])

    def test_training_cannot_include_regression_or_evaluation_scenarios(self):
        check_split(["a"], ["b"], ["c"])
        for args in [(["a"], ["a"], ["c"]), (["a"], ["b"], ["a"]), (["a"], ["b"], ["b"])]:
            with self.subTest(args=args), self.assertRaisesRegex(ValueError, "disjoint"):
                check_split(*args)

    def test_misquoted_teacher_evidence_is_rejected(self):
        payload, value = self.fixture()
        value["state_judgments"][0].update(judgment="ordinary_new_evidence", direction="increase",
                                           directness="direct", evidence_span="Approval is final.")
        with self.assertRaises(ValueError):
            validate_example("state", payload, json.dumps(value))


if __name__ == "__main__":
    unittest.main()
