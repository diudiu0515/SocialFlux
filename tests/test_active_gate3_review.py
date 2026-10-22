import unittest

from scripts.review_active_rollouts import decision


DIMENSIONS = (
    "coherence",
    "history_dependence",
    "character_consistency",
    "state_response_consistency",
    "interaction_progression",
    "naturalness",
)


class ActiveGate3ReviewTest(unittest.TestCase):
    def judgment(self, score=4):
        return {
            "scores": {name: score for name in DIMENSIONS},
            "hard_reject_reasons": [],
        }

    def test_single_model_review_approves_only_all_required_scores(self):
        self.assertEqual(decision(self.judgment()), "approve")
        value = self.judgment()
        value["scores"]["naturalness"] = 3
        self.assertEqual(decision(value), "reject")

    def test_hard_reject_overrides_scores(self):
        value = self.judgment(5)
        value["hard_reject_reasons"] = ["contradictory_response"]
        self.assertEqual(decision(value), "reject")


if __name__ == "__main__":
    unittest.main()
