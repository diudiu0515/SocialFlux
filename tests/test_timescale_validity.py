import unittest

from evaluation.timescale_validity import (
    build_timescale_review_items,
    machine_timescale_packet_ready,
    pending_timescale_payload,
    trajectory_timescale_items,
)


def trajectory(index):
    deltas = (
        (1, 1, 0, 2),
        (-1, 1, 1, 0),
        (0, -1, 0, -1),
    )
    turns = []
    for turn_index, values in enumerate(deltas, start=1):
        emotion, disposition, relationship, risk = values
        turns.append({
            "turn_id": f"t{turn_index}",
            "numeric_state_delta": {
                "emotion": {"anxiety": emotion},
                "behavioral_disposition": {"cooperation_readiness": disposition},
                "relationship": {"trust": relationship},
                "consequence_risk": {"goal_failure_risk": risk},
            },
        })
    return {
        "scenario_id": f"scenario-{index}",
        "trajectory_id": f"trajectory-{index}",
        "turns": turns,
    }


class TimescaleValidityTest(unittest.TestCase):
    def test_trajectory_summary_preserves_family_priors_and_reversals(self):
        items = trajectory_timescale_items(trajectory(1))
        by_state = {item["state_id"]: item for item in items}
        self.assertEqual(
            by_state["emotion.anxiety"]["expected_timescale_prior"],
            "fast",
        )
        self.assertEqual(by_state["emotion.anxiety"]["reversal_count"], 1)
        self.assertEqual(
            by_state["relationship.trust"]["expected_timescale_prior"],
            "slow",
        )
        self.assertEqual(
            by_state["consequence_risk.goal_failure_risk"][
                "expected_timescale_prior"
            ],
            "context_dependent",
        )

    def test_packet_is_deterministic_covered_and_never_human_approved(self):
        trajectories = [trajectory(index) for index in range(3)]
        forward = build_timescale_review_items(trajectories, limit=40)
        backward = build_timescale_review_items(
            list(reversed(trajectories)), limit=40
        )
        self.assertEqual(forward, backward)
        payload = pending_timescale_payload(trajectories, limit=40)
        self.assertEqual(payload["record"]["candidate_variable_count"], 12)
        self.assertIsNone(payload["record"]["passed"])
        self.assertFalse(payload["record"]["human_attestation"])
        self.assertTrue(payload["record"]["non_degenerate"])
        self.assertEqual(
            payload["record"]["population_summary"]["variable_count"], 12
        )
        self.assertIn(
            "by_state_family", payload["record"]["population_summary"]
        )
        self.assertEqual(
            payload["record"]["population_summary"]["by_expected_timescale"]
            ["slow"]["variable_count"],
            3,
        )
        self.assertTrue(machine_timescale_packet_ready(payload))

    def test_packet_readiness_requires_all_three_explicit_priors(self):
        payload = pending_timescale_payload(
            [trajectory(index) for index in range(3)], limit=40
        )
        payload["record"]["timescale_families"]["slow"] = 0
        self.assertFalse(machine_timescale_packet_ready(payload))


if __name__ == "__main__":
    unittest.main()
