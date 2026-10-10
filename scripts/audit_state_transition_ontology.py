#!/usr/bin/env python3
"""Audit saved trajectories from state ontology through applied transitions.

The audit is intentionally offline: it performs no provider calls and never
rewrites trajectories or scenarios. It reports the accepted cohort separately
from any other Gate 2 population and traces each state candidate through
appraisal, deterministic calibration, selection, and numeric application.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUTS = ROOT / "data/gpt50/experiment/gate2/accepted_rollout_inputs"
DEFAULT_SCENARIOS = ROOT / "data/gpt50/experiment/scenario/scenarios"
DEFAULT_OUTPUT = (
    ROOT / "reports/experiments/2026-09-26_gpt50_state_transition_audit.json"
)


def _flatten(values, prefix=""):
    result = {}
    for key, value in (values or {}).items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(_flatten(value, path))
        else:
            result[path] = value
    return result


def _ratio(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else 0.0


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _scenario_map(root):
    result = {}
    for path in sorted(Path(root).glob("scenario_*/scenario_*.json")):
        value = _load_json(path)
        scenario_id = value.get("scenario_id")
        if not isinstance(scenario_id, str) or not scenario_id:
            raise ValueError(f"scenario lacks scenario_id: {path}")
        if scenario_id in result:
            raise ValueError(f"duplicate scenario_id {scenario_id}")
        result[scenario_id] = (path, value)
    if not result:
        raise ValueError(f"no scenarios found under {root}")
    return result


def _trajectory_map(root):
    result = {}
    for path in sorted(Path(root).glob("scenario_*/trajectory.json")):
        value = _load_json(path)
        scenario_id = value.get("scenario_id")
        if not isinstance(scenario_id, str) or not scenario_id:
            raise ValueError(f"trajectory lacks scenario_id: {path}")
        if scenario_id in result:
            raise ValueError(f"duplicate trajectory for {scenario_id}")
        result[scenario_id] = (path, value)
    if not result:
        raise ValueError(f"no trajectory.json files under {root}")
    return result


def _time_bin(index, turn_count):
    # Relative thirds avoid treating a 10-turn and a 20-turn run as though
    # their eighth turns occupied the same longitudinal position.
    fraction = index / max(turn_count, 1)
    if fraction <= 1 / 3:
        return "early"
    if fraction <= 2 / 3:
        return "middle"
    return "late"


def _nested_rationale_paths(scenario):
    rationale = (
        (scenario.get("initialization_notes") or {}).get("rationale") or {}
    )
    return set(
        _flatten(
            {
                family: values
                for family, values in rationale.items()
                if isinstance(values, dict)
            }
        )
    )


def _selected_state_paths(scenario):
    selected = scenario.get("selected_state_variables") or {}
    return [
        f"{family}.{variable}"
        for family, variables in selected.items()
        for variable in variables
    ]


def _rationale_granularity(scenario, path):
    family, variable = path.split(".", 1)
    rationale = (
        (scenario.get("initialization_notes") or {}).get("rationale") or {}
    )
    family_value = rationale.get(family)
    if isinstance(family_value, dict) and isinstance(
        family_value.get(variable), str
    ):
        return "variable"
    if isinstance(family_value, str) and family_value.strip():
        return "family"
    return "missing"


def _suppression_reason(item, turn, before):
    supplied = item.get("suppressed_by")
    if supplied:
        return supplied
    if item.get("selected"):
        return "selected"
    if item.get("calibrated_level", 0) <= 0:
        return "no_calibrated_change"
    if (turn.get("calibration") or {}).get("semantic_no_change_enforced"):
        return "semantic_no_change"
    current = before.get(item.get("variable"))
    if (
        isinstance(current, (int, float))
        and not isinstance(current, bool)
        and (
            (item.get("direction") == "increase" and current >= 10)
            or (item.get("direction") == "decrease" and current <= 0)
        )
    ):
        return "state_boundary_noop"
    # Legacy sparse_v1 evidence did not record a more specific reason.
    return "legacy_budget_or_rank"


def build_report(input_root, scenario_root):
    input_root = Path(input_root)
    manifest_path = input_root / "gate2_input_manifest.json"
    manifest = _load_json(manifest_path)
    scenarios = _scenario_map(scenario_root)
    trajectories = _trajectory_map(input_root)

    expected_ids = [
        record["scenario_id"] for record in manifest.get("records", [])
    ]
    if set(expected_ids) != set(trajectories):
        raise ValueError(
            "input manifest scenario IDs do not match trajectory files"
        )

    stage_totals = Counter()
    family_totals = defaultdict(Counter)
    variable_totals = defaultdict(Counter)
    time_totals = defaultdict(Counter)
    initial_values = defaultdict(list)
    selected_counts = Counter()
    variable_frequency = Counter()
    suppression_reasons = Counter()
    candidate_directions = Counter()
    applied_directions = Counter()
    calibrated_levels = Counter()
    inferred_features = Counter()
    scenario_records = []
    changed_scenario_variables = set()
    all_scenario_variables = set()
    inferred_tie_turns = 0
    lexical_tie_winner_turns = 0

    schema_totals = Counter()
    missing_scenarios = []
    for scenario_id in expected_ids:
        if scenario_id not in scenarios:
            missing_scenarios.append(scenario_id)
            continue
        scenario_path, scenario = scenarios[scenario_id]
        trajectory_path, trajectory = trajectories[scenario_id]
        selected_paths = _selected_state_paths(scenario)
        selected_counts[len(selected_paths)] += 1
        rationale_paths = _nested_rationale_paths(scenario)
        transition_specs = scenario.get("state_transition_specs") or {}
        transition_spec_paths = set(_flatten(transition_specs))
        initial = _flatten(scenario.get("initial_state", {}))
        schema_totals["scenario_count"] += 1
        schema_totals["selected_variable_count"] += len(selected_paths)
        schema_totals["variable_rationale_count"] += sum(
            path in rationale_paths for path in selected_paths
        )
        schema_totals["family_rationale_fallback_count"] += sum(
            _rationale_granularity(scenario, path) == "family"
            for path in selected_paths
        )
        schema_totals["transition_spec_count"] += sum(
            path in transition_specs or path in transition_spec_paths
            for path in selected_paths
        )
        reachability = (
            (scenario.get("initialization_notes") or {}).get(
                "trigger_reachability"
            )
            or []
        )
        schema_totals["generic_reachability_statement_count"] += len(
            reachability
        )

        scenario_changed = set()
        scenario_stage = Counter()
        for path in selected_paths:
            family = path.split(".", 1)[0]
            variable_frequency[path] += 1
            all_scenario_variables.add((scenario_id, path))
            if path in initial:
                initial_values[path].append(initial[path])
                stage_totals["initial_value_count"] += 1
                if initial[path] in {0, 1, 9, 10}:
                    stage_totals["initial_near_boundary_count"] += 1
                family_totals[family]["initial_value_count"] += 1
                if initial[path] in {0, 1, 9, 10}:
                    family_totals[family][
                        "initial_near_boundary_count"
                    ] += 1

        turns = trajectory.get("turns") or []
        for index, turn in enumerate(turns, start=1):
            time_bin = _time_bin(index, len(turns))
            numeric = _flatten(turn.get("numeric_state_delta", {}))
            before = _flatten(turn.get("state_before", {}))
            diagnostics = (
                (turn.get("calibration") or {}).get("state_impacts") or []
            )

            for path in selected_paths:
                family = path.split(".", 1)[0]
                delta = numeric.get(path, 0)
                stage_totals["labels"] += 1
                family_totals[family]["labels"] += 1
                variable_totals[path]["labels"] += 1
                time_totals[time_bin]["labels"] += 1
                if not delta:
                    stage_totals["unchanged_labels"] += 1
                    family_totals[family]["unchanged_labels"] += 1
                    variable_totals[path]["unchanged_labels"] += 1
                    time_totals[time_bin]["unchanged_labels"] += 1
                else:
                    stage_totals["applied"] += 1
                    family_totals[family]["applied"] += 1
                    variable_totals[path]["applied"] += 1
                    time_totals[time_bin]["applied"] += 1
                    direction = "increase" if delta > 0 else "decrease"
                    applied_directions[direction] += 1
                    scenario_changed.add(path)
                    changed_scenario_variables.add((scenario_id, path))

            eligible_for_tie = [
                item
                for item in diagnostics
                if item.get("calibrated_level", 0) > 0
                and not (
                    isinstance(
                        before.get(item.get("variable")), (int, float)
                    )
                    and (
                        (
                            item.get("direction") == "increase"
                            and before.get(item.get("variable")) >= 10
                        )
                        or (
                            item.get("direction") == "decrease"
                            and before.get(item.get("variable")) <= 0
                        )
                    )
                )
            ]
            if eligible_for_tie:
                best_key = max(
                    (
                        item.get("calibrated_level", 0),
                        abs(item.get("feature_value", 0)),
                    )
                    for item in eligible_for_tie
                )
                tied = [
                    item
                    for item in eligible_for_tie
                    if (
                        item.get("calibrated_level", 0),
                        abs(item.get("feature_value", 0)),
                    )
                    == best_key
                ]
                selected_tied = [
                    item for item in tied if item.get("selected")
                ]
                if len(tied) > 1 and all(
                    item.get("feature_inferred") for item in tied
                ):
                    inferred_tie_turns += 1
                    if (
                        selected_tied
                        and selected_tied[0].get("variable")
                        == min(item.get("variable") for item in tied)
                    ):
                        lexical_tie_winner_turns += 1

            for item in diagnostics:
                path = item.get("variable", "unknown.unknown")
                family = path.split(".", 1)[0]
                stage_totals["appraised_candidates"] += 1
                family_totals[family]["appraised_candidates"] += 1
                variable_totals[path]["appraised_candidates"] += 1
                scenario_stage["appraised_candidates"] += 1
                candidate_directions[
                    item.get("direction", "unknown")
                ] += 1
                if item.get("feature_inferred"):
                    stage_totals["feature_inferred_candidates"] += 1
                    family_totals[family][
                        "feature_inferred_candidates"
                    ] += 1
                    variable_totals[path][
                        "feature_inferred_candidates"
                    ] += 1
                    inferred_features[
                        item.get("evidence_feature", "unknown")
                    ] += 1
                if item.get("explicit_evidence"):
                    stage_totals["explicit_evidence_candidates"] += 1
                calibrated_levels[str(item.get("calibrated_level", 0))] += 1
                if item.get("calibrated_level", 0) > 0:
                    stage_totals["calibrated_positive"] += 1
                    family_totals[family]["calibrated_positive"] += 1
                    variable_totals[path]["calibrated_positive"] += 1
                    scenario_stage["calibrated_positive"] += 1
                    time_totals[time_bin]["calibrated_positive"] += 1
                if item.get("selected"):
                    stage_totals["selected"] += 1
                    family_totals[family]["selected"] += 1
                    variable_totals[path]["selected"] += 1
                    scenario_stage["selected"] += 1
                    time_totals[time_bin]["selected"] += 1
                    if not numeric.get(path, 0):
                        stage_totals["selected_numeric_noop"] += 1
                        family_totals[family][
                            "selected_numeric_noop"
                        ] += 1
                        variable_totals[path][
                            "selected_numeric_noop"
                        ] += 1
                        current = before.get(path)
                        if (
                            item.get("direction") == "increase"
                            and current == 10
                        ) or (
                            item.get("direction") == "decrease"
                            and current == 0
                        ):
                            stage_totals[
                                "selected_boundary_noop"
                            ] += 1
                            family_totals[family][
                                "selected_boundary_noop"
                            ] += 1
                            variable_totals[path][
                                "selected_boundary_noop"
                            ] += 1
                time_totals[time_bin]["appraised_candidates"] += 1
                if item.get("feature_inferred"):
                    time_totals[time_bin]["feature_inferred_candidates"] += 1
                reason = _suppression_reason(item, turn, before)
                if reason != "selected":
                    suppression_reasons[reason] += 1

        scenario_records.append(
            {
                "scenario_id": scenario_id,
                "scenario_path": str(scenario_path),
                "trajectory_path": str(trajectory_path),
                "turn_count": len(turns),
                "selected_state_variable_count": len(selected_paths),
                "selected_state_paths": selected_paths,
                "initial_values": initial,
                "variable_rationale_coverage": {
                    "covered": sum(
                        path in rationale_paths for path in selected_paths
                    ),
                    "total": len(selected_paths),
                },
                "family_rationale_fallback_coverage": {
                    "covered": sum(
                        _rationale_granularity(scenario, path) == "family"
                        for path in selected_paths
                    ),
                    "total": len(selected_paths),
                },
                "missing_rationale_state_paths": sorted(
                    path
                    for path in selected_paths
                    if _rationale_granularity(scenario, path) == "missing"
                ),
                "per_variable_transition_spec_coverage": {
                    "covered": sum(
                        path in transition_specs
                        or path in transition_spec_paths
                        for path in selected_paths
                    ),
                    "total": len(selected_paths),
                },
                "generic_trigger_reachability_statements": len(
                    reachability
                ),
                "changed_state_paths": sorted(scenario_changed),
                "all_time_unchanged_state_paths": sorted(
                    set(selected_paths) - scenario_changed
                ),
                "stage_counts": dict(scenario_stage),
            }
        )

    all_time_unchanged = all_scenario_variables - changed_scenario_variables
    stage_summary = dict(stage_totals)
    stage_summary.update(
        {
            "unchanged_label_fraction": _ratio(
                stage_totals["unchanged_labels"], stage_totals["labels"]
            ),
            "candidate_to_positive_fraction": _ratio(
                stage_totals["calibrated_positive"],
                stage_totals["appraised_candidates"],
            ),
            "positive_to_selected_fraction": _ratio(
                stage_totals["selected"],
                stage_totals["calibrated_positive"],
            ),
            "selected_to_applied_fraction": _ratio(
                stage_totals["applied"], stage_totals["selected"]
            ),
            "feature_inferred_fraction": _ratio(
                stage_totals["feature_inferred_candidates"],
                stage_totals["appraised_candidates"],
            ),
            "all_time_unchanged_scenario_variable_count": len(
                all_time_unchanged
            ),
            "scenario_variable_count": len(all_scenario_variables),
            "all_time_unchanged_scenario_variable_fraction": _ratio(
                len(all_time_unchanged), len(all_scenario_variables)
            ),
        }
    )

    def summarized(counter):
        value = dict(counter)
        value["unchanged_label_fraction"] = _ratio(
            counter["unchanged_labels"], counter["labels"]
        )
        value["candidate_to_positive_fraction"] = _ratio(
            counter["calibrated_positive"],
            counter["appraised_candidates"],
        )
        value["positive_to_selected_fraction"] = _ratio(
            counter["selected"], counter["calibrated_positive"]
        )
        value["selected_to_applied_fraction"] = _ratio(
            counter["applied"], counter["selected"]
        )
        return value

    schema_summary = dict(schema_totals)
    schema_summary.update(
        {
            "variable_rationale_coverage": _ratio(
                schema_totals["variable_rationale_count"],
                schema_totals["selected_variable_count"],
            ),
            "family_rationale_fallback_coverage": _ratio(
                schema_totals["family_rationale_fallback_count"],
                schema_totals["selected_variable_count"],
            ),
            "any_scenario_rationale_coverage": _ratio(
                schema_totals["variable_rationale_count"]
                + schema_totals["family_rationale_fallback_count"],
                schema_totals["selected_variable_count"],
            ),
            "per_variable_transition_spec_coverage": _ratio(
                schema_totals["transition_spec_count"],
                schema_totals["selected_variable_count"],
            ),
            "selected_variable_count_distribution": {
                str(key): value
                for key, value in sorted(selected_counts.items())
            },
        }
    )

    return {
        "format": "socialflux_state_transition_ontology_audit_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "audit_scope": "offline accepted-cohort evidence only",
        "model_calls": 0,
        "source_artifacts_rewritten": False,
        "input_manifest": str(manifest_path),
        "source_status_filter": manifest.get("source_status_filter"),
        "population_source_status_counts": manifest.get(
            "population_source_status_counts", {}
        ),
        "cohort": {
            "manifest_scenario_count": manifest.get("scenario_count"),
            "evaluated_scenario_count": len(scenario_records),
            "trajectory_turn_count": sum(
                record["turn_count"] for record in scenario_records
            ),
            "turn_count_distribution": manifest.get(
                "turn_count_distribution", {}
            ),
            "exact_20_turn_count": manifest.get("exact_20_turn_count"),
            "missing_source_scenario_ids": missing_scenarios,
        },
        "ontology_schema": schema_summary,
        "transition_pipeline": stage_summary,
        "by_family": {
            family: summarized(counter)
            for family, counter in sorted(family_totals.items())
        },
        "by_relative_time": {
            time_bin: summarized(time_totals[time_bin])
            for time_bin in ("early", "middle", "late")
        },
        "by_variable": {
            path: {
                **summarized(variable_totals[path]),
                "scenario_frequency": variable_frequency[path],
                "initial_values": initial_values[path],
            }
            for path in sorted(variable_totals)
        },
        "directionality": {
            "appraised_candidates": dict(candidate_directions),
            "applied_changes": dict(applied_directions),
        },
        "suppression_reasons": dict(suppression_reasons),
        "legacy_ranking_risk": {
            "turns_with_inferred_top_rank_tie": inferred_tie_turns,
            "turns_where_lexicographically_first_tied_variable_won": (
                lexical_tie_winner_turns
            ),
            "winner_fraction": _ratio(
                lexical_tie_winner_turns, inferred_tie_turns
            ),
        },
        "calibration_diagnostics": {
            "calibrated_level_counts": dict(calibrated_levels),
            "level_3_candidate_count": calibrated_levels["3"],
            "inferred_feature_counts": dict(inferred_features),
            "strong_extra_budget_was_reachable": (
                calibrated_levels["3"] > 0
            ),
        },
        "records": scenario_records,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = build_report(args.inputs, args.scenarios)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
