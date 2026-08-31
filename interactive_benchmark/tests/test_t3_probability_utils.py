import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "tasks" / "T3"))
from t3_probability_utils import expected_change, human_direction_distribution, model_confidence, rank_options, validate_probabilities


class T3ProbabilityUtilsTest(unittest.TestCase):
    def test_distribution_and_confidence(self):
        p = {"increase": 0.6, "similar": 0.2, "decrease": 0.1, "cannot_determine": 0.1}
        self.assertTrue(validate_probabilities(p))
        self.assertEqual(model_confidence(p)["predicted_direction"], "increase")

    def test_cannot_determine_excluded_from_expected_change(self):
        p = {"increase": 0.4, "similar": 0.0, "decrease": 0.4, "cannot_determine": 0.2}
        self.assertAlmostEqual(expected_change(p), 0.0)

    def test_rank_options_is_derived(self):
        a = {"increase": 0.8, "similar": 0.1, "decrease": 0.1, "cannot_determine": 0.0}
        b = {"increase": 0.1, "similar": 0.2, "decrease": 0.7, "cannot_determine": 0.0}
        self.assertEqual(rank_options({"A": a, "B": b}), ["A", "B"])

    def test_human_distribution(self):
        d = human_direction_distribution(["increase", "similar", "increase"])
        self.assertAlmostEqual(d["increase"], 2 / 3)


if __name__ == "__main__":
    unittest.main()
