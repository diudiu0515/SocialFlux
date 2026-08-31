"""Appraisal and state-update contracts for the Phase-A environment."""

import json
from copy import deepcopy
from .delta_mapper import DELTA_LABELS, apply_semantic_deltas
from .prompts import build_appraisal_prompt


class TransitionValidationError(ValueError):
    pass


def _fill_like(state, value="similar"):
    if any(isinstance(v, dict) for v in state.values()):
        return {group: _fill_like(values, value) for group, values in state.items()}
    return {key: value for key in state}


def _validate_delta_shape(state, delta, path=""):
    if not isinstance(delta, dict):
        raise TransitionValidationError(f"{path or 'delta'} must be an object")
    expected = set(state)
    if set(delta) != expected:
        missing, extra = expected - set(delta), set(delta) - expected
        raise TransitionValidationError(
            f"{path or 'delta'} variables mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    for key, value in state.items():
        current = f"{path}.{key}" if path else key
        if isinstance(value, dict):
            _validate_delta_shape(value, delta[key], current)
        elif delta[key] not in DELTA_LABELS:
            raise TransitionValidationError(f"{current} has invalid delta {delta[key]!r}")


def validate_transition(transition, state, dynamics):
    if not isinstance(transition, dict):
        raise TransitionValidationError("transition must be an object")
    for key in ("appraisal", "state_delta", "interaction_dynamics_delta"):
        if key not in transition:
            raise TransitionValidationError(f"transition missing {key}")
    _validate_delta_shape(state, transition["state_delta"], "state_delta")
    _validate_delta_shape(dynamics, transition["interaction_dynamics_delta"], "interaction_dynamics_delta")
    return transition


def apply_transition(state, dynamics, transition):
    validate_transition(transition, state, dynamics)
    new_state, state_numeric = apply_semantic_deltas(state, transition["state_delta"])
    new_dynamics, dynamics_numeric = apply_semantic_deltas(
        dynamics, transition["interaction_dynamics_delta"]
    )
    return new_state, new_dynamics, state_numeric, dynamics_numeric


class RuleBasedStateUpdater:
    """Deterministic fallback; production rollouts can replace this component."""

    def __init__(self, scenario):
        self.scenario = scenario

    def update(self, *, action, previous_state, previous_dynamics, memory):
        action_id = action.get("action_id") if isinstance(action, dict) else "default"
        effect = self.scenario.get("action_effects", {}).get(action_id or "default", {})
        transition = {
            "appraisal": {
                "other_party_intent": action.get("text", "") if isinstance(action, dict) else str(action),
                "goal_alignment": effect.get("goal_alignment", "unknown"),
                "hidden_intention_effect": effect.get("hidden_intention_effect", "unknown"),
                "persona_conditioned_interpretation": effect.get("interpretation", "rule_based"),
                "relevant_history": memory.get("relevant_turn_ids", []),
            },
            "state_delta": deepcopy(effect.get("state_delta", _fill_like(previous_state))),
            "interaction_dynamics_delta": deepcopy(
                effect.get("interaction_dynamics_delta", _fill_like(previous_dynamics))
            ),
            "evidence_turn_ids": memory.get("relevant_turn_ids", []),
        }
        return validate_transition(transition, previous_state, previous_dynamics)


class ModelStateUpdater:
    """Provider-backed updater using the versioned appraisal prompt catalog."""

    def __init__(self, scenario, provider):
        self.scenario = scenario
        self.provider = provider

    def update(self, *, action, previous_state, previous_dynamics, memory):
        agent = self.scenario["environment_agent"]
        prompt = build_appraisal_prompt(
            persona=agent["persona"],
            background=agent["background"],
            explicit_goal=agent["explicit_goal"],
            hidden_intention=agent["hidden_intention"],
            previous_state=previous_state,
            previous_dynamics=previous_dynamics,
            memory=memory,
            action=action,
        )
        raw = self.provider.complete([{"role": "user", "content": prompt}])
        try:
            transition = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TransitionValidationError("model state updater returned invalid JSON") from exc
        return validate_transition(transition, previous_state, previous_dynamics)
