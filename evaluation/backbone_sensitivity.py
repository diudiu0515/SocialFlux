"""Metrics for simulator-backbone sensitivity at matched checkpoints."""

from __future__ import annotations

from .transition_metrics import compare_transition_outputs


def compare_transitions(left, right):
    groups = compare_transition_outputs(left, right)
    state = groups["state"]
    dynamics = groups["dynamics"]
    overall = groups["overall"]
    active_direction = overall["active_union_direction_agreement"]
    active_change = overall["active_union_change_no_change_agreement"]
    active_reversal = overall["active_union_true_sign_reversal_rate"]
    return {
        "variable_count": overall["variable_count"],
        # Gate agreement is evaluated on dimensions where at least one
        # backbone proposed a change. Counting zero/zero dimensions here made
        # sparse transitions look robust without testing backbone sensitivity.
        "direction_agreement": active_direction if active_direction is not None else 0.0,
        "active_union_direction_agreement": active_direction,
        "active_union_change_no_change_agreement": active_change,
        "active_union_true_sign_reversal_rate": active_reversal,
        "active_union_count": overall["active_union_count"],
        "both_changed_count": overall["both_changed_count"],
        "both_changed_direction_agreement": overall[
            "both_changed_direction_agreement"
        ],
        "zero_zero_count": overall["zero_zero_count"],
        "zero_zero_fraction": overall["zero_zero_fraction"],
        "all_dimension_direction_agreement": overall["exact_direction_agreement"],
        "all_dimension_change_no_change_agreement": overall[
            "change_no_change_agreement"
        ],
        "all_dimension_true_sign_reversal_rate": overall[
            "true_sign_reversal_rate"
        ],
        "exact_direction_agreement": overall["exact_direction_agreement"],
        "change_no_change_agreement": active_change if active_change is not None else 0.0,
        "severe_reversal_fraction": active_reversal if active_reversal is not None else 0.0,
        "true_sign_reversal_rate": active_reversal if active_reversal is not None else 0.0,
        "mean_ordinal_delta_distance": overall["mean_ordinal_delta_distance"],
        "legacy_state_direction_agreement": state["exact_direction_agreement"],
        "state_metrics": state,
        "dynamics_metrics": dynamics,
        "left_numeric_delta": state["left_numeric_delta"],
        "right_numeric_delta": state["right_numeric_delta"],
        "left_numeric_dynamics_delta": dynamics["left_numeric_delta"],
        "right_numeric_dynamics_delta": dynamics["right_numeric_delta"],
    }


def failed_comparison():
    """Record an unusable replay without pretending it was model disagreement."""
    return {
        "variable_count": 0,
        "direction_agreement": None,
        "active_union_direction_agreement": None,
        "active_union_change_no_change_agreement": None,
        "active_union_true_sign_reversal_rate": None,
        "active_union_count": 0,
        "both_changed_count": 0,
        "both_changed_direction_agreement": None,
        "zero_zero_count": 0,
        "zero_zero_fraction": None,
        "all_dimension_direction_agreement": None,
        "all_dimension_change_no_change_agreement": None,
        "all_dimension_true_sign_reversal_rate": None,
        "exact_direction_agreement": None,
        "change_no_change_agreement": None,
        "severe_reversal_fraction": None,
        "true_sign_reversal_rate": None,
        "mean_ordinal_delta_distance": None,
        "left_numeric_delta": {},
        "right_numeric_delta": {},
        "left_numeric_dynamics_delta": {},
        "right_numeric_dynamics_delta": {},
        "replay_failed": True,
    }


def _activity_summary(records, side):
    changed_dimensions = 0
    dimension_count = 0
    active_records = 0
    for record in records:
        comparison = record["comparison"]
        values = list(comparison.get(f"{side}_numeric_delta", {}).values())
        values += list(
            comparison.get(f"{side}_numeric_dynamics_delta", {}).values()
        )
        changed = sum(value != 0 for value in values)
        changed_dimensions += changed
        dimension_count += len(values)
        active_records += changed > 0
    record_count = len(records)
    return {
        "active_record_count": active_records,
        "active_record_fraction": round(
            active_records / record_count, 4
        ) if record_count else 0.0,
        "changed_dimension_count": changed_dimensions,
        "dimension_count": dimension_count,
        "changed_dimension_fraction": round(
            changed_dimensions / dimension_count, 4
        ) if dimension_count else 0.0,
    }


