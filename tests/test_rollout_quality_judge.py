import unittest

from scripts.run_rollout_quality_judge import deterministic_judge_sampling, validate


class RolloutQualityJudgeValidationTest(unittest.TestCase):
    def judgment(self):
        return {
            "scores": {
                "dialogue_coherence": 4,
                "history_dependence": 4,
                "character_consistency": 4,
                "state_response_consistency": 4,
                "interaction_progression": 3,
                "naturalness": 4,
            },
            "hard_reject_reasons": [],
            "evidence": {
                "dialogue_coherence": ["t1"],
                "history_dependence": ["t2"],
                "character_consistency": ["t1"],
                "state_response_consistency": ["t2"],
                "interaction_progression": ["t2"],
                "naturalness": ["t1"],
            },
            "rationale": "observable evidence supports the ratings",
        }

    def test_caller_replaces_model_transcribed_trajectory_id(self):
        value = self.judgment()
        value["trajectory_id"] = "mistyped-by-model"
        result = validate(value, "caller-owned-id")
        self.assertEqual(result["trajectory_id"], "caller-owned-id")
        self.assertEqual(value["trajectory_id"], "mistyped-by-model")

    def test_caller_adds_missing_trajectory_id(self):
        result = validate(self.judgment(), "caller-owned-id")
        self.assertEqual(result["trajectory_id"], "caller-owned-id")

    def test_turn_evidence_must_exist_in_trajectory(self):
        with self.assertRaisesRegex(ValueError, "invalid turn evidence"):
            validate(self.judgment(), "caller-owned-id", {"t1"})
        result = validate(self.judgment(), "caller-owned-id", {"t1", "t2"})
        self.assertEqual(result["evidence"]["history_dependence"], ["t2"])

    def test_extra_model_field_is_rejected(self):
        value = self.judgment()
        value["unexpected"] = True
        with self.assertRaisesRegex(ValueError, "fields mismatch"):
            validate(value, "caller-owned-id")

    def test_judge_seed_is_stable_per_trajectory_and_order_independent(self):
        sampling = {"seed": 7401, "temperature": 0.1}
        first = deterministic_judge_sampling(sampling, "trajectory-a")
        repeated = deterministic_judge_sampling(sampling, "trajectory-a")
        other = deterministic_judge_sampling(sampling, "trajectory-b")
        self.assertEqual(first, repeated)
        self.assertNotEqual(first["seed"], other["seed"])
        self.assertEqual(sampling["seed"], 7401)


if __name__ == "__main__":
    unittest.main()
