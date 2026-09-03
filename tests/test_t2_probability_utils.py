import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tasks" / "T2"))
from t2_probability_utils import causal_relevance, human_direction_distribution, model_confidence


class T2ProbabilityUtilsTest(unittest.TestCase):
    def test_human_direction_distribution(self):
        result = human_direction_distribution(["higher_in_a", "higher_in_a", "higher_in_a", "similar", "higher_in_b"])
        self.assertAlmostEqual(result["higher_in_a"], 0.6)
        self.assertAlmostEqual(result["similar"], 0.2)
        self.assertAlmostEqual(result["higher_in_b"], 0.2)

    def test_similar_is_not_cannot_determine(self):
        result = human_direction_distribution(["similar"] * 5)
        self.assertEqual(result["similar"], 1.0)
        self.assertEqual(result["cannot_determine"], 0.0)

    def test_causal_relevance_is_multilabel_probability(self):
        self.assertAlmostEqual(causal_relevance([True, True, True, True, False]), 0.8)

    def test_model_confidence(self):
        result = model_confidence({"higher_in_a": 0.62, "similar": 0.20, "higher_in_b": 0.13, "cannot_determine": 0.05})
        self.assertEqual(result["predicted_direction"], "higher_in_a")
        self.assertAlmostEqual(result["max_probability"], 0.62)
        self.assertAlmostEqual(result["margin"], 0.42)


if __name__ == "__main__":
    unittest.main()
