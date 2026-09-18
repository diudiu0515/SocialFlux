"""Metrics for simulator-backbone sensitivity at matched checkpoints."""

from __future__ import annotations

from .transition_metrics import compare_transition_outputs


def compare_transitions(left, right):
    groups = compare_transition_outputs(left, right)
    state = groups["state"]
    dynamics = groups["dynamics"]
    overall = groups["overall"]
    return {
        "variable_count": overall["variable_count"],
        "direction_agreement": overall["exact_direction_agreement"],
        "exact_direction_agreement": overall["exact_direction_agreement"],
        "change_no_change_agreement": overall["change_no_change_agreement"],
        "severe_reversal_fraction": overall["true_sign_reversal_rate"],
        "true_sign_reversal_rate": overall["true_sign_reversal_rate"],
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
    """Conservatively score an unusable matched replay without hiding it."""
    return {
        "variable_count": 0,
        "direction_agreement": 0.0,
        "exact_direction_agreement": 0.0,
        "change_no_change_agreement": 0.0,
        "severe_reversal_fraction": 1.0,
        "true_sign_reversal_rate": 1.0,
        "mean_ordinal_delta_distance": 6.0,
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
        "active_record_fraction": round(active_records / record_count, 4),
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
    direction = sum(
        item["comparison"]["exact_direction_agreement"] for item in records
    ) / len(records)
    change_agreement = sum(
        item["comparison"]["change_no_change_agreement"] for item in records
    ) / len(records)
    reversals = sum(
        item["comparison"]["true_sign_reversal_rate"] for item in records
    ) / len(records)
    ordinal_distance = sum(
        item["comparison"]["mean_ordinal_delta_distance"] for item in records
    ) / len(records)
    scenarios = {item["scenario_id"] for item in records}
    record_pass_count = sum(
        item["comparison"]["exact_direction_agreement"] >= 0.50
        and item["comparison"]["true_sign_reversal_rate"] <= 0.40
        for item in records
    )
    record_pass_fraction = record_pass_count / len(records)
    replay_failure_count = sum(
        bool(item["comparison"].get("replay_failed")) for item in records
    )
    activity = {
        "left": _activity_summary(records, "left"),
        "right": _activity_summary(records, "right"),
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
        and activity_passed
    )
    return {
        "passed": passed,
        "matched_checkpoint_count": len(records),
        "scenario_count": len(scenarios),
        "mean_direction_agreement": round(direction, 4),
        "mean_exact_direction_agreement": round(direction, 4),
        "mean_change_no_change_agreement": round(change_agreement, 4),
        "mean_severe_reversal_fraction": round(reversals, 4),
        "mean_true_sign_reversal_rate": round(reversals, 4),
        "mean_ordinal_delta_distance": round(ordinal_distance, 4),
        "record_pass_fraction": round(record_pass_fraction, 4),
        "replay_failure_count": replay_failure_count,
        "backbone_activity": activity,
        "backbone_activity_passed": activity_passed,
        "metric_scope": "state_and_dynamics_dimension_weighted",
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
