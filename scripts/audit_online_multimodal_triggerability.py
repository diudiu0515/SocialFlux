#!/usr/bin/env python3
"""Explain online multimodal triggerability on saved state trajectories.

This is a diagnostic counterfactual replay.  It reuses recorded state
snapshots, makes no model calls, and does not alter rollout artifacts.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import median
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from environment.multimodal import (
    ObservableExpressionLayer,
    _condition_matches,
    _flat,
    _relaxed_conditions,
)
from environment.online_multimodal import ONLINE_MULTIMODAL_PROFILE
from pipeline.scenarios import load_scenarios


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIOS = ROOT / "data/gpt50/experiment/scenario/scenarios"
DEFAULT_TRAJECTORIES = ROOT / "data/gpt50/experiment/gate2/all50_rollout_inputs"

POLICY = {
    "profile": ONLINE_MULTIMODAL_PROFILE,
    "threshold_margin": 0,
    "change_threshold_margin": 0,
    "cooldown_turns": 2,
    "crossing_as_threshold": True,
    "max_events_per_turn": 1,
    "max_events_per_episode": 5,
    "max_fires_per_trigger": 1,
    "global_cooldown_turns": 2,
    "event_family_cooldown_turns": 3,
}

TIER_DEFINITION = {
    "easy": "observed at least two fires and the first fire was by turn 3",
    "moderate": "observed at least one fire but did not satisfy easy",
    "near_miss": "observed no fire but reached within one state point of a condition",
    "not_observed": "observed no fire and never came within one state point",
    "warning": (
        "Diagnostic bands only: they are not a Gate threshold and do not prove "
        "causal controllability by the tested model."
    ),
}


def _load_trajectories(root):
    by_id = {}
    for path in sorted(Path(root).rglob("trajectory.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        scenario_id = value.get("scenario_id")
        if not isinstance(scenario_id, str) or not scenario_id:
            raise ValueError(f"trajectory lacks scenario_id: {path}")
        if scenario_id in by_id:
            raise ValueError(
                f"duplicate trajectory for {scenario_id}: "
                f"{by_id[scenario_id][0]} and {path}"
            )
        by_id[scenario_id] = (path, value)
    if not by_id:
        raise ValueError(f"no trajectory.json files under {root}")
    return by_id


def _condition_gap(value, operator, threshold):
    if operator == ">=":
        return max(0, threshold - value)
    if operator == ">":
        return max(0, threshold + 1 - value)
    if operator == "<=":
        return max(0, value - threshold)
    if operator == "<":
        return max(0, value - threshold + 1)
    if operator == "==":
        return abs(value - threshold)
    raise ValueError(f"unsupported multimodal operator: {operator}")


def _trigger_detail(trigger, previous_values, current_values, policy):
    conditions = _relaxed_conditions(
        trigger.get("conditions", {}), policy["threshold_margin"]
    )
    details = []
    for variable, condition in conditions.items():
        current = current_values[variable]
        previous = previous_values.get(variable, current)
        operator = condition["operator"]
        threshold = condition["threshold"]
        details.append({
            "variable": variable,
            "operator": operator,
            "threshold": threshold,
            "previous": previous,
            "current": current,
            "delta": current - previous,
            "matched": _condition_matches(
                {variable: current}, {variable: condition}
            ),
            "distance_to_threshold": _condition_gap(
                current, operator, threshold
            ),
        })
    currently_active = all(item["matched"] for item in details)
    mode = trigger.get("trigger_mode", "crossing")
    if mode == "crossing":
        previously_active = _condition_matches(previous_values, conditions)
        raw_eligible = currently_active and (
            policy["crossing_as_threshold"] or not previously_active
        )
    elif mode == "threshold":
        previously_active = None
        raw_eligible = currently_active
    elif mode == "state_change":
        changes = {
            key: current_values[key] - previous_values.get(key, current_values[key])
            for key in current_values
        }
        change_conditions = _relaxed_conditions(
            trigger.get("change_conditions", {}),
            policy["change_threshold_margin"],
        )
        previously_active = None
        raw_eligible = _condition_matches(changes, change_conditions)
    else:
        raise ValueError(f"unsupported trigger_mode: {mode}")
    return {
        "trigger_id": trigger["trigger_id"],
        "event_family": trigger.get("event_family"),
        "source_state_family": trigger.get("source_state_family"),
        "source_state_variable": trigger.get("source_state_variable"),
        "source_direction": trigger.get("source_direction"),
        "priority": trigger.get("priority"),
        "trigger_mode": mode,
        "conditions": details,
        "currently_active": currently_active,
        "previously_active": previously_active,
        "raw_eligible": raw_eligible,
        "minimum_distance": max(
            (item["distance_to_threshold"] for item in details), default=0
        ),
    }


def _policy_blockers(trigger, runtime, turn_id, policy):
    blockers = []
    episode_limit = policy["max_events_per_episode"]
    if (
        episode_limit is not None
        and runtime.get("__event_count__", 0) >= episode_limit
    ):
        blockers.append("episode_cap")
    last_global = runtime.get("__global__")
    if (
        last_global is not None
        and turn_id < last_global + policy["global_cooldown_turns"]
    ):
        blockers.append("global_cooldown")
    fire_limit = policy["max_fires_per_trigger"]
    if (
        fire_limit is not None
        and runtime.get(f"__fire_count__:{trigger['trigger_id']}", 0)
        >= fire_limit
    ):
        blockers.append("per_trigger_cap")
    family = trigger.get("event_family")
    family_last = runtime.get(f"__family__:{family}")
    if (
        family and family_last is not None
        and turn_id < family_last + policy["event_family_cooldown_turns"]
    ):
        blockers.append("event_family_cooldown")
    last_turn = runtime.get(trigger["trigger_id"])
    cooldown = policy["cooldown_turns"]
    if cooldown is None:
        cooldown = trigger.get("cooldown_turns", 0)
    if last_turn is not None and turn_id < last_turn + cooldown:
        blockers.append("trigger_cooldown")
    return blockers


def _tier(event_count, first_fire_turn, minimum_gap):
    if event_count >= 2 and first_fire_turn is not None and first_fire_turn <= 3:
        return "easy"
    if event_count:
        return "moderate"
    if minimum_gap is not None and minimum_gap <= 1:
        return "near_miss"
    return "not_observed"


def replay_scenario(scenario, trajectory, trajectory_path):
    layer = ObservableExpressionLayer(scenario, POLICY)
    runtime = {}
    events = []
    turn_records = []
    skipped_turns = []
    blocked_reasons = Counter()
    eligible_turns = 0
    near_miss_turns = 0
    minimum_gap = None

    for index, turn in enumerate(trajectory.get("turns", []), start=1):
        previous_state = turn.get("state_before")
        state = turn.get("state_after")
        previous_dynamics = turn.get("dynamics_before", {})
        dynamics = turn.get("dynamics_after", {})
        turn_label = turn.get("turn_id", f"t{index}")
        if not isinstance(previous_state, dict) or not isinstance(state, dict):
            skipped_turns.append(turn_label)
            continue

        previous_values = _flat(previous_state, previous_dynamics)
        current_values = _flat(state, dynamics)
        runtime_before = dict(runtime)
        ordered = sorted(
            layer.triggers,
            key=lambda item: (
                runtime_before.get(
                    "__state_family_fire_count__:"
                    f"{item.get('source_state_family')}",
                    0,
                ),
                item.get("priority", 999),
            ),
        )
        details = [
            _trigger_detail(trigger, previous_values, current_values, POLICY)
            for trigger in ordered
        ]
        detail_by_id = {item["trigger_id"]: item for item in details}
        for trigger, detail in zip(ordered, details):
            if detail["raw_eligible"]:
                detail["blocked_reasons"] = _policy_blockers(
                    trigger, runtime_before, index, POLICY
                )
            else:
                detail["blocked_reasons"] = ["condition_not_met"]

        result = layer.evaluate(
            turn_id=index,
            previous_state=previous_state,
            previous_dynamics=previous_dynamics,
            state=state,
            dynamics=dynamics,
            last_trigger_turns=runtime,
        )
        fired = result["private_events"][0] if result["private_events"] else None
        fired_id = fired.get("trigger_id") if fired else None
        if fired_id:
            detail_by_id[fired_id]["blocked_reasons"] = []
            detail_by_id[fired_id]["fired"] = True
        for detail in details:
            detail.setdefault("fired", False)
            if (
                detail["raw_eligible"]
                and not detail["blocked_reasons"]
                and not detail["fired"]
            ):
                detail["blocked_reasons"] = ["per_turn_priority_budget"]

        hits = [item for item in details if item["raw_eligible"]]
        if hits:
            eligible_turns += 1
        else:
            turn_gap = min(
                (item["minimum_distance"] for item in details), default=None
            )
            if turn_gap is not None:
                minimum_gap = turn_gap if minimum_gap is None else min(
                    minimum_gap, turn_gap
                )
                if turn_gap <= 1:
                    near_miss_turns += 1
        for item in hits:
            blocked_reasons.update(item["blocked_reasons"])

        fired_record = None
        if fired:
            fired_detail = detail_by_id[fired_id]
            fired_record = {
                "turn_id": turn_label,
                "turn_number": index,
                "trigger_id": fired_id,
                "event_family": fired.get("event_family"),
                "source_state_family": fired.get("source_state_family"),
                "source_state_variable": fired.get("source_state_variable"),
                "source_direction": fired.get("source_direction"),
                "conditions": fired_detail["conditions"],
            }
            events.append(fired_record)

        nearest = sorted(
            (item for item in details if not item["raw_eligible"]),
            key=lambda item: (item["minimum_distance"], item["priority"]),
        )[:1]
        turn_records.append({
            "turn_id": turn_label,
            "turn_number": index,
            "condition_hit_count": len(hits),
            "condition_hits": hits,
            "nearest_miss": nearest[0] if nearest else None,
            "fired": fired_record,
        })

    first_fire_turn = events[0]["turn_number"] if events else None
    event_count = len(events)
    return {
        "scenario_id": scenario["scenario_id"],
        "trajectory_path": str(trajectory_path),
        "trajectory_turns": len(trajectory.get("turns", [])),
        "evaluable_turns": len(turn_records),
        "profile_trigger_count": layer.online_profile["trigger_count"],
        "event_count": event_count,
        "distinct_event_family_count": len({
            item["event_family"] for item in events
        }),
        "distinct_state_family_count": len({
            item["source_state_family"] for item in events
        }),
        "at_least_two_events": event_count >= 2,
        "at_least_three_events": event_count >= 3,
        "eligible_turn_count": eligible_turns,
        "eligible_turn_fraction": round(
            eligible_turns / len(turn_records), 4
        ) if turn_records else 0.0,
        "fire_given_eligible_turn_fraction": round(
            event_count / eligible_turns, 4
        ) if eligible_turns else 0.0,
        "first_fire_turn": first_fire_turn,
        "near_miss_turn_count": near_miss_turns,
        "minimum_unmet_distance": minimum_gap,
        "triggerability_tier": _tier(
            event_count, first_fire_turn, minimum_gap
        ),
        "blocked_reason_counts": dict(sorted(blocked_reasons.items())),
        "events": events,
        "turns": turn_records,
        "skipped_turns": skipped_turns,
    }


def build_report(scenarios, trajectories):
    records = []
    missing = []
    for scenario in scenarios:
        scenario_id = scenario["scenario_id"]
        source = trajectories.get(scenario_id)
        if source is None:
            missing.append(scenario_id)
            continue
        path, trajectory = source
        records.append(replay_scenario(scenario, trajectory, path))

    event_counts = [record["event_count"] for record in records]
    first_turns = [
        record["first_fire_turn"]
        for record in records
        if record["first_fire_turn"] is not None
    ]
    tiers = Counter(record["triggerability_tier"] for record in records)
    blocked = Counter()
    event_families = Counter()
    state_families = Counter()
    for record in records:
        blocked.update(record["blocked_reason_counts"])
        event_families.update(item["event_family"] for item in record["events"])
        state_families.update(
            item["source_state_family"] for item in record["events"]
        )
    evaluated = len(records)
    at_least_two = sum(item["at_least_two_events"] for item in records)
    at_least_three = sum(item["at_least_three_events"] for item in records)
    median_events = float(median(event_counts)) if event_counts else 0.0
    target_pass = (
        at_least_two / evaluated >= 0.9 and median_events >= 3
    ) if evaluated else False
    return {
        "format": "socialflux_online_multimodal_triggerability_audit_v1",
        "profile": ONLINE_MULTIMODAL_PROFILE,
        "audit_scope": "counterfactual_trigger_replay_with_diagnostics",
        "model_calls": 0,
        "source_trajectories_rewritten": False,
        "response_text_regenerated": False,
        "state_snapshots_reused": True,
        "policy": POLICY,
        "tier_definition": TIER_DEFINITION,
        "scenario_count": len(scenarios),
        "evaluated_scenario_count": evaluated,
        "missing_trajectory_scenario_ids": missing,
        "summary": {
            "at_least_two_event_count": at_least_two,
            "at_least_two_event_fraction": round(
                at_least_two / evaluated, 4
            ) if evaluated else 0.0,
            "at_least_three_event_count": at_least_three,
            "at_least_three_event_fraction": round(
                at_least_three / evaluated, 4
            ) if evaluated else 0.0,
            "median_event_count": median_events,
            "minimum_event_count": min(event_counts) if event_counts else 0,
            "maximum_event_count": max(event_counts) if event_counts else 0,
            "median_first_fire_turn": (
                float(median(first_turns)) if first_turns else None
            ),
            "triggerability_tier_counts": dict(sorted(tiers.items())),
            "blocked_reason_counts": dict(sorted(blocked.items())),
            "event_family_counts": dict(sorted(event_families.items())),
            "source_state_family_counts": dict(sorted(state_families.items())),
            "target": {
                "at_least_two_event_fraction": 0.9,
                "median_event_count": 3,
            },
            "target_pass": target_pass,
            "scale_recommendation": (
                "bounded_scale_ready" if target_pass else "hold_full_scale"
            ),
        },
        "records": records,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument(
        "--trajectories", type=Path, default=DEFAULT_TRAJECTORIES
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-target", action="store_true")
    args = parser.parse_args(argv)
    report = build_report(
        load_scenarios(args.scenarios), _load_trajectories(args.trajectories)
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    if args.require_target and not report["summary"]["target_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
