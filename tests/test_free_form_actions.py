import json
import unittest
from pathlib import Path

from environment.env import coerce_free_form_action
from rollout.runner import RolloutRunner
from tests.support import TextPolicy, environment_factory


class FreeFormActionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = json.loads(
            Path("configs/scenarios/scenario_001/scenario_001.json").read_text(encoding="utf-8")
        )

    def test_arbitrary_text_is_preserved_without_taxonomy(self):
        text = "我想先核对贡献证据，再讨论一项双方能接受的安排。"
        trajectory = RolloutRunner(environment_factory(self.scenario)).run(
            TextPolicy("test-model-seed-1", [text]),
            max_turns=1,
        )
        self.assertEqual(trajectory["turns"][0]["policy_action"], {"text": text})
        self.assertNotIn("action_id", trajectory["turns"][0]["policy_action"])

    def test_action_id_is_rejected(self):
        with self.assertRaises(ValueError):
            coerce_free_form_action({"action_id": "repair", "text": "hello"})

    def test_empty_action_is_rejected(self):
        with self.assertRaises(ValueError):
            coerce_free_form_action("   ")


if __name__ == "__main__":
    unittest.main()
