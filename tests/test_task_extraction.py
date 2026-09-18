import unittest

from tasks.extraction import public_history, validate_extraction


class TaskExtractionTest(unittest.TestCase):
    def setUp(self):
        self.scenario = {
            "target_state_ids": [
                "emotion.anxiety",
                "relationship.trust",
                "motivation.resolve",
            ]
        }
        self.trajectory = {
            "turns": [
                {
                    "turn_id": f"t{index}",
                    "policy_action": {"text": f"行动 {index}"},
                    "environment_response": f"回应 {index}",
                    "observable_expression": {"tone": "平静"},
                    "public_events_after": [],
                    "appraisal": {"private": True},
                }
                for index in range(1, 9)
            ]
        }

    def _valid(self):
        return {
            "t1": [{
                "checkpoint_turn_id": "t4",
                "target_state_ids": ["emotion.anxiety", "relationship.trust"],
                "evidence_turn_ids": ["t2", "t4"],
                "rationale": "公开回应显示焦虑与信任判断发生变化。",
            }],
            "t3": {
                "checkpoint_turn_id": "t3",
                "target_state_ids": ["motivation.resolve"],
                "future_turns_available": 5,
                "rationale": "此时仍存在多种可行行动。",
            },
        }

    def test_valid_extraction(self):
        value = self._valid()
        self.assertIs(
            validate_extraction(value, self.scenario, self.trajectory),
            value,
        )

    def test_rejects_evidence_after_checkpoint(self):
        value = self._valid()
        value["t1"][0]["evidence_turn_ids"] = ["t5"]
        with self.assertRaisesRegex(ValueError, "after checkpoint"):
            validate_extraction(value, self.scenario, self.trajectory)

    def test_public_history_excludes_private_fields(self):
        history = public_history(self.trajectory)
        self.assertEqual(len(history), 8)
        self.assertNotIn("appraisal", history[0])
        self.assertEqual(history[0]["evaluated_agent"], "行动 1")

    def test_short_trajectory_allows_explicitly_missing_t3(self):
        trajectory = {"turns": self.trajectory["turns"][:5]}
        value = self._valid()
        value["t1"][0]["checkpoint_turn_id"] = "t4"
        value["t1"][0]["evidence_turn_ids"] = ["t2", "t4"]
        value["t3"] = None
        self.assertIs(validate_extraction(value, self.scenario, trajectory), value)

    def test_t3_cannot_be_null_when_a_five_turn_window_exists(self):
        value = self._valid()
        value["t3"] = None
        with self.assertRaisesRegex(ValueError, "may be null"):
            validate_extraction(value, self.scenario, self.trajectory)


if __name__ == "__main__":
    unittest.main()
