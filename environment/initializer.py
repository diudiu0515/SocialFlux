"""Validate and freeze the scenario's initial latent state and dynamics."""

from copy import deepcopy


def _validate_group(value, path):
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    for key, item in value.items():
        if isinstance(item, dict):
            _validate_group(item, f"{path}.{key}")
        elif not isinstance(item, (int, float)) or not 0 <= item <= 10:
            raise ValueError(f"{path}.{key} must be numeric in [0, 10]")


def freeze_initialization(scenario):
    """Return a deep-copied S0/D0 shared by every policy rollout."""
    state = scenario.get("initial_state")
    dynamics = scenario.get("initial_dynamics", {})
    if not isinstance(state, dict) or not state:
        raise ValueError("scenario.initial_state must be a non-empty object")
    if not isinstance(dynamics, dict):
        raise ValueError("scenario.initial_dynamics must be an object")
    _validate_group(state, "initial_state")
    _validate_group(dynamics, "initial_dynamics")
    return {"initial_state": deepcopy(state), "initial_dynamics": deepcopy(dynamics)}
