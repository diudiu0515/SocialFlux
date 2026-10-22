"""Machine-auditable metrics for State Transition Standard v3."""

from __future__ import annotations

from collections import Counter


REQUIRED_FAMILIES = {
    "emotion",
    "behavioral_disposition",
    "relationship",
    "consequence_risk",
}
FAST_TIMESCALES = {"turn_local", "turn_to_episode"}
MIN_MAIN_TURNS = 10
MAX_MAIN_TURNS = 20


def _flatten(values, prefix=""):
    result = {}
    for key, value in values.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(_flatten(value, path))
        else:
            result[path] = value
    return result


def state_v3_trajectory_metrics(trajectory):
    turns = trajectory.get("turns") or []
    environment = (
        (trajectory.get("environment_provenance") or {}).get("environment")
        or {}
    )
    calibration_profile = environment.get("state_calibration_profile")
    if not calibration_profile and turns:
        calibration_profile = (
            (turns[0].get("calibration") or {}).get("calibration_profile")
        )
    shared_evidence_across_distinct_variables_allowed = calibration_profile in {
        "evidence_causal_hysteretic_v5",
        "evidence_causal_slow_priority_hysteretic_v6",
        "state_judgment_primary_hysteretic_v7",
    }
    feature_is_auxiliary = (
        calibration_profile == "state_judgment_primary_hysteretic_v7"
    )
    family_changes = Counter()
    variable_changes = Counter()
    direction_changes = Counter()
    total_labels = 0
    unchanged_labels = 0
    selected_impacts = 0
    fast_changes = 0
    slow_changes = 0
    compliant_slow_changes = 0
    false_changes = []
    feature_mismatches = []
    duplicate_selected_spans = []
    family_cap_violations = []

    selected_paths = set(_flatten(trajectory.get("initial_state") or {}))
    for turn in turns:
        delta = _flatten(turn.get("numeric_state_delta") or {})
        diagnostics = (
            (turn.get("calibration") or {}).get("state_impacts") or []
        )
        selected = {
            item.get("variable"): item
            for item in diagnostics
            if item.get("selected") is True
        }
        selected_impacts += len(selected)

        spans = [
            item.get("evidence_span")
            for item in selected.values()
            if item.get("evidence_span")
        ]
        if len(spans) != len(set(spans)):
            duplicate_selected_spans.append(turn.get("turn_id"))
        family_selected = Counter(
            variable.split(".", 1)[0] for variable in selected
        )
        bad_caps = {
            family: count
            for family, count in family_selected.items()
            if count > 1
        }
        if bad_caps:
            family_cap_violations.append({
                "turn_id": turn.get("turn_id"),
                "families": bad_caps,
            })

        for path in selected_paths:
            value = delta.get(path, 0)
            total_labels += 1
            if not value:
                unchanged_labels += 1
                continue
            family = path.split(".", 1)[0]
            family_changes[family] += 1
            variable_changes[path] += 1
            direction_changes[f"{path}:{'increase' if value > 0 else 'decrease'}"] += 1
            impact = selected.get(path)
            if impact is None:
                false_changes.append({
                    "turn_id": turn.get("turn_id"),
                    "variable": path,
                    "reason": "numeric_change_without_selected_impact",
                })
                continue
            if impact.get("feature_compatible") is False:
                feature_mismatches.append({
                    "turn_id": turn.get("turn_id"),
                    "variable": path,
                })
            timescale = impact.get("timescale")
            if timescale in FAST_TIMESCALES:
                fast_changes += 1
            if timescale == "cross_turn_slow":
                slow_changes += 1
                if (
                    impact.get("decisive_evidence") is True
                    or impact.get("prior_consistent_evidence", 0) >= 1
                ):
                    compliant_slow_changes += 1

    final_state = (
        turns[-1].get("state_after") if turns
        else trajectory.get("initial_state") or {}
    )
    final_values = list(_flatten(final_state).values())
    boundary_count = sum(value in (0, 10) for value in final_values)
    covered_families = {
        family for family, count in family_changes.items() if count > 0
    }
    all_time_static = sum(
        variable_changes[path] == 0 for path in selected_paths
    )
    correctness_requirements = {
        "no_numeric_change_without_selected_impact": not false_changes,
        "feature_interface_is_advisory_or_matches": (
            feature_is_auxiliary or not feature_mismatches
        ),
        "no_duplicate_selected_evidence_span": (
            shared_evidence_across_distinct_variables_allowed
            or not duplicate_selected_spans
        ),
        "family_caps_respected": not family_cap_violations,
        "all_slow_changes_are_compliant": (
            slow_changes == compliant_slow_changes
        ),
    }
    coverage_targets = {
        "turn_count_in_main_10_to_20_window": (
            MIN_MAIN_TURNS <= len(turns) <= MAX_MAIN_TURNS
        ),
        "all_four_families_changed": covered_families == REQUIRED_FAMILIES,
        "has_fast_change": fast_changes > 0,
        "has_compliant_slow_change": compliant_slow_changes > 0,
    }
    requirements = {**correctness_requirements, **coverage_targets}
    return {
        "format": "socialflux_state_v3_trajectory_metrics_v3",
        "trajectory_id": trajectory.get("trajectory_id"),
        "turn_count": len(turns),
        "selected_state_count": len(selected_paths),
        "total_state_labels": total_labels,
        "unchanged_state_labels": unchanged_labels,
        "unchanged_state_label_rate": (
            unchanged_labels / total_labels if total_labels else None
        ),
        "all_time_static_variables": all_time_static,
        "all_time_static_variable_rate": (
            all_time_static / len(selected_paths) if selected_paths else None
        ),
        "family_changes": dict(family_changes),
        "variable_changes": dict(variable_changes),
        "direction_changes": dict(direction_changes),
        "selected_impacts": selected_impacts,
        "fast_changes": fast_changes,
        "slow_changes": slow_changes,
        "compliant_slow_changes": compliant_slow_changes,
        "final_boundary_count": boundary_count,
        "final_boundary_rate": (
            boundary_count / len(final_values) if final_values else None
        ),
        "false_changes": false_changes,
        "feature_mismatches": feature_mismatches,
        "feature_is_auxiliary": feature_is_auxiliary,
        "duplicate_selected_spans": duplicate_selected_spans,
        "shared_evidence_across_distinct_variables_allowed": (
            shared_evidence_across_distinct_variables_allowed
        ),
        "calibration_profile": calibration_profile,
        "family_cap_violations": family_cap_violations,
        "requirements": requirements,
        "correctness_requirements": correctness_requirements,
        "coverage_targets": coverage_targets,
        "state_update_integrity_passed": all(
            correctness_requirements.values()
        ),
        "coverage_sufficient": all(coverage_targets.values()),
        # Backward-compatible field: admission now means state-update integrity,
        # not whether this one trajectory happened to exercise every family.
        "machine_passed": all(correctness_requirements.values()),
        "human_review": "pending",
    }
