#!/usr/bin/env python3
"""Probe full/recent/critical-event-removed history from identical checkpoints."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from environment.delta_mapper import flatten_state
from environment.env import coerce_free_form_action
from environment.factory import ModelEnvironmentFactory
from environment.state_updater import apply_transition
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
    """Index effective policy specs by the trajectory policy ID.

    A model family can contain several seeds/policies, so family alone is not a
    stable lookup key. Expanding runs here mirrors run_pipeline's policy ID and
    seed rules without constructing a provider.
    """
    result = {}
    for item in config["policies"]:
        runs = item.get("runs", 1)
        if not isinstance(runs, int) or runs < 1:
            raise ValueError("policy runs must be a positive integer")
        for run_index in range(runs):
            effective = deepcopy(item)
            policy_id = item["policy_id"]
            if runs > 1:
                policy_id = f"{policy_id}__run_{run_index + 1}"
            sampling = deepcopy(item.get("sampling", {}))
            if isinstance(sampling.get("seed"), int):
                sampling["seed"] += run_index
            effective["sampling"] = sampling
            result[policy_id] = effective
    return result


def resolve_policy_spec(trajectory, specs):
    policy_id = trajectory.get("policy_id")
    if policy_id in specs:
        return policy_id, specs[policy_id]
    family = trajectory.get("policy_provenance", {}).get("model_family")
    matches = [
        (candidate_id, spec)
        for candidate_id, spec in specs.items()
        if spec.get("model_family") == family
    ]
    if len(matches) == 1:
        return matches[0]
    raise ValueError(
        f"cannot resolve policy spec for trajectory {trajectory.get('trajectory_id')}: "
        f"policy_id={policy_id!r}, model_family={family!r}, family_matches={len(matches)}"
    )


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
        outputs[name] = _interpret_without_response(
            environment,
            checkpoint["policy_action"],
        )
    return {
        "full_vs_recent": _interpretation_comparison(outputs["full"], outputs["recent_k"]),
        "full_vs_critical_removed": _interpretation_comparison(
            outputs["full"], outputs["critical_event_removed"]
        ),
    }


def _interpret_without_response(environment, action):
    """Run the canonical appraisal/update path without an unused response call."""
    action = coerce_free_form_action(action)
    state_before = deepcopy(environment.session["state"])
    dynamics_before = deepcopy(environment.session["dynamics"])
    memory_view = environment.memory.retrieve(environment.session["history"], action)
    transition = environment.state_updater.update(
        action=action,
        previous_state=state_before,
        previous_dynamics=dynamics_before,
        memory=memory_view,
    )
    _, _, state_numeric, dynamics_numeric = apply_transition(
        state_before,
        dynamics_before,
        transition,
    )
    return {
        "appraisal": transition["appraisal"],
        "numeric_state_delta": state_numeric,
        "numeric_dynamics_delta": dynamics_numeric,
    }


def write_records(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"records": records}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def resumable_records(path, enabled):
    if not enabled or not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records")
    if not isinstance(records, list) or any(
        not isinstance(item, dict) or not item.get("trajectory_id")
        for item in records
    ):
        raise ValueError("history resume output must contain trajectory records")
    ids = [item["trajectory_id"] for item in records]
    if len(ids) != len(set(ids)):
        raise ValueError("history resume output contains duplicate trajectory IDs")
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--rollout-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recent-k", type=int, default=2)
    parser.add_argument("--trajectory-limit", type=int)
    parser.add_argument("--trajectory-id", dest="trajectory_ids", action="append")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.trajectory_limit is not None and args.trajectory_limit < 1:
        raise ValueError("trajectory-limit must be positive")
    config = load_rollout_config(args.rollout_config)
    specs = provider_specs(config)
    providers = {
        policy_id: build_provider(spec["provider"])
        for policy_id, spec in specs.items()
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
    records = resumable_records(args.output, args.resume)
    completed_ids = {item["trajectory_id"] for item in records}
    trajectories = sorted(
        load_records(args.raw_root),
        key=lambda item: (item["scenario_id"], item["trajectory_id"]),
    )
    if args.trajectory_ids:
        requested_ids = set(args.trajectory_ids)
        trajectories = [
            item for item in trajectories
            if item["trajectory_id"] in requested_ids
        ]
        found_ids = {item["trajectory_id"] for item in trajectories}
        missing_ids = requested_ids - found_ids
        if missing_ids:
            raise ValueError(
                "requested history trajectories were not found: "
                + ", ".join(sorted(missing_ids))
            )
    if args.trajectory_limit is not None:
        trajectories = trajectories[:args.trajectory_limit]
    expected_ids = {item["trajectory_id"] for item in trajectories}
    unexpected_ids = completed_ids - expected_ids
    if unexpected_ids:
        raise ValueError(
            "history resume output contains trajectories outside current input: "
            + ", ".join(sorted(unexpected_ids))
        )
    for trajectory in trajectories:
        if trajectory["trajectory_id"] in completed_ids:
            continue
        policy_id, spec = resolve_policy_spec(trajectory, specs)
        provider = providers[policy_id]
        full, recent, removed, critical = observation_variants(
            trajectory, args.recent_k
        )
        observed_checkpoint_action = trajectory["turns"][-1]["policy_action"]["text"]
        full_action = generate(provider, full, spec.get("sampling", {}))
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
            "observed_checkpoint_action": observed_checkpoint_action,
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
        write_records(args.output, records)
        print(json.dumps({
            "progress": len(records),
            "total": len(trajectories),
            "trajectory_id": trajectory["trajectory_id"],
            "passed": records[-1]["passed"],
        }, ensure_ascii=False), file=sys.stderr, flush=True)
    write_records(args.output, records)
    print(json.dumps({
        "trajectory_count": len(records),
        "passed": sum(item["passed"] for item in records),
        "output": str(args.output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
