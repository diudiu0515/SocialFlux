import unittest

from evaluation.backbone_sensitivity import compare_transitions, failed_comparison, summarize_backbone_sensitivity


class BackboneSensitivityTest(unittest.TestCase):
    def test_direction_agreement_and_reversal_metrics(self):
        left = {"numeric_state_delta": {"emotion": {"anger": 1, "fear": -1}, "relationship": {"trust": 0}}}
        right = {"numeric_state_delta": {"emotion": {"anger": 2, "fear": -2}, "relationship": {"trust": 0}}}
        comparison = compare_transitions(left, right)
        self.assertEqual(comparison["direction_agreement"], 1.0)
        self.assertEqual(comparison["severe_reversal_fraction"], 0.0)
        summary = summarize_backbone_sensitivity([
            {"scenario_id": f"s{index}", "comparison": comparison}
            for index in range(10)
        ])
        self.assertTrue(summary["passed"])

    def test_failed_replay_is_preserved_and_conservatively_rejected(self):
        failed = failed_comparison()
        self.assertTrue(failed["replay_failed"])
        summary = summarize_backbone_sensitivity([
            {"scenario_id": "s1", "comparison": failed},
        ])
        self.assertFalse(summary["passed"])
        self.assertEqual(summary["replay_failure_count"], 1)

    def test_all_similar_backbones_cannot_pass_on_agreement_alone(self):
        comparison = compare_transitions(
            {"numeric_state_delta": {"emotion": {"anger": 0}}},
            {"numeric_state_delta": {"emotion": {"anger": 0}}},
        )
        summary = summarize_backbone_sensitivity([
            {"scenario_id": "s1", "comparison": comparison},
        ])
        self.assertEqual(summary["mean_direction_agreement"], 0.0)
        self.assertEqual(summary["mean_all_dimension_direction_agreement"], 1.0)
        self.assertFalse(summary["backbone_activity_passed"])
        self.assertFalse(summary["passed"])

    def test_zero_zero_dimensions_do_not_inflate_gate_agreement(self):
        comparison = compare_transitions(
            {"numeric_state_delta": {"emotion": {"a": 1, "b": 0, "c": 0}}},
            {"numeric_state_delta": {"emotion": {"a": 0, "b": 0, "c": 0}}},
        )
        self.assertAlmostEqual(
            comparison["all_dimension_direction_agreement"], 2 / 3, places=4
        )
        self.assertEqual(comparison["direction_agreement"], 0.0)
        self.assertEqual(comparison["active_union_count"], 1)

    def test_service_failure_is_not_scored_as_backbone_reversal(self):
        comparison = compare_transitions(
            {"numeric_state_delta": {"emotion": {"a": 1}}},
            {"numeric_state_delta": {"emotion": {"a": 1}}},
        )
        rows = [
            {"scenario_id": f"s{index}", "comparison": comparison}
            for index in range(10)
        ] + [{"scenario_id": "failed", "comparison": failed_comparison()}]
        summary = summarize_backbone_sensitivity(rows)
        self.assertEqual(summary["mean_direction_agreement"], 1.0)
        self.assertEqual(summary["replay_failure_count"], 1)
        self.assertEqual(summary["successful_matched_checkpoint_count"], 10)
        self.assertFalse(summary["passed"])

    def test_empty_evidence_never_passes(self):
        self.assertFalse(summarize_backbone_sensitivity([])["passed"])


if __name__ == "__main__":
    unittest.main()