def summarize_backbone_sensitivity(
    records,
    minimum_direction_agreement=0.70,
    maximum_reversal_fraction=0.20,
    minimum_backbone_active_record_fraction=0.25,
):
    if not records:
        return {
            "passed": False,
            "reason": "no matched backbone records",
            "matched_checkpoint_count": 0,
        }
    successful = [
        item for item in records
        if not item["comparison"].get("replay_failed")
    ]
    active_dimension_count = sum(
        item["comparison"].get("active_union_count", 0) for item in successful
    )
    direction = (
        sum(
            (item["comparison"].get("active_union_direction_agreement") or 0.0)
            * item["comparison"].get("active_union_count", 0)
            for item in successful
        ) / active_dimension_count
        if active_dimension_count else 0.0
    )
    change_agreement = (
        sum(
            (item["comparison"].get("active_union_change_no_change_agreement") or 0.0)
            * item["comparison"].get("active_union_count", 0)
            for item in successful
        ) / active_dimension_count
        if active_dimension_count else 0.0
    )
    reversals = (
        sum(
            (item["comparison"].get("active_union_true_sign_reversal_rate") or 0.0)
            * item["comparison"].get("active_union_count", 0)
            for item in successful
        ) / active_dimension_count
        if active_dimension_count else 0.0
    )
    variable_count = sum(
        item["comparison"].get("variable_count", 0) for item in successful
    )
    ordinal_distance = (
        sum(
            item["comparison"]["mean_ordinal_delta_distance"]
            * item["comparison"].get("variable_count", 0)
            for item in successful
        ) / variable_count
        if variable_count else 0.0
    )
    all_dimension_direction = (
        sum(
            item["comparison"]["all_dimension_direction_agreement"]
            * item["comparison"].get("variable_count", 0)
            for item in successful
        ) / variable_count
        if variable_count else 0.0
    )
    zero_zero_count = sum(
        item["comparison"].get("zero_zero_count", 0) for item in successful
    )
    scenarios = {item["scenario_id"] for item in records}
    record_pass_count = sum(
        (item["comparison"].get("active_union_direction_agreement") or 0.0) >= 0.50
        and (item["comparison"].get("active_union_true_sign_reversal_rate") or 0.0) <= 0.40
        and item["comparison"].get("active_union_count", 0) > 0
        for item in successful
    )
    record_pass_fraction = (
        record_pass_count / len(successful) if successful else 0.0
    )
    replay_failure_count = sum(
        bool(item["comparison"].get("replay_failed")) for item in records
    )
    activity = {
        "left": _activity_summary(successful, "left"),
        "right": _activity_summary(successful, "right"),
    }
    activity_passed = all(
        item["active_record_fraction"] >= minimum_backbone_active_record_fraction
        for item in activity.values()
    )
    passed = (
        direction >= minimum_direction_agreement
        and reversals <= maximum_reversal_fraction
        and record_pass_fraction >= 0.80
        and replay_failure_count == 0
        and len(successful) >= 10
        and activity_passed
    )
    return {
        "passed": passed,
        "matched_checkpoint_count": len(records),
        "successful_matched_checkpoint_count": len(successful),
        "scenario_count": len(scenarios),
        "mean_direction_agreement": round(direction, 4),
        "mean_active_union_direction_agreement": round(direction, 4),
        "mean_all_dimension_direction_agreement": round(
            all_dimension_direction, 4
        ),
        "zero_zero_dimension_fraction": round(
            zero_zero_count / variable_count, 4
        ) if variable_count else None,
        "active_union_dimension_count": active_dimension_count,
        "mean_exact_direction_agreement": round(direction, 4),
        "mean_change_no_change_agreement": round(change_agreement, 4),
        "mean_severe_reversal_fraction": round(reversals, 4),
        "mean_true_sign_reversal_rate": round(reversals, 4),
        "mean_ordinal_delta_distance": round(ordinal_distance, 4),
        "record_pass_fraction": round(record_pass_fraction, 4),
        "replay_failure_count": replay_failure_count,
        "backbone_activity": activity,
        "backbone_activity_passed": activity_passed,
        "metric_scope": "state_and_dynamics_active_union_dimension_weighted",
        "service_failure_policy": (
            "exclude failed replays from agreement denominators; retain them "
            "as a zero-tolerance hard blocker"
        ),
        "thresholds": {
            "minimum_direction_agreement": minimum_direction_agreement,
            "maximum_reversal_fraction": maximum_reversal_fraction,
            "minimum_record_pass_fraction": 0.80,
            "per_record_minimum_direction_agreement": 0.50,
            "per_record_maximum_reversal_fraction": 0.40,
            "minimum_backbone_active_record_fraction": (
                minimum_backbone_active_record_fraction
            ),
        },
    }
