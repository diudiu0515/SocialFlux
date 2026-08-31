import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "tasks" / "T1"))
from t1_probability_utils import (
    aggregate_human_confidence,
    human_label_distribution,
    model_confidence,
    ordinal_mean,
    validate_probabilities,
)


class T1ProbabilityUtilsTest(unittest.TestCase):
    def test_human_distribution_and_ordinal_mean(self):
        distribution = human_label_distribution(["mild", "moderate", "moderate", "moderate", "strong"])
        self.assertEqual(distribution["moderate"], 0.6)
        self.assertAlmostEqual(ordinal_mean(distribution), 2.0)

    def test_cannot_determine_is_not_absent(self):
        distribution = human_label_distribution(["cannot_determine"] * 5)
        self.assertEqual(distribution["absent"], 0.0)
        self.assertIsNone(ordinal_mean(distribution))

    def test_model_confidence(self):
        distribution = {"absent": 0.02, "mild": 0.08, "moderate": 0.45, "strong": 0.38, "very_strong": 0.06, "cannot_determine": 0.01}
        result = model_confidence(distribution)
        self.assertEqual(result["predicted_label"], "moderate")
        self.assertAlmostEqual(result["max_probability"], 0.45)
        self.assertAlmostEqual(result["margin"], 0.07)
        self.assertTrue(0 <= result["entropy_confidence"] <= 1)

    def test_human_confidence_is_separate(self):
        result = aggregate_human_confidence(["medium", "high", "high", "very_high", "high"])
        self.assertAlmostEqual(result["mean_1_to_4"], 3.0)
        self.assertAlmostEqual(result["normalized_0_to_1"], 2 / 3)

    def test_probability_sum_is_enforced(self):
        with self.assertRaises(ValueError):
            validate_probabilities({"absent": 1, "mild": 1, "moderate": 0, "strong": 0, "very_strong": 0, "cannot_determine": 0})


if __name__ == "__main__":
    unittest.main()
