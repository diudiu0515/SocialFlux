"""Validate the scenario's initial latent state and runtime dynamics seed."""

from copy import deepcopy

from schemas.validate import (
    STATE_CONTRACT_VERSION,
    validate_v2_dynamics,
    validate_v2_state_selection,
)


def _validate_group(value, path):
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    for key, item in value.items():
        if isinstance(item, dict):
            _validate_group(item, f"{path}.{key}")
        elif (
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not 0 <= item <= 10
        ):
            raise ValueError(f"{path}.{key} must be numeric in [0, 10]")


def freeze_initialization(scenario):
    """Return the immutable initial state and runtime dynamics seed."""
    state = scenario.get("initial_state")
    dynamics = scenario.get("initial_dynamics", {})
    if not isinstance(state, dict) or not state:
        raise ValueError("scenario.initial_state must be a non-empty object")
    if not isinstance(dynamics, dict):
        raise ValueError("scenario.initial_dynamics must be an object")
    _validate_group(state, "initial_state")
    _validate_group(dynamics, "initial_dynamics")
    if scenario.get("state_contract_version") == STATE_CONTRACT_VERSION:
        selected = scenario.get("selected_state_variables")
        if not isinstance(selected, dict):
            raise ValueError("v2 scenario requires selected_state_variables")
        validate_v2_state_selection(selected)
        if set(state) != set(selected):
            raise ValueError(
                "v2 initial_state must contain exactly the four selected state families"
            )
        for family, variables in selected.items():
            if (
                not isinstance(state.get(family), dict)
                or set(state[family]) != set(variables)
            ):
                raise ValueError(
                    f"v2 initial_state variables do not match selected family {family}"
                )
        validate_v2_dynamics(dynamics)
    return {
        "initial_state": deepcopy(state),
        "initial_dynamics": deepcopy(dynamics),
    }
