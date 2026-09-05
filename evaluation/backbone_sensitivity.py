"""Metrics for simulator-backbone sensitivity at matched checkpoints."""

from __future__ import annotations

from environment.delta_mapper import flatten_state


def _sign(value):
    return 0 if value == 0 else (1 if value > 0 else -1)


def compare_transitions(left, right):
    left_delta = flatten_state(left["numeric_state_delta"])
    right_delta = flatten_state(right["numeric_state_delta"])
    keys = sorted(set(left_delta) & set(right_delta))
    if not keys:
        raise ValueError("matched backbone transitions share no state variables")
    agreements = sum(_sign(left_delta[key]) == _sign(right_delta[key]) for key in keys)
    reversals = sum(
        _sign(left_delta[key]) * _sign(right_delta[key]) == -1 for key in keys
    )
    return {
        "variable_count": len(keys),
        "direction_agreement": round(agreements / len(keys), 4),
        "severe_reversal_fraction": round(reversals / len(keys), 4),
        "left_numeric_delta": left_delta,
        "right_numeric_delta": right_delta,
    }


def summarize_backbone_sensitivity(records, minimum_direction_agreement=0.70, maximum_reversal_fraction=0.20):
    if not records:
        return {
            "passed": False,
            "reason": "no matched backbone records",
            "matched_checkpoint_count": 0,
        }
    direction = sum(item["comparison"]["direction_agreement"] for item in records) / len(records)
    reversals = sum(item["comparison"]["severe_reversal_fraction"] for item in records) / len(records)
    scenarios = {item["scenario_id"] for item in records}
    record_pass_count = sum(
        item["comparison"]["direction_agreement"] >= 0.50
        and item["comparison"]["severe_reversal_fraction"] <= 0.40
        for item in records
    )
    record_pass_fraction = record_pass_count / len(records)
    passed = (
        direction >= minimum_direction_agreement
        and reversals <= maximum_reversal_fraction
        and record_pass_fraction >= 0.80
    )
    return {
        "passed": passed,
        "matched_checkpoint_count": len(records),
        "scenario_count": len(scenarios),
        "mean_direction_agreement": round(direction, 4),
        "mean_severe_reversal_fraction": round(reversals, 4),
        "record_pass_fraction": round(record_pass_fraction, 4),
        "thresholds": {
            "minimum_direction_agreement": minimum_direction_agreement,
            "maximum_reversal_fraction": maximum_reversal_fraction,
            "minimum_record_pass_fraction": 0.80,
            "per_record_minimum_direction_agreement": 0.50,
            "per_record_maximum_reversal_fraction": 0.40,
        },
    }
