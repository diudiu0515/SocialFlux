#!/usr/bin/env python3
"""Replay online multimodal triggers over saved state trajectories.

This is a counterfactual trigger-only audit.  It reuses recorded state_before /
state_after snapshots, makes no model calls, does not regenerate environment
responses, and never rewrites source trajectories.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from environment.multimodal import ObservableExpressionLayer
from environment.online_multimodal import ONLINE_MULTIMODAL_PROFILE
from pipeline.scenarios import load_scenarios


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIOS = ROOT / "data/gpt50/experiment/scenario/scenarios"
DEFAULT_TRAJECTORIES = (
    ROOT / "data/gpt50/experiment/gate2/all50_rollout_inputs"
)


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


def replay_scenario(scenario, trajectory, trajectory_path):
    layer = ObservableExpressionLayer(
        scenario,
        {
            "profile": ONLINE_MULTIMODAL_PROFILE,
            "max_events_per_episode": 5,
            "max_fires_per_trigger": 1,
            "global_cooldown_turns": 2,
            "event_family_cooldown_turns": 3,
        },
    )
    runtime = {}
    events = []
    skipped_turns = []
    for index, turn in enumerate(trajectory.get("turns", []), start=1):
        previous_state = turn.get("state_before")
        state = turn.get("state_after")
        previous_dynamics = turn.get("dynamics_before", {})
        dynamics = turn.get("dynamics_after", {})
        if not isinstance(previous_state, dict) or not isinstance(state, dict):
            skipped_turns.append(turn.get("turn_id", f"t{index}"))
            continue
        result = layer.evaluate(
            turn_id=index,
            previous_state=previous_state,
            previous_dynamics=previous_dynamics,
            state=state,
            dynamics=dynamics,
            last_trigger_turns=runtime,
        )
        for event in result["private_events"]:
            events.append({
                "turn_id": turn.get("turn_id", f"t{index}"),
                "trigger_id": event["trigger_id"],
                "event_family": event.get("event_family"),
                "trigger_variables": event["trigger_variables"],
            })
    return {
        "scenario_id": scenario["scenario_id"],
        "trajectory_path": str(trajectory_path),
        "trajectory_turns": len(trajectory.get("turns", [])),
        "profile_trigger_count": layer.online_profile["trigger_count"],
        "replayed_event_count": len(events),
        "at_least_two_events": len(events) >= 2,
        "at_least_three_events": len(events) >= 3,
        "events": events,
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
    counts = [record["replayed_event_count"] for record in records]
    at_least_two = sum(record["at_least_two_events"] for record in records)
    at_least_three = sum(record["at_least_three_events"] for record in records)
    evaluated = len(records)
    fraction_two = at_least_two / evaluated if evaluated else 0.0
    fraction_three = at_least_three / evaluated if evaluated else 0.0
    median_events = float(median(counts)) if counts else 0.0
    return {
        "format": "socialflux_online_multimodal_reachability_audit_v2",
        "profile": ONLINE_MULTIMODAL_PROFILE,
        "audit_scope": "counterfactual_trigger_replay_only",
        "model_calls": 0,
        "source_trajectories_rewritten": False,
        "response_text_regenerated": False,
        "state_snapshots_reused": True,
        "scenario_count": len(scenarios),
        "evaluated_scenario_count": evaluated,
        "missing_trajectory_scenario_ids": missing,
        "summary": {
            "at_least_two_event_count": at_least_two,
            "at_least_two_event_fraction": round(fraction_two, 4),
            "at_least_three_event_count": at_least_three,
            "at_least_three_event_fraction": round(fraction_three, 4),
            "median_event_count": median_events,
            "minimum_event_count": min(counts) if counts else 0,
            "maximum_event_count": max(counts) if counts else 0,
            "target": {
                "at_least_two_event_fraction": 0.9,
                "median_event_count": 3,
            },
            "target_pass": fraction_two >= 0.9 and median_events >= 3,
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

    scenarios = load_scenarios(args.scenarios)
    trajectories = _load_trajectories(args.trajectories)
    report = build_report(scenarios, trajectories)
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
