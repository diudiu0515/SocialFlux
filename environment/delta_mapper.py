"""Map semantic seven-level deltas to bounded numeric state updates."""

DELTA_LABELS = (
    "strong_decrease", "moderate_decrease", "mild_decrease", "similar",
    "mild_increase", "moderate_increase", "strong_increase",
)
DELTA_TO_INT = {
    "strong_decrease": -3, "moderate_decrease": -2, "mild_decrease": -1,
    "similar": 0, "mild_increase": 1, "moderate_increase": 2,
    "strong_increase": 3,
}


def _apply_group(state_group, delta_group, minimum, maximum):
    updated, numeric = {}, {}
    delta_group = delta_group or {}
    for key, value in state_group.items():
        label = delta_group.get(key, "similar")
        if label not in DELTA_TO_INT:
            raise ValueError(f"invalid delta label for {key}: {label!r}")
        amount = DELTA_TO_INT[label]
        updated[key] = max(minimum, min(maximum, value + amount))
        numeric[key] = updated[key] - value
    unknown = set(delta_group) - set(state_group)
    if unknown:
        raise ValueError(f"delta contains unselected state variables: {sorted(unknown)}")
    return updated, numeric


def apply_semantic_deltas(state, semantic_deltas, minimum=0, maximum=10):
    """Return updated state and numeric deltas for grouped or flat states."""
    if not isinstance(state, dict) or not isinstance(semantic_deltas, dict):
        raise TypeError("state and semantic_deltas must be objects")
    updated, numeric = {}, {}
    grouped = any(isinstance(value, dict) for value in state.values())
    if grouped:
        for group, values in state.items():
            if not isinstance(values, dict):
                raise TypeError("mixed flat and grouped state is not supported")
            updated[group], numeric[group] = _apply_group(
                values, semantic_deltas.get(group), minimum, maximum
            )
        unknown_groups = set(semantic_deltas) - set(state)
        if unknown_groups:
            raise ValueError(f"delta contains unselected groups: {sorted(unknown_groups)}")
        return updated, numeric
    return _apply_group(state, semantic_deltas, minimum, maximum)


def flatten_state(state):
    """Return stable group.variable keys for metrics and logging."""
    if any(isinstance(v, dict) for v in state.values()):
        return {
            f"{group}.{key}": value
            for group, values in state.items()
            for key, value in values.items()
        }
    return dict(state)
