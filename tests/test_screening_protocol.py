import unittest

from evaluation.screening_protocol import automatic_decision, choose_one
from evaluation.rollout_gate import QUALITY_DIMENSIONS


class ScreeningProtocolTest(unittest.TestCase):
    def scores(self, value=4):
        return {key: value for key in QUALITY_DIMENSIONS}

    def test_exact_pass_thresholds(self):
        result = automatic_decision(self.scores(4), [])
        self.assertEqual(result["decision"], "PASS")
        self.assertEqual(result["mean_quality_score"], 4.0)

    def test_review_is_not_forced_into_binary_decision(self):
        scores = self.scores(4)
        scores["history_dependence"] = 3
        self.assertEqual(automatic_decision(scores, [])["decision"], "REVIEW")

    def test_hard_failure_always_rejects(self):
        result = automatic_decision(self.scores(5), ["future_information_leakage"])
        self.assertEqual(result["decision"], "REJECT")

    def test_missing_scores_stay_review(self):
        result = automatic_decision({"naturalness": 5}, [])
        self.assertEqual(result["decision"], "REVIEW")
        self.assertIn("dialogue_coherence", result["missing_evidence"])

    def test_one_winner_uses_quality_not_model_quota(self):
        records = [
            {"trajectory_id": "a", "automatic_decision": "PASS", "mean_quality_score": 4.0,
             "scores": self.scores(4), "model_family": "qwen"},
            {"trajectory_id": "b", "automatic_decision": "PASS", "mean_quality_score": 4.5,
             "scores": self.scores(4.5), "model_family": "qwen"},
        ]
        winner, ordered = choose_one(records)
        self.assertEqual(winner["trajectory_id"], "b")
        self.assertEqual(len(ordered), 2)


if __name__ == "__main__":
    unittest.main()
