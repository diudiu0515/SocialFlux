import unittest

from evaluation.backbone_sensitivity import compare_transitions, summarize_backbone_sensitivity


class BackboneSensitivityTest(unittest.TestCase):
    def test_direction_agreement_and_reversal_metrics(self):
        left = {"numeric_state_delta": {"emotion": {"anger": 1, "fear": -1}, "relationship": {"trust": 0}}}
        right = {"numeric_state_delta": {"emotion": {"anger": 2, "fear": -2}, "relationship": {"trust": 0}}}
        comparison = compare_transitions(left, right)
        self.assertEqual(comparison["direction_agreement"], 1.0)
        self.assertEqual(comparison["severe_reversal_fraction"], 0.0)
        summary = summarize_backbone_sensitivity([{"scenario_id": "s1", "comparison": comparison}])
        self.assertTrue(summary["passed"])

    def test_empty_evidence_never_passes(self):
        self.assertFalse(summarize_backbone_sensitivity([])["passed"])


if __name__ == "__main__":
    unittest.main()
