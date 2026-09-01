import json
import unittest
from pathlib import Path

from environment.action_interpreter import normalize_action
from environment.env import StatefulEnvironment


class ActionInterpreterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = json.loads(Path("configs/scenarios/scenario_001/scenario_001.json").read_text(encoding="utf-8"))

    def test_paraphrases_map_to_same_canonical_action(self):
        first = "我想先把问题说清楚，找一个双方都能接受的解决办法。"
        second = "我们先冷静沟通，一起讨论一个可执行的方案。"
        self.assertEqual(normalize_action({"text": first}, self.scenario)["action_id"], "repair")
        self.assertEqual(normalize_action({"text": second}, self.scenario)["action_id"], "repair")

    def test_environment_logs_submitted_and_normalized_actions(self):
        text = "如果没有明确处理，我会正式提出申诉并追究责任。"
        env = StatefulEnvironment(self.scenario)
        env.reset("normalizer-test")
        _, turn = env.step({"text": text})
        self.assertEqual(turn["submitted_action"], {"text": text})
        self.assertEqual(turn["policy_action"]["action_id"], "escalate")
        self.assertEqual(turn["policy_action"]["text"], text)


if __name__ == "__main__":
    unittest.main()
