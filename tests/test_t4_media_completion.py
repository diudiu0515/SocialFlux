import json
from copy import deepcopy
from pathlib import Path
import unittest

from environment.env import StatefulEnvironment
from environment.multimodal import ObservableExpressionLayer, media_completion_guard
from environment.online_multimodal import ONLINE_EVENT_FAMILIES
from environment.state_updater import validate_transition
from policies.model_policy import ModelPolicy
from rollout.runner import RolloutRunner
from scripts.run_t4_multimodal_experiment import configure_media_completion
from tests.support import ContextualTestUpdater


class ClosingUpdater(ContextualTestUpdater):
    def __init__(self, scenario, event_turn=1):
        super().__init__(scenario)
        self.event_turn = event_turn
        self.calls = 0

    def update(self, *, action, previous_state, previous_dynamics, memory):
        self.calls += 1
        state_delta = self._fill(previous_state, "similar")
        if self.calls == self.event_turn:
            variable = next(iter(previous_state["emotion"]))
            state_delta["emotion"][variable] = (
                "mild_increase" if previous_state["emotion"][variable] < 10 else "mild_decrease"
            )
        return validate_transition({
            "appraisal": {
                "exact_action": action["text"],
                "dialogue_diagnostics": {
                    "continuation": {
                        "status": "continue" if self.event_turn and self.calls < self.event_turn else "can_close",
                    }
                },
            },
            "state_delta": state_delta,
            "interaction_dynamics_delta": self._fill(previous_dynamics, "similar"),
            "evidence_turn_ids": memory["relevant_turn_ids"],
        }, previous_state, previous_dynamics)


class ClosingResponse:
    horizon_mode = "natural_max_20"
    provenance = {"provider": "test-double", "model": "closing-response"}

    def generate(self, context):
        return "收到。"


class CaptureProvider:
    provenance = {"provider": "test-double", "model": "capture"}

    def __init__(self):
        self.requests = []

    def complete(self, messages, **sampling):
        self.requests.append(deepcopy(messages))
        return "确认收到。"


class MediaCompletionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = json.loads(Path(
            "data/gpt50/experiment/scenario/scenarios/scenario_001/scenario_001.json"
        ).read_text())

    def run_case(self, *, enabled, condition="text_video", event_turn=1, max_turns=20,
                 termination_conditions=None):
        scenario = deepcopy(self.scenario)
        scenario["max_turns"] = max_turns
        scenario["termination_conditions"] = termination_conditions or []
        settings = {
            "profile": "online_multimodal_v2",
            "defer_first_media_completion": enabled,
            "event_assets": {
                scenario["scenario_id"]: {
                    family: {"asset_url": f"https://assets.example.test/{family}.mp4"}
                    for family in ONLINE_EVENT_FAMILIES
                }
            },
        }
        provider = CaptureProvider()
        policy = ModelPolicy(
            "test-policy", provider, prompt_id="task_t4_action_v21",
            validation_profile="hard_only", observation_condition=condition,
            media_input_format="openai_video_url" if condition == "text_video" else None,
            minimum_natural_turns=1,
        )
        factory = lambda: StatefulEnvironment(
            scenario, state_updater=ClosingUpdater(scenario, event_turn),
            response_generator=ClosingResponse(), multimodal_trigger_policy=settings,
        )
        return RolloutRunner(factory).run(policy, max_turns=max_turns), provider.requests

    def test_default_keeps_original_natural_ending(self):
        trajectory, requests = self.run_case(enabled=False)
        self.assertEqual(len(requests), 1)
        self.assertEqual(trajectory["ending"]["reason"], "natural_completion")
        self.assertEqual(len(trajectory["turns"][0]["trigger_events"]), 1)
        self.assertNotIn("media_completion_guard", trajectory["turns"][0])

    def test_first_event_has_one_followup_and_conditions_share_text_and_state(self):
        text, text_calls = self.run_case(enabled=True, condition="text_only")
        video, video_calls = self.run_case(enabled=True)
        self.assertEqual(len(text_calls), 2)
        self.assertEqual(len(video_calls), 2)
        self.assertEqual(video["ending"], {"reason": "natural_completion", "turn_id": 2})
        self.assertEqual(text["ending"], video["ending"])
        self.assertTrue(video["turns"][0]["media_completion_guard"]["natural_completion_deferred"])
        self.assertFalse(video["turns"][1]["media_completion_guard"]["natural_completion_deferred"])
        self.assertEqual(text_calls[0], video_calls[0])
        self.assertEqual(video_calls[1][1]["content"][0], {"type": "text", "text": text_calls[1][1]["content"]})
        self.assertEqual(video_calls[1][1]["content"][1]["type"], "video_url")
        original, _ = self.run_case(enabled=False)
        self.assertEqual(original["turns"][0]["state_after"], video["turns"][0]["state_after"])
        self.assertEqual(original["turns"][0]["environment_response"], video["turns"][0]["environment_response"])
        for a, b in zip(text["turns"], video["turns"]):
            self.assertEqual(a["state_after"], b["state_after"])
        self.assertNotIn("media_completion_guard", json.dumps(video_calls, ensure_ascii=False))

    def test_unchanged_state_does_not_force_media_or_another_turn(self):
        trajectory, requests = self.run_case(enabled=True, event_turn=None)
        self.assertEqual(len(requests), 1)
        self.assertEqual(trajectory["turns"][0]["trigger_events"], [])
        self.assertFalse(trajectory["turns"][0]["media_completion_guard"]["natural_completion_deferred"])

    def test_hard_turn_cap_and_explicit_scenario_stop_remain_effective(self):
        for options in ({"max_turns": 1}, {
            "termination_conditions": [{"type": "turns", "value": 1, "reason": "fixed_stop"}]
        }):
            with self.subTest(options=options):
                trajectory, requests = self.run_case(enabled=True, **options)
                self.assertEqual(len(requests), 1)
                guard = trajectory["turns"][0]["media_completion_guard"]
                self.assertTrue(guard["hard_termination"])
                self.assertFalse(guard["natural_completion_deferred"])
                self.assertIn(trajectory["ending"]["reason"], ("max_turns", "fixed_stop"))

    def test_first_event_later_in_dialogue_also_gets_one_followup(self):
        trajectory, requests = self.run_case(enabled=True, event_turn=2)
        self.assertEqual(len(requests), 3)
        self.assertTrue(trajectory["turns"][1]["media_completion_guard"]["natural_completion_deferred"])
        self.assertEqual(trajectory["ending"]["turn_id"], 3)

    def test_later_events_never_extend_the_first_event_rule(self):
        result = media_completion_guard(
            {"defer_first_media_completion": True}, turn_id=3,
            previous_trigger_turns={"__event_count__": 1},
            multimodal={"private_events": [{"media_type": "video"}],
                        "media": [{"media_type": "video", "asset_status": "available"}]},
            natural_completion=True, hard_termination=False,
        )
        self.assertFalse(result["natural_completion_deferred"])

    def test_unavailable_media_does_not_extend_dialogue(self):
        result = media_completion_guard(
            {"defer_first_media_completion": True}, turn_id=1,
            previous_trigger_turns={},
            multimodal={"private_events": [{"media_type": "video"}],
                        "media": [{"media_type": "video", "asset_status": "planned"}]},
            natural_completion=True, hard_termination=False,
        )
        self.assertFalse(result["natural_completion_deferred"])

    def test_versioned_configuration_is_opt_in_and_validated(self):
        base = {"multimodal_trigger_policy": {"profile": "online_multimodal_v2"}}
        self.assertEqual(configure_media_completion(base, {}), base)
        configured = configure_media_completion(base, {"media_completion_policy": "first_event_response_v1"})
        self.assertTrue(configured["multimodal_trigger_policy"]["defer_first_media_completion"])
        self.assertNotIn("defer_first_media_completion", base["multimodal_trigger_policy"])
        with self.assertRaises(ValueError):
            configure_media_completion(base, {"media_completion_policy": "unknown"})
        for flag in ("true", 1, None):
            with self.assertRaises(ValueError):
                ObservableExpressionLayer(self.scenario, {
                    "profile": "online_multimodal_v2", "defer_first_media_completion": flag,
                })


if __name__ == "__main__":
    unittest.main()
