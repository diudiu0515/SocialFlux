import unittest

from evaluation.judge_protocol import merge_judgments, required_secondary_ids
from evaluation.rollout_gate import QUALITY_DIMENSIONS
from tests.test_rollout_gate import trajectory


def record(item, score=4, rejects=None):
    return {
        "trajectory_id": item["trajectory_id"],
        "scores": {key: score for key in QUALITY_DIMENSIONS},
        "hard_reject_reasons": list(rejects or []),
        "evidence": {key: ["t1"] for key in QUALITY_DIMENSIONS},
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

    def test_same_model_independent_profiles_are_allowed(self):
        bundle = {
            "format": "socialflux_rollout_quality_judgments_v3",
            "judge_role": "primary", "model": "claude-fable-5", "model_family": "claude",
            "review_profile": {
                "profile": "rollout_primary",
                "sampling": {"seed": 7401},
            },
            "records": [record(item) for item in self.items],
        }
        reasons = required_secondary_ids(self.items, bundle["records"])
        second = {
            **bundle,
            "judge_role": "secondary",
            "review_profile": {
                "profile": "rollout_secondary",
                "sampling": {"seed": 7402},
            },
            "records": [
                record(item) for item in self.items
                if item["trajectory_id"] in reasons
            ],
        }
        result = merge_judgments(self.items, bundle, second)
        self.assertEqual(result["format"], "socialflux_dual_judge_merge_v3")
        self.assertTrue(result["complete"])

    def test_same_model_same_seed_is_rejected(self):
        primary = {
            "judge_role": "primary", "model": "claude-fable-5",
            "model_family": "claude",
            "review_profile": {
                "profile": "rollout_primary", "sampling": {"seed": 7401},
            },
            "records": [record(item) for item in self.items],
        }
        secondary = {
            **primary,
            "judge_role": "secondary",
            "review_profile": {
                "profile": "rollout_secondary", "sampling": {"seed": 7401},
            },
            "records": [],
        }
        with self.assertRaisesRegex(ValueError, "different seeds"):
            merge_judgments(self.items, primary, secondary)


if __name__ == "__main__":
    unittest.main()
