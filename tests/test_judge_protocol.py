import unittest

from evaluation.judge_protocol import merge_judgments, required_secondary_ids
from evaluation.rollout_gate import QUALITY_DIMENSIONS
from tests.test_rollout_gate import trajectory


def record(item, score=4, rejects=None):
    return {
        "trajectory_id": item["trajectory_id"],
        "scores": {key: score for key in QUALITY_DIMENSIONS},
        "hard_reject_reasons": list(rejects or []),
        "rationale": "independent observable review",
    }


class JudgeProtocolTest(unittest.TestCase):
    def setUp(self):
        self.items = [trajectory(index, "glm" if index % 2 else "deepseek") for index in range(8)]

    def test_stratified_subset_and_borderline_cases_require_second_judge(self):
        primary = [record(item) for item in self.items]
        primary[0]["scores"]["naturalness"] = 3
        reasons = required_secondary_ids(self.items, primary)
        self.assertIn(self.items[0]["trajectory_id"], reasons)
        self.assertTrue(any("deterministic_stratified_sample" in value for value in reasons.values()))

    def test_missing_required_secondary_stays_incomplete(self):
        primary = {
            "judge_role": "primary", "model": "judge-a", "model_family": "a",
            "records": [record(item) for item in self.items],
        }
        secondary = {
            "judge_role": "secondary", "model": "judge-b", "model_family": "b",
            "records": [],
        }
        result = merge_judgments(self.items, primary, secondary)
        self.assertFalse(result["complete"])
        self.assertTrue(result["missing_secondary_ids"])

    def test_same_family_judges_are_rejected(self):
        bundle = {
            "judge_role": "primary", "model": "judge-a", "model_family": "same",
            "records": [record(item) for item in self.items],
        }
        second = {**bundle, "judge_role": "secondary", "model": "judge-b"}
        with self.assertRaisesRegex(ValueError, "different model families"):
            merge_judgments(self.items, bundle, second)


if __name__ == "__main__":
    unittest.main()
