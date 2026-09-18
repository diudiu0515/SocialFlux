"""Shared direction/change/reversal/ordinal metrics for environment transitions."""

from __future__ import annotations

from environment.delta_mapper import flatten_state


def sign(value):
    return 0 if value == 0 else (1 if value > 0 else -1)


def compare_numeric_groups(left, right):
    left_flat = flatten_state(left)
    right_flat = flatten_state(right)
    keys = sorted(set(left_flat) & set(right_flat))
    if not keys:
        return {
            "variable_count": 0,
            "exact_direction_agreement": 1.0,
            "change_no_change_agreement": 1.0,
            "true_sign_reversal_rate": 0.0,
            "mean_ordinal_delta_distance": 0.0,
            "left_numeric_delta": left_flat,
            "right_numeric_delta": right_flat,
        }
    exact = sum(sign(left_flat[key]) == sign(right_flat[key]) for key in keys)
    change = sum(
        (sign(left_flat[key]) == 0) == (sign(right_flat[key]) == 0)
        for key in keys
    )
    reversals = sum(
        sign(left_flat[key]) * sign(right_flat[key]) == -1 for key in keys
    )
    distance = sum(abs(left_flat[key] - right_flat[key]) for key in keys)
    return {
        "variable_count": len(keys),
        "exact_direction_agreement": round(exact / len(keys), 4),
        "change_no_change_agreement": round(change / len(keys), 4),
        "true_sign_reversal_rate": round(reversals / len(keys), 4),
        "mean_ordinal_delta_distance": round(distance / len(keys), 4),
        "left_numeric_delta": left_flat,
        "right_numeric_delta": right_flat,
    }


def compare_transition_outputs(left, right):
    state = compare_numeric_groups(
        left["numeric_state_delta"], right["numeric_state_delta"]
    )
    dynamics = compare_numeric_groups(
        left.get("numeric_dynamics_delta", {}), right.get("numeric_dynamics_delta", {})
    )
    left_overall = {
        **{f"state.{key}": value for key, value in state["left_numeric_delta"].items()},
        **{f"dynamics.{key}": value for key, value in dynamics["left_numeric_delta"].items()},
    }
    right_overall = {
        **{f"state.{key}": value for key, value in state["right_numeric_delta"].items()},
        **{f"dynamics.{key}": value for key, value in dynamics["right_numeric_delta"].items()},
    }
    overall = compare_numeric_groups(left_overall, right_overall)
    return {"state": state, "dynamics": dynamics, "overall": overall}
