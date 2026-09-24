"""Prepare auditable Gate-2 evidence for state-timescale validity.

The simulator statistics in this module are review aids, not ground truth.  A
human reviewer still decides whether a variable changed at a contextually
reasonable speed.  In particular, consequence risk is intentionally marked
``context_dependent`` instead of being forced into one global timescale.
"""

from __future__ import annotations

from collections import Counter
import hashlib

from environment.delta_mapper import flatten_state


FAMILY_TIMESCALE_PRIORS = {
    "emotion": "fast",
    "behavioral_disposition": "medium",
    "relationship": "slow",
    "consequence_risk": "context_dependent",
}


def _stable_rank(value):
    return hashlib.sha256(
        f"socialflux-timescale-v1:{value}".encode("utf-8")
    ).hexdigest()


def _numeric_deltas(turn):
    provided = flatten_state(turn.get("numeric_state_delta", {}))
    if provided:
        return provided
    before = flatten_state(turn.get("state_before", {}))
    after = flatten_state(turn.get("state_after", {}))
    return {
        variable: after[variable] - value
        for variable, value in before.items()
        if variable in after
    }


def _reversal_count(nonzero_deltas):
    signs = [1 if value > 0 else -1 for value in nonzero_deltas]
    return sum(left != right for left, right in zip(signs, signs[1:]))


def trajectory_timescale_items(trajectory):
    """Return one private diagnostic item per state variable in a trajectory."""
    by_variable = {}
    turns = trajectory.get("turns", [])
    for turn in turns:
        turn_id = turn.get("turn_id")
        for variable, value in _numeric_deltas(turn).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            by_variable.setdefault(variable, []).append((turn_id, value))

    items = []
    for variable, observations in sorted(by_variable.items()):
        family = variable.split(".", 1)[0]
        if family not in FAMILY_TIMESCALE_PRIORS:
            continue
        changes = [(turn_id, value) for turn_id, value in observations if value]
        nonzero = [value for _, value in changes]
        item_id = (
            f"E9:{trajectory.get('scenario_id')}:{trajectory.get('trajectory_id')}:"
            f"{variable}"
        )
        items.append({
            "review_id": item_id,
            "scenario_id": trajectory.get("scenario_id"),
            "source_trajectory_id": trajectory.get("trajectory_id"),
            "state_id": variable,
            "state_family": family,
            "expected_timescale_prior": FAMILY_TIMESCALE_PRIORS[family],
            "turn_count": len(turns),
            "changed_turn_count": len(changes),
            "change_rate": round(len(changes) / len(turns), 4) if turns else 0.0,
            "total_absolute_change": sum(abs(value) for value in nonzero),
            "maximum_single_turn_change": max(
                (abs(value) for value in nonzero), default=0
            ),
            "net_change": sum(nonzero),
            "reversal_count": _reversal_count(nonzero),
            "evidence_turn_ids": [turn_id for turn_id, _ in changes],
            "review": {
                "observed_timescale": None,
                "contextually_valid": None,
                "direction_consistent": None,
                "rationale": "",
            },
        })
    return items


def build_timescale_review_items(trajectories, limit=40):
    """Build a deterministic, family-covered sample for Gate-2 human review."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("timescale review limit must be a positive integer")
    candidates = [
        item
        for trajectory in trajectories
        for item in trajectory_timescale_items(trajectory)
    ]
    ordered = sorted(candidates, key=lambda item: _stable_rank(item["review_id"]))

    selected = []
    selected_ids = set()
    # Preserve the three explicit priors before filling the rest of the sample.
    for timescale in ("fast", "medium", "slow"):
        match = next(
            (
                item for item in ordered
                if item["expected_timescale_prior"] == timescale
                and item["review_id"] not in selected_ids
            ),
            None,
        )
        if match is not None:
            selected.append(match)
            selected_ids.add(match["review_id"])
    for item in ordered:
        if len(selected) >= limit:
            break
        if item["review_id"] not in selected_ids:
            selected.append(item)
            selected_ids.add(item["review_id"])
    return selected[:limit]


def pending_timescale_payload(trajectories, limit=40):
    """Return an E9 artifact that cannot accidentally claim human approval."""
    review_items = build_timescale_review_items(trajectories, limit=limit)
    family_counts = Counter(
        item["expected_timescale_prior"] for item in review_items
    )
    changed = sum(item["changed_turn_count"] > 0 for item in review_items)
    return {
        "format": "socialflux_timescale_validity_v1",
        "record": {
            "passed": None,
            "human_attestation": False,
            "reviewers": [],
            "reviewed_at_utc": "",
            "review_status": "pending_human",
            "candidate_variable_count": len(review_items),
            "matched_variable_count": 0,
            "timescale_families": dict(sorted(family_counts.items())),
            "direction_consistency": None,
            "non_degenerate": changed > 0,
        },
        "review_items": review_items,
        "interpretation": {
            "fast": "May react within one or a few turns when supported by evidence.",
            "medium": "Usually changes across several relevant interaction moves.",
            "slow": "Requires accumulated or especially diagnostic relational evidence.",
            "context_dependent": (
                "May jump after an acute threat or accumulate across repeated risk events."
            ),
            "warning": (
                "These simulator summaries are review aids; they are not formal labels."
            ),
        },
    }


def machine_timescale_packet_ready(payload, minimum=10):
    """Check packet coverage only; do not infer human validity or Gate-2 pass."""
    record = (payload or {}).get("record", payload or {})
    candidate_count = max(
        int(record.get("candidate_variable_count", 0) or 0),
        int(record.get("matched_variable_count", 0) or 0),
    )
    families = record.get("timescale_families", {})
    return (
        candidate_count >= minimum
        and isinstance(families, dict)
        and all(int(families.get(name, 0) or 0) >= 1 for name in ("fast", "medium", "slow"))
    )
