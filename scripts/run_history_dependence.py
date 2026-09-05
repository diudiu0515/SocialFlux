#!/usr/bin/env python3
"""Probe full/recent/critical-event-removed history from identical checkpoints."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from environment.delta_mapper import flatten_state
from environment.factory import ModelEnvironmentFactory
from prompts.loader import render_prompt
from providers.factory import build_provider
from providers.text import complete_distinct_text, text_similarity
from scripts.audit_formal_rollout_pool import load_records
from scripts.run_pipeline import load_rollout_config, load_scenarios


def critical_turn(trajectory, checkpoint):
    candidates = trajectory.get("turns", [])[:checkpoint]
    if not candidates:
        return None
    def magnitude(turn):
        before = flatten_state(turn.get("state_before", {}))
        after = flatten_state(turn.get("state_after", {}))
        return sum(abs(after.get(key, value) - value) for key, value in before.items())
    return max(candidates, key=magnitude).get("turn_id")


def observation_variants(trajectory, recent_k):
    turns = trajectory["turns"]
    checkpoint = len(turns) - 1
    observation = dict(turns[checkpoint]["observation"])
    history = list(observation.get("history", []))
    critical = critical_turn(trajectory, checkpoint)
    recent = history[-2 * recent_k:]
    removed = [
        item for item in history
        if str(item.get("turn_id")) != str(critical).lstrip("t")
    ]
    full = dict(observation)
    recent_observation = dict(observation)
    removed_observation = dict(observation)
    recent_observation["history"] = recent
    removed_observation["history"] = removed
    return full, recent_observation, removed_observation, critical


def provider_specs(config):
    return {
        item["model_family"]: item
        for item in config["policies"]
    }


def generate(provider, observation, sampling):
    prompt = render_prompt("history_dependence_probe_v1", observation)
    return complete_distinct_text(
        provider,
        [{"role": "user", "content": prompt}],
        sampling,
        [],
        context="history dependence probe",
        max_attempts=6,
    )


def _direction_agreement(left, right):
    left = flatten_state(left)
    right = flatten_state(right)
    keys = set(left) & set(right)
    if not keys:
        return 1.0
    def sign(value):
        return 0 if value == 0 else (1 if value > 0 else -1)
    return sum(sign(left[key]) == sign(right[key]) for key in keys) / len(keys)


def _interpretation_comparison(full, variant):
    state_agreement = _direction_agreement(
        full["numeric_state_delta"], variant["numeric_state_delta"]
    )
    dynamics_agreement = _direction_agreement(
        full["numeric_dynamics_delta"], variant["numeric_dynamics_delta"]
    )
    appraisal_similarity = text_similarity(
        json.dumps(full.get("appraisal", {}), ensure_ascii=False, sort_keys=True),
        json.dumps(variant.get("appraisal", {}), ensure_ascii=False, sort_keys=True),
    )
    return {
        "state_direction_agreement": round(state_agreement, 4),
        "dynamics_direction_agreement": round(dynamics_agreement, 4),
        "appraisal_similarity": round(appraisal_similarity, 4),
        "change_score": round(
            max(1.0 - state_agreement, 1.0 - dynamics_agreement, 1.0 - appraisal_similarity),
            4,
        ),
    }


def _replay_interpretations(factory, trajectory, recent_k, critical):
    checkpoint = trajectory["turns"][-1]
    base_snapshot = checkpoint["environment_snapshot_before"]
    history = list(base_snapshot.get("history", []))
    snapshots = {
        "full": deepcopy(base_snapshot),
        "recent_k": deepcopy(base_snapshot),
        "critical_event_removed": deepcopy(base_snapshot),
    }
    snapshots["recent_k"]["history"] = history[-2 * recent_k:]
    snapshots["critical_event_removed"]["history"] = [
        item for item in history
        if str(item.get("turn_id")) != str(critical).lstrip("t")
    ]
    outputs = {}
    for name, snapshot in snapshots.items():
        environment = factory()
        environment.restore(snapshot)
        _, outputs[name] = environment.step(checkpoint["policy_action"])
    return {
        "full_vs_recent": _interpretation_comparison(outputs["full"], outputs["recent_k"]),
        "full_vs_critical_removed": _interpretation_comparison(
            outputs["full"], outputs["critical_event_removed"]
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--rollout-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recent-k", type=int, default=2)
    args = parser.parse_args()
    config = load_rollout_config(args.rollout_config)
    specs = provider_specs(config)
    providers = {
        family: build_provider(spec["provider"])
        for family, spec in specs.items()
    }
    scenarios = {
        item["scenario_id"]: item
        for item in load_scenarios("configs/scenarios")
    }
    environment_factories = {
        scenario_id: ModelEnvironmentFactory(
            scenario,
            config["environment"]["provider"],
            config["environment"].get("sampling", {}),
        )
        for scenario_id, scenario in scenarios.items()
    }
    records = []
    for trajectory in load_records(args.raw_root):
        family = trajectory["policy_provenance"]["model_family"]
        spec = specs[family]
        provider = providers[family]
        full, recent, removed, critical = observation_variants(
            trajectory, args.recent_k
        )
        full_action = trajectory["turns"][-1]["policy_action"]["text"]
        recent_action = generate(provider, recent, spec.get("sampling", {}))
        removed_action = generate(provider, removed, spec.get("sampling", {}))
        recent_similarity = text_similarity(full_action, recent_action)
        removed_similarity = text_similarity(full_action, removed_action)
        interpretation = _replay_interpretations(
            environment_factories[trajectory["scenario_id"]],
            trajectory,
            args.recent_k,
            critical,
        )
        interpretation_score = max(
            interpretation["full_vs_recent"]["change_score"],
            interpretation["full_vs_critical_removed"]["change_score"],
        )
        score = max(
            1.0 - recent_similarity,
            1.0 - removed_similarity,
            interpretation_score,
        )
        records.append({
            "trajectory_id": trajectory["trajectory_id"],
            "checkpoint_turn_id": trajectory["turns"][-1]["turn_id"],
            "full_history_action": full_action,
            "recent_k_action": recent_action,
            "critical_event_removed_action": removed_action,
            "critical_event_turn_ids": [critical],
            "full_vs_recent_similarity": round(recent_similarity, 4),
            "full_vs_removed_similarity": round(removed_similarity, 4),
            "environment_interpretation": interpretation,
            "score": round(score, 4),
            "passed": score >= 0.20 and (
                removed_similarity < 0.85
                or interpretation["full_vs_critical_removed"]["change_score"] >= 0.15
            ),
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"records": records}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "trajectory_count": len(records),
        "passed": sum(item["passed"] for item in records),
        "output": str(args.output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
