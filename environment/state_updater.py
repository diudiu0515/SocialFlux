"""Semantic state updates derived from an independent model appraisal."""

import json
from copy import deepcopy

from prompts.loader import render_prompt

from .appraisal import ModelAppraiser
from .delta_mapper import DELTA_LABELS, apply_semantic_deltas


class TransitionValidationError(ValueError):
    pass


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
    for key in ("appraisal", "state_delta", "interaction_dynamics_delta", "evidence_turn_ids"):
        if key not in transition:
            raise TransitionValidationError(f"transition missing {key}")
    _validate_delta_shape(state, transition["state_delta"], "state_delta")
    _validate_delta_shape(
        dynamics,
        transition["interaction_dynamics_delta"],
        "interaction_dynamics_delta",
    )
    if not isinstance(transition["appraisal"], dict):
        raise TransitionValidationError("appraisal must be an object")
    return transition


def apply_transition(state, dynamics, transition):
    validate_transition(transition, state, dynamics)
    new_state, state_numeric = apply_semantic_deltas(state, transition["state_delta"])
    new_dynamics, dynamics_numeric = apply_semantic_deltas(
        dynamics,
        transition["interaction_dynamics_delta"],
    )
    return new_state, new_dynamics, state_numeric, dynamics_numeric


class ModelStateUpdater:
    def __init__(self, scenario, provider, sampling=None, appraiser=None):
        self.scenario = deepcopy(scenario)
        self.provider = provider
        self.sampling = dict(sampling or {})
        self.appraiser = appraiser or ModelAppraiser(scenario, provider, sampling)

    @property
    def provenance(self):
        return {
            **getattr(self.provider, "provenance", {}),
            "appraisal_prompt_id": "environment_appraisal_v2",
            "state_update_prompt_id": "state_update_v1",
            "sampling": dict(self.sampling),
        }

    def update(self, *, action, previous_state, previous_dynamics, memory):
        appraisal = self.appraiser.appraise(
            action=action,
            previous_state=previous_state,
            previous_dynamics=previous_dynamics,
            memory=memory,
        )
        prompt = render_prompt("state_update_v1", {
            "previous_state": previous_state,
            "previous_dynamics": previous_dynamics,
            "appraisal": appraisal["appraisal"],
            "relevant_memory": memory,
        })
        raw = self.provider.complete(
            [{"role": "user", "content": prompt}],
            **self.sampling,
        )
        try:
            deltas = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TransitionValidationError("model state updater returned invalid JSON") from exc
        transition = {
            "appraisal": appraisal["appraisal"],
            "evidence_turn_ids": appraisal["evidence_turn_ids"],
            "state_delta": deltas.get("state_delta"),
            "interaction_dynamics_delta": deltas.get("interaction_dynamics_delta"),
        }
        return validate_transition(transition, previous_state, previous_dynamics)
