import json
import unittest
from pathlib import Path

from environment.env import StatefulEnvironment
from policies.controlled import ControlledPolicy
from rollout.runner import RolloutRunner
from schemas.validate import validate_scenario


class MultimodalEnvironmentTest(unittest.TestCase):
    def test_crossing_trigger_is_private_and_public_media_is_safe(self):
        scenario = json.loads(Path("configs/scenarios/scenario_001/scenario_001.json").read_text())
        trajectory = RolloutRunner(lambda: StatefulEnvironment(scenario)).run(
            ControlledPolicy("escalate", [{"action_id": "escalate", "text": "escalate"}]),
            max_turns=3,
        )
        first, second, third = trajectory["turns"]
        self.assertEqual(first["media"], [])
        self.assertEqual(len(second["media"]), 1)
        self.assertEqual(second["trigger_events"][0]["trigger_id"], "escalation_confrontation")
        self.assertIn("trigger_variables", second["trigger_events"][0])
        self.assertNotIn("trigger_events", second["observation"])
        self.assertNotIn("trigger_id", third["observation"]["media"][0])
        self.assertEqual(third["media"], [])

    def test_all_scenarios_register_valid_media_rules(self):
        for path in sorted(Path("configs/scenarios").glob("scenario_*/scenario_*.json")):
            scenario = json.loads(path.read_text())
            validate_scenario(scenario)
            self.assertGreaterEqual(len(scenario["video_triggers"]), 1)
            self.assertEqual(scenario["media_generation"]["asset_status"], "spec_only")


if __name__ == "__main__":
    unittest.main()
