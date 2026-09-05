#!/usr/bin/env python3
"""Generate free-form model trajectories and derive SocialFlux T1/T2/T3."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from environment.factory import ModelEnvironmentFactory
from evaluation.leakage import assert_no_leaks
from offline.candidate_generation import ModelCandidateGenerator
from offline.rollout_builders import (
    build_t1_checkpoints,
    build_t2_pairs,
    build_t3_candidates,
)
from policies.model_policy import ModelPolicy
from providers.factory import build_provider, public_provider_config
from rollout.counterfactual import branch_counterfactuals
from rollout.logger import TrajectoryLogger
from rollout.manifest import write_manifest
from rollout.runner import RolloutRunner
from schemas.validate import validate_scenario, validate_trajectory
from scripts.scenario_docs import (
    assert_document_current,
    assert_manifest_current,
    discover_scenario_paths,
)
from scripts.task_docs import write_task_review


def load_scenario_records(directory):
    directory = Path(directory)
    assert_manifest_current(directory)
    records = []
    for path in discover_scenario_paths(directory):
        assert_document_current(path)
        scenario = json.loads(path.read_text(encoding="utf-8"))
        validate_scenario(scenario)
        records.append((path, scenario))
    return records


def load_scenarios(directory):
    return [scenario for _, scenario in load_scenario_records(directory)]


def select_scenario_records(records, scenario_ids=None):
    if not scenario_ids:
        return list(records)
    requested = list(dict.fromkeys(scenario_ids))
    by_id = {scenario["scenario_id"]: (path, scenario) for path, scenario in records}
    missing = [scenario_id for scenario_id in requested if scenario_id not in by_id]
    if missing:
        raise ValueError(f"unknown scenario IDs: {missing}")
    return [by_id[scenario_id] for scenario_id in requested]


def load_rollout_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("format") != "socialflux_rollout_pool_v1":
        raise ValueError("rollout config format must be socialflux_rollout_pool_v1")
    if "environment" not in config or "provider" not in config["environment"]:
        raise ValueError("rollout config requires one canonical environment provider")
    if "construction" not in config or "provider" not in config["construction"]:
        raise ValueError("rollout config requires a construction provider for T2/T3")
    policies = config.get("policies", [])
    if len(policies) < 2:
        raise ValueError("trajectory diversity requires at least two model/sampling policy specs")
    identities = {
        (
            item.get("policy_id"),
            item.get("provider", {}).get("model"),
            json.dumps(item.get("sampling", {}), sort_keys=True),
        )
        for item in policies
    }
    if len(identities) < 2:
        raise ValueError("rollout policy specs must differ by model and/or sampling")
    limits = config.get("pilot_limits")
    if limits is not None:
        allowed = {"rollout_turns", "t1", "t2", "t3", "t3_horizon"}
        if not isinstance(limits, dict) or set(limits) - allowed:
            raise ValueError("pilot_limits contains unsupported fields")
        for key in ("rollout_turns", "t1", "t2", "t3"):
            if key in limits and (not isinstance(limits[key], int) or limits[key] < 1):
                raise ValueError(f"pilot_limits.{key} must be a positive integer")
        horizon = limits.get("t3_horizon", 5)
        if not isinstance(horizon, int) or not 5 <= horizon <= 10:
            raise ValueError("pilot_limits.t3_horizon must be between 5 and 10")
    if config.get("t2_pairing", "all") not in {"all", "within_source_model"}:
        raise ValueError("t2_pairing must be all or within_source_model")
    return config


def _public_config(config):
    return {
        "format": config["format"],
        "environment": {
            "provider": public_provider_config(config["environment"]["provider"]),
            "sampling": config["environment"].get("sampling", {}),
        },
        "construction": {
            "provider": public_provider_config(config["construction"]["provider"]),
            "sampling": config["construction"].get("sampling", {}),
        },
        "policies": [
            {
                "policy_id": item["policy_id"],
                "provider": public_provider_config(item["provider"]),
                "sampling": item.get("sampling", {}),
                "runs": item.get("runs", 1),
            }
            for item in config["policies"]
        ],
        "pilot_limits": deepcopy(config.get("pilot_limits")),
        "t2_pairing": config.get("t2_pairing", "all"),
    }


def _prepare_rollout_directory(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    for candidate in path.glob("*.json"):
        candidate.unlink()
    for document_name in ("dialogues.md", "tasks.md"):
        document = path / document_name
        if document.exists():
            document.unlink()
    return path


def _write_dialogues(path, scenario, trajectories):
    lines = [
        f"# {scenario['title']} — Free-form Rollout Dialogues",
        "",
        "> Generated from open-ended model interaction. No predefined strategy labels or scripted action paths.",
        "",
        f"- Scenario ID: `{scenario['scenario_id']}`",
        f"- Trajectories: `{len(trajectories)}`",
        "",
    ]
    for trajectory in trajectories:
        provenance = trajectory.get("policy_provenance", {})
        lines.extend([
            f"## `{trajectory['policy_id']}`",
            "",
            f"Model: `{provenance.get('model', 'unknown')}` · sampling: `{json.dumps(provenance.get('sampling', {}), ensure_ascii=False, sort_keys=True)}`",
            "",
        ])
        for turn in trajectory["turns"]:
            lines.extend([
                f"### {turn['turn_id']}",
                "",
                f"**Evaluated model:** {turn['policy_action']['text']}",
                "",
                f"**Environment character:** {turn['environment_response']}",
                "",
            ])
            expression = turn.get("observable_expression", {})
            if expression:
                lines.extend([
                    f"_Expression: {expression.get('facial_expression', '—')}; gaze: {expression.get('gaze', '—')}; prosody: {expression.get('prosody', '—')}._",
                    "",
                ])
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def _policy_from_spec(spec, run_index=0):
    sampling = deepcopy(spec.get("sampling", {}))
    if isinstance(sampling.get("seed"), int):
        sampling["seed"] += run_index
    policy_id = spec["policy_id"]
    if spec.get("runs", 1) > 1:
        policy_id = f"{policy_id}__run_{run_index + 1}"
    return ModelPolicy(
        policy_id,
        build_provider(spec["provider"]),
        sampling=sampling,
    )


def _policy_specs(config):
    for spec in config["policies"]:
        runs = spec.get("runs", 1)
        if not isinstance(runs, int) or runs < 1:
            raise ValueError("policy runs must be a positive integer")
        for run_index in range(runs):
            yield spec, run_index


def _require_reviewed(scenario, allow_unreviewed):
    status = scenario["construction_status"]
    if allow_unreviewed:
        return
    if status["quality_gate"] != "approved":
        raise ValueError(
            f"{scenario['scenario_id']} has no approved scenario quality gate; "
            "use --allow-unreviewed only for development"
        )
    if status["initial_state"] != "human_frozen":
        raise ValueError(
            f"{scenario['scenario_id']} S0/D0 is not human_frozen; "
            "use --allow-unreviewed only for development"
        )


def _load_existing_rollouts(rollout_dir):
    trajectories = []
    manifest_path = Path(rollout_dir) / "manifest.json"
    if not manifest_path.exists():
        return trajectories
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("format") != "socialflux_rollout_manifest_v2"
        or manifest.get("config", {}).get("origin") != "free_form_model_interaction"
    ):
        raise ValueError(f"rollout bundle is not a v2 free-form pool: {rollout_dir}")
    for trajectory_id in manifest.get("trajectory_ids", []):
        path = Path(rollout_dir) / f"{trajectory_id}.json"
        trajectory = json.loads(path.read_text(encoding="utf-8"))
        validate_trajectory(trajectory)
        trajectories.append(trajectory)
    return trajectories


def _write_offline(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            assert_no_leaks(record)
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _round_robin(groups, limit):
    selected = []
    depth = 0
    while len(selected) < limit and any(depth < len(group) for group in groups):
        for group in groups:
            if depth < len(group):
                selected.append(group[depth])
                if len(selected) >= limit:
                    break
        depth += 1
    return selected


def _round_robin_turns(trajectories):
    depth = 0
    while any(depth < len(trajectory.get("turns", [])) for trajectory in trajectories):
        for trajectory in trajectories:
            if depth < len(trajectory.get("turns", [])):
                yield trajectory, trajectory["turns"][depth]
        depth += 1


def run_scenario(scenario, scenario_path, output_dir, config, *, build_only=False, allow_unreviewed=False):
    _require_reviewed(scenario, allow_unreviewed)
    scenario_id = scenario["scenario_id"]
    scenario_output = Path(output_dir) / scenario_id
    rollout_dir = Path(scenario_path).parent / "rollouts"
    environment_factory = ModelEnvironmentFactory(
        scenario,
        config["environment"]["provider"],
        config["environment"].get("sampling", {}),
    )

    policy_lookup = {
        _policy_from_spec(spec, run_index).policy_id: (spec, run_index)
        for spec, run_index in _policy_specs(config)
    }
    pilot_limits = config.get("pilot_limits", {})
    if build_only:
        trajectories = _load_existing_rollouts(rollout_dir)
        if not trajectories:
            raise ValueError(f"no valid free-form trajectory pool found for {scenario_id}")
    else:
        rollout_dir = _prepare_rollout_directory(rollout_dir)
        logger = TrajectoryLogger(rollout_dir)
        trajectories = []
        for spec, run_index in _policy_specs(config):
            policy = _policy_from_spec(spec, run_index)
            trajectories.append(
                RolloutRunner(environment_factory, logger=logger).run(
                    policy,
                    max_turns=pilot_limits.get("rollout_turns"),
                )
            )
        _write_dialogues(rollout_dir / "dialogues.md", scenario, trajectories)
        write_manifest(
            rollout_dir / "manifest.json",
            trajectories,
            {
                "origin": "free_form_model_interaction",
                "rollout_config": _public_config(config),
                "dialogues": "dialogues.md",
                "task_review": "tasks.md",
            },
        )

    t1_limit = pilot_limits.get(
        "t1",
        scenario.get("sampling_plan", {}).get("t1_max", 5),
    )
    t1_groups = [
        build_t1_checkpoints(trajectory, scenario.get("target_state_ids", []))
        for trajectory in trajectories
    ]
    t1_candidates = _round_robin(t1_groups, t1_limit)

    construction = ModelCandidateGenerator(
        build_provider(config["construction"]["provider"]),
        config["construction"].get("sampling", {}),
    )
    t2_limit = pilot_limits.get(
        "t2",
        scenario.get("sampling_plan", {}).get("t2_max", 3),
    )
    t2 = build_t2_pairs(
        trajectories,
        construction.shared_observation,
        t2_limit,
        scenario.get("target_state_ids", []),
        same_source_model=config.get("t2_pairing") == "within_source_model",
    )

    t3_limit = pilot_limits.get(
        "t3",
        scenario.get("sampling_plan", {}).get("t3_max", 4),
    )
    t3_horizon = pilot_limits.get(
        "t3_horizon",
        scenario.get("t3_delayed_horizon", 5),
    )
    t3 = []
    branches = []
    for trajectory, turn in _round_robin_turns(trajectories):
        if len(t3) >= t3_limit:
            break
        actions = construction.candidate_actions(turn["observation"], count=3)
        checkpoint = {
            **turn,
            "trajectory_id": trajectory["trajectory_id"],
            "scenario_id": scenario_id,
        }
        t3.append(build_t3_candidates(
            checkpoint,
            actions,
            t3_horizon,
            scenario.get("target_state_ids", []),
        ))
        spec_run = policy_lookup.get(trajectory["policy_id"])
        if spec_run is None:
            provenance = trajectory.get("policy_provenance", {})
            for candidate_spec, candidate_run in _policy_specs(config):
                candidate = _policy_from_spec(candidate_spec, candidate_run)
                if (
                    candidate.provenance.get("model") == provenance.get("model")
                    and candidate.provenance.get("sampling") == provenance.get("sampling")
                ):
                    spec_run = (candidate_spec, candidate_run)
                    break
        if spec_run is None:
            raise ValueError(
                f"no rollout-config policy matches trajectory {trajectory['trajectory_id']}"
            )
        spec, run_index = spec_run
        new_branches = branch_counterfactuals(
            environment_factory,
            turn,
            actions,
            lambda spec=spec, run_index=run_index: _policy_from_spec(spec, run_index),
            t3_horizon,
        )
        for branch in new_branches:
            branch["scenario_id"] = scenario_id
            branch["source_trajectory_id"] = trajectory["trajectory_id"]
        branches.extend(new_branches)

    _write_offline(
        scenario_output / "offline" / "instances.jsonl",
        t1_candidates + t2 + t3,
    )
    validation_dir = scenario_output / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    (validation_dir / "local_action_interventions.json").write_text(
        json.dumps(branches, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_task_review(
        rollout_dir / "tasks.md",
        scenario,
        t1_candidates + t2 + t3,
        trajectories,
        branches,
    )
    summary = {
        "scenario_id": scenario_id,
        "trajectory_count": len(trajectories),
        "trajectory_origin": "free_form_model_interaction",
        "rollout_bundle": f"configs/scenarios/{Path(scenario_path).parent.name}/rollouts",
        "t1": len(t1_candidates),
        "t2": len(t2),
        "t3": len(t3),
        "local_intervention_branches": len(branches),
        "task_review": f"configs/scenarios/{Path(scenario_path).parent.name}/rollouts/tasks.md",
        "ground_truth_status": "pending_human_annotation",
        "run_scope": "pilot" if pilot_limits else "full_scenario",
        "pilot_limits": deepcopy(pilot_limits) if pilot_limits else None,
    }
    scenario_output.mkdir(parents=True, exist_ok=True)
    (scenario_output / "pipeline_manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", type=Path, default=Path("configs/scenarios"))
    parser.add_argument("--output", type=Path, default=Path("build/pipeline_v2"))
    parser.add_argument(
        "--scenario-id",
        dest="scenario_ids",
        action="append",
        help="Run only this canonical scenario ID; repeat to select multiple scenarios.",
    )
    parser.add_argument("--rollout-config", type=Path, required=True)
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--allow-unreviewed", action="store_true")
    args = parser.parse_args()
    config = load_rollout_config(args.rollout_config)
    records = select_scenario_records(
        load_scenario_records(args.scenarios),
        args.scenario_ids,
    )
    summaries = [
        run_scenario(
            scenario,
            path,
            args.output,
            config,
            build_only=args.build_only,
            allow_unreviewed=args.allow_unreviewed,
        )
        for path, scenario in records
    ]
    instances = []
    for summary in summaries:
        source = args.output / summary["scenario_id"] / "offline" / "instances.jsonl"
        instances.extend(
            json.loads(line)
            for line in source.read_text(encoding="utf-8").splitlines()
            if line
        )
    args.output.mkdir(parents=True, exist_ok=True)
    _write_offline(args.output / "instances.jsonl", instances)
    result = {
        "format": "socialflux_pipeline_manifest_v2",
        "scenario_count": len(summaries),
        "trajectory_origin": "free_form_model_interaction",
        "totals": {
            "trajectories": sum(item["trajectory_count"] for item in summaries),
            "t1": sum(item["t1"] for item in summaries),
            "t2": sum(item["t2"] for item in summaries),
            "t3": sum(item["t3"] for item in summaries),
            "instances": len(instances),
        },
        "scenarios": summaries,
        "rollout_config": _public_config(config),
        "ground_truth_status": "pending_human_annotation",
    }
    (args.output / "manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
