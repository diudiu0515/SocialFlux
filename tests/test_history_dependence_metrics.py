import unittest

from scripts.run_history_dependence import (
    _interpretation_comparison,
    critical_turn,
)


def output(intent, state_delta):
    return {
        "appraisal": {
            "speaker_intent": intent,
            "social_act": "request",
            "event_features": {"goal_alignment": 1},
            "state_impacts": [{
                "variable": "relationship.trust",
                "direction": "increase",
            }],
            "dynamics_impacts": [],
        },
        "numeric_state_delta": {
            "relationship": {"trust": state_delta},
        },
        "numeric_dynamics_delta": {},
    }


class HistoryDependenceMetricTest(unittest.TestCase):
    def test_free_text_rewording_does_not_create_history_change(self):
        comparison = _interpretation_comparison(
            output("请求核对记录", 1),
            output("请对现有记录进行核验", 1),
        )
        self.assertEqual(comparison["change_score"], 0.0)
        self.assertLess(comparison["appraisal_similarity"], 1.0)

    def test_one_sided_state_change_is_not_diluted_by_unchanged_dimensions(self):
        comparison = _interpretation_comparison(
            output("请求核对记录", 1),
            output("请求核对记录", 0),
        )
        self.assertEqual(comparison["change_score"], 1.0)
        self.assertEqual(
            comparison["state_active_union_direction_agreement"], 0.0
        )

    def test_critical_turn_prefers_retrieved_history(self):
        trajectory = {
            "turns": [
                {
                    "turn_id": "t1",
                    "state_before": {"emotion": {"anxiety": 0}},
                    "state_after": {"emotion": {"anxiety": 3}},
                },
                {
                    "turn_id": "t2",
                    "state_before": {"emotion": {"anxiety": 3}},
                    "state_after": {"emotion": {"anxiety": 4}},
                },
                {"turn_id": "t3"},
            ]
        }
        self.assertEqual(
            critical_turn(trajectory, 2, relevant_turn_ids=["t2"]), "t2"
        )


if __name__ == "__main__":
    unittest.main()
