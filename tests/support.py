"""Test-only free-form policies and deterministic component doubles."""

from copy import deepcopy

from environment.env import StatefulEnvironment
from environment.state_updater import validate_transition


class TextPolicy:
    def __init__(self, policy_id, actions, model="test-model", seed=1):
        self.policy_id = policy_id
        self.actions = list(actions)
        self.index = 0
        self.provenance = {
            "policy_id": policy_id,
            "provider": "test-double",
            "model": model,
            "prompt_id": "task_t4_action_v2",
            "sampling": {"temperature": 0.5, "seed": seed},
        }

    def reset(self):
        self.index = 0

    def generate(self, observation):
        action = self.actions[min(self.index, len(self.actions) - 1)]
        self.index += 1
        return {"text": action}


class ContextualTestUpdater:
    """A test double, not a production transition implementation."""

    provenance = {"provider": "test-double", "model": "contextual-updater"}

    def __init__(self, scenario):
        self.scenario = scenario

    def _fill(self, values, label):
        return {
            key: self._fill(value, label) if isinstance(value, dict) else label
            for key, value in values.items()
        }

    def update(self, *, action, previous_state, previous_dynamics, memory):
        text = action["text"]
        if "证据" in text or "解释" in text:
            state_label, dynamics_label = "mild_decrease", "mild_decrease"
        elif "程序" in text or "责任" in text:
            state_label, dynamics_label = "mild_increase", "mild_increase"
        else:
            state_label, dynamics_label = "similar", "similar"
        transition = {
            "appraisal": {
                "interpretation": f"test appraisal of exact text: {text}",
                "relevant_history": memory["relevant_turn_ids"],
            },
            "state_delta": self._fill(previous_state, state_label),
            "interaction_dynamics_delta": self._fill(previous_dynamics, dynamics_label),
            "evidence_turn_ids": memory["relevant_turn_ids"],
        }
        return validate_transition(transition, previous_state, previous_dynamics)


class ContextualTestResponse:
    provenance = {"provider": "test-double", "model": "contextual-response"}

    def generate(self, context):
        return "我听到你的具体说法：" + context["action"]["text"]


def environment_factory(scenario):
    def build():
        return StatefulEnvironment(
            deepcopy(scenario),
            state_updater=ContextualTestUpdater(scenario),
            response_generator=ContextualTestResponse(),
            provenance={
                "environment": {"provider": "test-double", "model": "test-environment"},
                "state_prompt": "test-only",
                "response_prompt": "test-only",
            },
        )
    return build
