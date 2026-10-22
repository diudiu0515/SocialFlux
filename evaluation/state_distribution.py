"""Distribution diagnostics for calibrated latent-state trajectories."""

from __future__ import annotations

from collections import Counter, defaultdict

from environment.delta_mapper import flatten_state


def _sign(value):
    return 0 if value == 0 else (1 if value > 0 else -1)


def summarize_state_distribution(trajectories):
    magnitude = Counter()
    change_frequency = Counter()
    opportunity = Counter()
    changed_per_turn = []
    saturation_count = 0
    state_value_count = 0
    oscillations = 0
    consecutive_nonzero_pairs = 0
    prior_sign = defaultdict(dict)

    for trajectory in trajectories:
        trajectory_id = trajectory.get("trajectory_id", "unknown")
        for turn in trajectory.get("turns", []):
            state_delta = {
                f"state.{key}": value
                for key, value in flatten_state(turn.get("numeric_state_delta", {})).items()
            }
            dynamics_delta = {
                f"dynamics.{key}": value
                for key, value in flatten_state(turn.get("numeric_dynamics_delta", {})).items()
            }
            combined = {**state_delta, **dynamics_delta}
            changed_per_turn.append(sum(value != 0 for value in combined.values()))
            for variable, value in combined.items():
                opportunity[variable] += 1
                magnitude[abs(value)] += 1
                if value != 0:
                    change_frequency[variable] += 1
                    previous = prior_sign[trajectory_id].get(variable)
                    if previous is not None:
                        consecutive_nonzero_pairs += 1
                        if previous != _sign(value):
                            oscillations += 1
                    prior_sign[trajectory_id][variable] = _sign(value)
            for value in flatten_state(turn.get("state_after", {})).values():
                state_value_count += 1
                saturation_count += value in {0, 10}

    total_dimensions = sum(magnitude.values())
    turn_count = len(changed_per_turn)
    ratios = {
        name: round(magnitude[level] / total_dimensions, 4) if total_dimensions else 0.0
        for name, level in (("similar", 0), ("mild", 1), ("moderate", 2), ("strong", 3))
    }
    return {
        "trajectory_count": len(trajectories),
        "turn_count": turn_count,
        "dimension_observation_count": total_dimensions,
        "delta_ratio": ratios,
        "mean_changed_variables_per_turn": round(
            sum(changed_per_turn) / turn_count, 4
        ) if turn_count else 0.0,
        "per_variable_change_frequency": {
            variable: round(change_frequency[variable] / count, 4)
            for variable, count in sorted(opportunity.items())
        },
        "oscillation_rate": round(
            oscillations / consecutive_nonzero_pairs, 4
        ) if consecutive_nonzero_pairs else 0.0,
        "oscillation_count": oscillations,
        "saturation_ratio": round(
            saturation_count / state_value_count, 4
        ) if state_value_count else 0.0,
    }


def compare_state_distributions(before, after):
    comparable = bool(before.get("turn_count")) and bool(after.get("turn_count"))
    return {
        "comparison_status": (
            "comparable" if comparable else "insufficient_after_samples"
        ),
        "before": before,
        "after": after,
        "change": {
            "similar_ratio": round(
                after["delta_ratio"]["similar"] - before["delta_ratio"]["similar"], 4
            ) if comparable else None,
            "mean_changed_variables_per_turn": round(
                after["mean_changed_variables_per_turn"]
                - before["mean_changed_variables_per_turn"], 4
            ) if comparable else None,
            "oscillation_rate": round(
                after["oscillation_rate"] - before["oscillation_rate"], 4
            ) if comparable else None,
            "saturation_ratio": round(
                after["saturation_ratio"] - before["saturation_ratio"], 4
            ) if comparable else None,
        },
    }
