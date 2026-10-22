import unittest

from evaluation.task_source_selection import (
    rank_t1_checkpoints,
    rank_t3_checkpoints,
    select_task_sources,
)


TASK_DIMENSIONS = {
    "dialogue_coherence", "history_dependence", "character_consistency",
    "state_response_consistency", "interaction_progression", "naturalness",
}


class TaskSourceSelectionTest(unittest.TestCase):
    def test_tasks_rank_independently_without_model_quota(self):
        trajectories = [
            {"trajectory_id": "qwen-a", "policy_provenance": {"model_family": "qwen"}},
            {"trajectory_id": "qwen-b", "policy_provenance": {"model_family": "qwen"}},
            {"trajectory_id": "glm-a", "policy_provenance": {"model_family": "glm"}},
        ]
        base = {
            "dialogue_coherence": 0.8,
            "history_dependence": 0.8,
            "character_consistency": 0.8,
            "state_response_consistency": 0.8,
            "interaction_progression": 0.8,
            "naturalness": 0.8,
        }
        audits = [
            {"trajectory_id": "qwen-a", "passed": True, "scores": {**base, "state_response_consistency": 1.0}},
            {"trajectory_id": "qwen-b", "passed": True, "scores": {**base, "interaction_progression": 1.0}},
            {"trajectory_id": "glm-a", "passed": True, "scores": {**base, "history_dependence": 0.6}},
        ]
        result = select_task_sources(trajectories, audits, t1_source_count=2)
        self.assertFalse(result["model_quota"])
        self.assertEqual(result["t1_source_ids"], ["qwen-a", "qwen-b"])
        self.assertEqual(result["t3_source_ids_ranked"][0], "qwen-b")

    def test_canonical_winner_is_primary_for_t1_and_t3(self):
        trajectories = [{"trajectory_id": "winner"}, {"trajectory_id": "higher-score"}]
        low = {name: 0.7 for name in TASK_DIMENSIONS}
        high = {name: 1.0 for name in TASK_DIMENSIONS}
        result = select_task_sources(
            trajectories,
            [
                {"trajectory_id": "winner", "passed": True, "scores": low},
                {"trajectory_id": "higher-score", "passed": True, "scores": high},
            ],
            t1_source_count=1,
            canonical_trajectory_id="winner",
        )
        self.assertEqual(result["t1_source_ids"], ["winner"])
        self.assertEqual(result["t3_source_ids_ranked"][0], "winner")
        self.assertEqual(result["canonical_trajectory_id"], "winner")

    def test_failed_quality_candidate_is_never_ranked(self):
        trajectories = [{"trajectory_id": "good"}, {"trajectory_id": "bad"}]
        scores = {name: 1.0 for name in (
            "dialogue_coherence", "history_dependence", "character_consistency",
            "state_response_consistency", "interaction_progression", "naturalness",
        )}
        result = select_task_sources(trajectories, [
            {"trajectory_id": "good", "passed": True, "scores": scores},
            {"trajectory_id": "bad", "passed": False, "scores": scores},
        ])
        self.assertEqual(result["eligible_trajectory_ids"], ["good"])


    def test_t1_checkpoint_ranking_prefers_history_and_information(self):
        trajectory = {
            "trajectory_id": "source",
            "turns": [
                {
                    "state_before": {"emotion": {"anger": 1}},
                    "state_after": {"emotion": {"anger": 1}},
                },
                {
                    "state_before": {"emotion": {"anger": 1}},
                    "state_after": {"emotion": {"anger": 4}},
                },
            ],
        }
        ranked = rank_t1_checkpoints([trajectory], {"source": 0.8})
        self.assertEqual(ranked[0]["turn_index"], 1)


    def test_t3_checkpoint_ranking_balances_history_and_future_room(self):
        trajectory = {
            "trajectory_id": "source",
            "turns": [{"turn_id": f"t{index}"} for index in range(1, 7)],
        }
        ranked = rank_t3_checkpoints([trajectory], {"source": 0.8})
        self.assertEqual(ranked[0]["turn"]["turn_id"], "t4")
        self.assertGreater(ranked[0]["checkpoint_depth"], 0)


if __name__ == "__main__":
    unittest.main()
