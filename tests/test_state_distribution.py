import unittest

from evaluation.state_distribution import (
    compare_state_distributions,
    summarize_state_distribution,
)


class StateDistributionTest(unittest.TestCase):
    def test_empty_after_sample_is_not_reported_as_improvement(self):
        before = summarize_state_distribution([{
            "trajectory_id": "old",
            "turns": [{
                "numeric_state_delta": {"emotion": {"anger": 1}},
                "numeric_dynamics_delta": {"negotiation_open": 0},
                "state_after": {"emotion": {"anger": 5}},
            }],
        }])
        after = summarize_state_distribution([])
        result = compare_state_distributions(before, after)
        self.assertEqual(result["comparison_status"], "insufficient_after_samples")
        self.assertTrue(all(value is None for value in result["change"].values()))

    def test_distribution_reports_inertia_oscillation_and_saturation(self):
        trajectory = {
            "trajectory_id": "r1",
            "turns": [
                {
                    "numeric_state_delta": {"emotion": {"anger": 1, "hope": 0}},
                    "numeric_dynamics_delta": {"open": 0},
                    "state_after": {"emotion": {"anger": 6, "hope": 10}},
                },
                {
                    "numeric_state_delta": {"emotion": {"anger": -1, "hope": 0}},
                    "numeric_dynamics_delta": {"open": 2},
                    "state_after": {"emotion": {"anger": 5, "hope": 9}},
                },
            ],
        }
        result = summarize_state_distribution([trajectory])
        self.assertEqual(result["turn_count"], 2)
        self.assertEqual(result["delta_ratio"]["similar"], 0.5)
        self.assertEqual(result["delta_ratio"]["mild"], 0.3333)
        self.assertEqual(result["delta_ratio"]["moderate"], 0.1667)
        self.assertEqual(result["mean_changed_variables_per_turn"], 1.5)
        self.assertEqual(result["oscillation_count"], 1)
        self.assertEqual(result["saturation_ratio"], 0.25)


if __name__ == "__main__":
    unittest.main()
