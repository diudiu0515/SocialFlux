import json
import unittest
from pathlib import Path

from environment.env import StatefulEnvironment
from environment.state_updater import validate_transition
from rollout.runner import RolloutRunner
from schemas.validate import validate_scenario
from tests.support import ContextualTestResponse, TextPolicy


class IncreasingUpdater:
    provenance = {"provider": "test-double", "model": "increasing-updater"}

    def _fill(self, values):
        return {
            key: self._fill(value) if isinstance(value, dict) else "strong_increase"
            for key, value in values.items()
        }

    def update(self, *, action, previous_state, previous_dynamics, memory):
        return validate_transition({
            "appraisal": {"exact_action": action["text"]},
            "state_delta": self._fill(previous_state),
            "interaction_dynamics_delta": self._fill(previous_dynamics),
            "evidence_turn_ids": memory["relevant_turn_ids"],
        }, previous_state, previous_dynamics)


class MultimodalEnvironmentTest(unittest.TestCase):
    def test_crossing_trigger_is_private_and_public_media_is_safe(self):
        scenario = json.loads(
            Path("configs/scenarios/scenario_001/scenario_001.json").read_text()
        )
        factory = lambda: StatefulEnvironment(
            scenario,
            state_updater=IncreasingUpdater(),
            response_generator=ContextualTestResponse(),
        )
        trajectory = RolloutRunner(factory).run(
            TextPolicy("test-model", ["我要说明我的考虑。"]),
            max_turns=3,
        )
        first, second, third = trajectory["turns"]
        self.assertEqual(first["media"], [])
        self.assertEqual(len(second["media"]), 1)
        self.assertEqual(second["trigger_events"][0]["trigger_id"], "escalation_confrontation")
        self.assertNotIn("trigger_events", second["observation"])
        self.assertNotIn("trigger_id", third["observation"]["media"][0])
        self.assertEqual(third["media"], [])

    def test_all_scenarios_have_no_action_transition_table(self):
        for path in sorted(Path("configs/scenarios").glob("scenario_*/scenario_*.json")):
            scenario = json.loads(path.read_text())
            validate_scenario(scenario)
            self.assertNotIn("action_effects", scenario)
            self.assertNotIn("response_templates", scenario)
            self.assertGreaterEqual(len(scenario["video_triggers"]), 1)


if __name__ == "__main__":
    unittest.main()
