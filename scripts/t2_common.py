"""Compatibility imports for historical T2 experiment scripts.

Production ownership lives in :mod:`tasks.T2.runtime`. New code must import
that module directly.
"""

from tasks.T2.runtime import (
    DIRECTIONS,
    ROOT,
    atomic,
    call_count,
    environment_call_counts,
    environment_for,
    flat_private,
    internal_direction,
    load,
    now,
    public_events,
    public_turn,
    scenario_path,
    selected_state_ids,
    supported_t2_candidates,
    target_preference_ids,
)


__all__ = [
    "DIRECTIONS",
    "ROOT",
    "atomic",
    "call_count",
    "environment_call_counts",
    "environment_for",
    "flat_private",
    "internal_direction",
    "load",
    "now",
    "public_events",
    "public_turn",
    "scenario_path",
    "selected_state_ids",
    "supported_t2_candidates",
    "target_preference_ids",
]
