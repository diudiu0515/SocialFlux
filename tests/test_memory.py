import unittest

from environment.memory import MemoryModule


class MemoryModuleTest(unittest.TestCase):
    def test_relevant_turn_ids_are_unique_while_summary_keeps_both_roles(self):
        history = [
            {"turn_id": 1, "role": "evaluated_agent", "text": "先核对记录"},
            {"turn_id": 1, "role": "environment_agent", "text": "可以核对"},
            {"turn_id": 2, "role": "evaluated_agent", "text": "再确认时间"},
            {"turn_id": 2, "role": "environment_agent", "text": "时间已确认"},
        ]
        memory = MemoryModule(max_events=4).retrieve(
            history, {"text": "核对时间"}
        )
        self.assertEqual(memory["relevant_turn_ids"], ["t1", "t2"])
        self.assertIn("evaluated_agent", memory["memory_summary"])
        self.assertIn("environment_agent", memory["memory_summary"])


if __name__ == "__main__":
    unittest.main()
