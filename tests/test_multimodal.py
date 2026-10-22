import json
import unittest
from pathlib import Path

from environment.env import StatefulEnvironment
from environment.multimodal import ObservableExpressionLayer
from environment.online_multimodal import (
    ONLINE_MULTIMODAL_PROFILE,
    build_online_multimodal_profile,
)
from environment.state_updater import validate_transition
from environment.video_requests import attach_online_requests
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
    def test_priority_cooldown_and_public_media_boundary(self):
        scenario = json.loads(
            Path("data/gpt50/experiment/scenario/scenarios/scenario_001/scenario_001.json").read_text()
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
        self.assertEqual(len(first["media"]), 1)
        configured_ids = {item["trigger_id"] for item in scenario["video_triggers"]}
        self.assertIn(first["trigger_events"][0]["trigger_id"], configured_ids)
        self.assertEqual(len(first["video_api_requests"]), 1)
        request = first["video_api_requests"][0]["request"]
        self.assertTrue(request["prompt"])
        self.assertTrue(all(
            value is False for value in request["safety_check"].values()
        ))
        self.assertEqual(second["media"], [])
        self.assertNotIn("trigger_events", second["observation"])
        self.assertEqual(third["observation"]["media"], [])
        self.assertEqual(third["media"], [])

    def test_only_highest_priority_eligible_event_fires_per_turn(self):
        def trigger(trigger_id, priority):
            return {
                "trigger_id": trigger_id,
                "priority": priority,
                "trigger_mode": "threshold",
                "conditions": {"emotion.anger": {"operator": ">=", "threshold": 5}},
                "observable_expression": {"facial_expression": trigger_id},
                "cue_template": trigger_id,
            }

        layer = ObservableExpressionLayer({
            "video_triggers": [trigger("lower_priority", 2), trigger("highest_priority", 1)]
        })
        result = layer.evaluate(
            turn_id=1,
            previous_state={"emotion": {"anger": 4}},
            previous_dynamics={},
            state={"emotion": {"anger": 6}},
            dynamics={},
            last_trigger_turns={},
        )
        self.assertEqual(len(result["private_events"]), 1)
        self.assertEqual(result["private_events"][0]["trigger_id"], "highest_priority")

    def test_relaxed_online_policy_turns_crossing_into_threshold(self):
        scenario = {
            "video_triggers": [{
                "trigger_id": "high_tension",
                "priority": 1,
                "trigger_mode": "crossing",
                "conditions": {
                    "emotion.anger": {"operator": ">=", "threshold": 8}
                },
                "observable_expression": {
                    "facial_expression": "明显绷紧",
                    "gaze": "持续注视",
                    "speech_style": "语速放慢",
                    "prosody": "克制",
                    "behavioral_cues": ["下颌收紧"],
                },
                "cue_template": "张力外显",
            }]
        }
        default = ObservableExpressionLayer(scenario).evaluate(
            turn_id=3,
            previous_state={"emotion": {"anger": 7}},
            previous_dynamics={},
            state={"emotion": {"anger": 7}},
            dynamics={},
            last_trigger_turns={},
        )
        relaxed = ObservableExpressionLayer(scenario, {
            "profile": "online_relaxed_v1",
            "threshold_margin": 1,
            "crossing_as_threshold": True,
        }).evaluate(
            turn_id=3,
            previous_state={"emotion": {"anger": 7}},
            previous_dynamics={},
            state={"emotion": {"anger": 7}},
            dynamics={},
            last_trigger_turns={},
        )
        self.assertEqual(default["private_events"], [])
        self.assertEqual(len(relaxed["private_events"]), 1)
        self.assertEqual(
            relaxed["private_events"][0]["trigger_policy_profile"],
            "online_relaxed_v1",
        )

    def test_online_profile_covers_every_state_leaf_in_both_directions(self):
        scenario = json.loads(
            Path(
                "data/gpt50/experiment/scenario/scenarios/"
                "scenario_001/scenario_001.json"
            ).read_text(encoding="utf-8")
        )
        profile = build_online_multimodal_profile(scenario)
        expected = sum(
            1
            for values in scenario["initial_state"].values()
            for value in values.values()
            for threshold in (value - 1, value + 1)
            if 0 <= threshold <= 10
        )
        self.assertEqual(profile["profile"], ONLINE_MULTIMODAL_PROFILE)
        self.assertEqual(profile["trigger_count"], expected)
        covered = {
            trigger["source_state_variable"].split(".", 1)[0]
            for trigger in profile["triggers"]
        }
        self.assertEqual(
            covered,
            {
                "emotion",
                "behavioral_disposition",
                "relationship",
                "consequence_risk",
            },
        )
        self.assertTrue(profile["scenario_sha256"])
        self.assertTrue(all(
            profile["state_family_trigger_counts"][family] > 0
            for family in (
                "emotion", "behavioral_disposition", "relationship",
                "consequence_risk",
            )
        ))

    def test_online_v2_does_not_fire_at_unchanged_s0(self):
        initial = {
            "emotion": {"anxiety": 5},
            "behavioral_disposition": {"resolve": 5},
            "relationship": {"trust": 5},
            "consequence_risk": {"goal_failure_risk": 5},
        }
        layer = ObservableExpressionLayer({
            "scenario_id": "unchanged-s0",
            "initial_state": initial,
            "video_triggers": [],
        }, {
            "profile": ONLINE_MULTIMODAL_PROFILE,
            "crossing_as_threshold": True,
            "threshold_margin": 0,
        })
        result = layer.evaluate(
            turn_id=1,
            previous_state=initial,
            previous_dynamics={},
            state=initial,
            dynamics={},
            last_trigger_turns={},
        )
        self.assertEqual(result["private_events"], [])

    def test_online_v2_balances_simultaneous_events_across_state_families(self):
        initial = {
            "emotion": {"anxiety": 5, "frustration": 5},
            "behavioral_disposition": {"resolve": 5, "repair_intent": 5},
            "relationship": {"trust": 5, "respect": 5},
            "consequence_risk": {"goal_failure_risk": 5, "material_loss_risk": 5},
        }
        active = {
            family: {variable: value + 1 for variable, value in values.items()}
            for family, values in initial.items()
        }
        layer = ObservableExpressionLayer({
            "scenario_id": "family-balanced",
            "initial_state": initial,
            "video_triggers": [],
        }, {"profile": ONLINE_MULTIMODAL_PROFILE})
        runtime = {}
        families = []
        for turn_id in range(1, 8):
            result = layer.evaluate(
                turn_id=turn_id,
                previous_state=initial if turn_id == 1 else active,
                previous_dynamics={},
                state=active,
                dynamics={},
                last_trigger_turns=runtime,
            )
            if result["private_events"]:
                families.append(
                    result["private_events"][0]["source_state_family"]
                )
        self.assertEqual(
            set(families[:4]),
            {
                "emotion", "behavioral_disposition", "relationship",
                "consequence_risk",
            },
        )

    def test_online_profile_surfaces_three_events_by_turn_five_with_caps(self):
        initial = {
            "emotion": {"anxiety": 5},
            "behavioral_disposition": {"resolve": 5},
            "relationship": {"trust": 5},
            "consequence_risk": {"goal_failure_risk": 5},
        }
        scenario = {
            "scenario_id": "online-profile-test",
            "initial_state": initial,
            "video_triggers": [],
        }
        layer = ObservableExpressionLayer(
            scenario, {"profile": ONLINE_MULTIMODAL_PROFILE}
        )
        active = {
            "emotion": {"anxiety": 6},
            "behavioral_disposition": {"resolve": 6},
            "relationship": {"trust": 6},
            "consequence_risk": {"goal_failure_risk": 6},
        }
        runtime = {}
        fired = []
        for turn_id in range(1, 6):
            result = layer.evaluate(
                turn_id=turn_id,
                previous_state=initial if turn_id == 1 else active,
                previous_dynamics={},
                state=active,
                dynamics={},
                last_trigger_turns=runtime,
            )
            self.assertLessEqual(len(result["private_events"]), 1)
            if result["private_events"]:
                routed = attach_online_requests(
                    scenario, result, "The exact environment text is unchanged."
                )
                self.assertEqual(routed["video_api_requests"], [])
                self.assertEqual(
                    routed["private_events"][0]["video_api_status"],
                    "pre_generated_asset_pending",
                )
                fired.extend(result["private_events"])
        self.assertEqual(len(fired), 3)
        self.assertEqual(
            len({event["trigger_id"] for event in fired}), len(fired)
        )
        self.assertTrue(all(event["response_neutral"] for event in fired))
        self.assertTrue(all(not event["spoken_content"] for event in fired))

    def test_all_scenarios_have_no_action_transition_table(self):
        for path in sorted(Path("data/gpt50/experiment/scenario/scenarios").glob("scenario_*/scenario_*.json")):
            scenario = json.loads(path.read_text())
            validate_scenario(scenario)
            self.assertNotIn("action_effects", scenario)
            self.assertNotIn("response_templates", scenario)
            self.assertEqual(len(scenario["video_triggers"]), 3)
            self.assertEqual(
                len({trigger["priority"] for trigger in scenario["video_triggers"]}),
                3,
            )


if __name__ == "__main__":
    unittest.main()
