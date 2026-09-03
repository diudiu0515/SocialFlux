import json
import unittest
from pathlib import Path

from environment.state_updater import ModelStateUpdater, canonicalize_bounded_transition


SCENARIO = json.loads(
    Path("configs/scenarios/scenario_001/scenario_001.json").read_text(encoding="utf-8")
)


def _fill(values, label="similar"):
    return {
        key: _fill(value, label) if isinstance(value, dict) else label
        for key, value in values.items()
    }


class SequencedProvider:
    provenance = {"provider": "test-double", "model": "sequenced"}

    def __init__(self):
        self.calls = []

    def complete(self, messages, **generation):
        self.calls.append(messages[0]["content"])
        if len(self.calls) == 1:
            return json.dumps({
                "appraisal": {
                    "other_party_intent": "核对事实",
                    "explicit_goal_effect": "有助于澄清",
                    "hidden_intention_effect": "降低被忽视感",
                    "persona_conditioned_interpretation": "谨慎接受",
                    "history_conditioned_interpretation": "与前史一致",
                },
                "evidence_turn_ids": [],
            }, ensure_ascii=False)
        return json.dumps({
            "state_delta": _fill(SCENARIO["initial_state"]),
            "interaction_dynamics_delta": _fill(SCENARIO["initial_dynamics"]),
        }, ensure_ascii=False)


class ModelEnvironmentBoundaryTest(unittest.TestCase):
    def test_semantic_delta_matches_bounded_numeric_effect(self):
        transition = {
            "appraisal": {},
            "evidence_turn_ids": [],
            "state_delta": {"at_ceiling": "strong_increase", "near_floor": "strong_decrease"},
            "interaction_dynamics_delta": {"near_ceiling": "moderate_increase"},
        }
        normalized = canonicalize_bounded_transition(
            transition,
            {"at_ceiling": 10, "near_floor": 1},
            {"near_ceiling": 9},
        )
        self.assertEqual(normalized["state_delta"]["at_ceiling"], "similar")
        self.assertEqual(normalized["state_delta"]["near_floor"], "mild_decrease")
        self.assertEqual(
            normalized["interaction_dynamics_delta"]["near_ceiling"],
            "mild_increase",
        )

    def test_appraisal_and_state_update_are_separate_model_calls(self):
        provider = SequencedProvider()
        updater = ModelStateUpdater(SCENARIO, provider, {"temperature": 0})
        transition = updater.update(
            action={"text": "我想先核对双方记录。"},
            previous_state=SCENARIO["initial_state"],
            previous_dynamics=SCENARIO["initial_dynamics"],
            memory={"relevant_turn_ids": [], "events": []},
        )
        self.assertEqual(len(provider.calls), 2)
        self.assertIn("latest arbitrary natural-language action", provider.calls[0])
        self.assertIn("convert a completed appraisal", provider.calls[1])
        self.assertNotIn("我想先核对双方记录", provider.calls[1])
        self.assertEqual(transition["state_delta"]["emotion"]["anger"], "similar")


if __name__ == "__main__":
    unittest.main()
