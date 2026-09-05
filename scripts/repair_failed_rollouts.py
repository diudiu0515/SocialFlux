#!/usr/bin/env python3
"""Replace only trajectories that fail the current clean-pool quality gate."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from environment.factory import ModelEnvironmentFactory
from evaluation.instance_quality import audit_trajectory
from rollout.logger import TrajectoryLogger
from rollout.manifest import write_manifest
from rollout.runner import RolloutRunner
from scripts.run_pipeline import (
    _policy_from_spec,
    _policy_specs,
    _write_dialogues,
    load_rollout_config,
    load_scenario_records,
    select_scenario_records,
)


def _load_bundle(scenario_path):
    rollout_dir = Path(scenario_path).parent / "rollouts"
    manifest_path = rollout_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    trajectories = [
        json.loads((rollout_dir / f"{trajectory_id}.json").read_text(encoding="utf-8"))
        for trajectory_id in manifest["trajectory_ids"]
    ]
    return rollout_dir, manifest, trajectories


def _policy_lookup(config):
    result = {}
    for spec, run_index in _policy_specs(config):
        policy = _policy_from_spec(spec, run_index)
        result[policy.policy_id] = (spec, run_index)
    return result


def _seed_offset(value, offset):
    updated = deepcopy(value)
    if isinstance(updated.get("seed"), int):
        updated["seed"] += offset
    return updated


def _generate_clean(scenario, config, spec, run_index, max_attempts):
    last_audit = None
    last_error = None
    for attempt in range(max_attempts):
        offset = (attempt + 1) * 100_003
        environment_factory = ModelEnvironmentFactory(
            scenario,
            config["environment"]["provider"],
            _seed_offset(config["environment"].get("sampling", {}), offset),
        )
        varied_spec = deepcopy(spec)
        varied_spec["sampling"] = _seed_offset(spec.get("sampling", {}), offset)
        policy = _policy_from_spec(varied_spec, run_index)
        try:
            trajectory = RolloutRunner(environment_factory).run(
                policy,
                max_turns=config.get("pilot_limits", {}).get("rollout_turns"),
            )
        except ValueError as exc:
            last_error = str(exc)
            continue
        last_audit = audit_trajectory(trajectory)
        if last_audit["passed"]:
            return trajectory, attempt + 1
    raise RuntimeError(
        f"could not generate a clean trajectory for {scenario['scenario_id']} / "
        f"{spec['policy_id']}: audit={last_audit}; error={last_error}"
    )


def repair_scenario(scenario_path, scenario, config, max_attempts):
    rollout_dir, manifest, trajectories = _load_bundle(scenario_path)
    lookup = _policy_lookup(config)
    replacements = []
    repaired = []
    for trajectory in trajectories:
        audit = audit_trajectory(trajectory)
        if audit["passed"]:
            repaired.append(trajectory)
            continue
        policy_id = trajectory["policy_id"]
        if policy_id not in lookup:
            raise ValueError(f"no config policy matches {policy_id}")
        replacement, attempts = _generate_clean(
            scenario,
            config,
            *lookup[policy_id],
            max_attempts,
        )
        TrajectoryLogger(rollout_dir).write(replacement)
        rejected_dir = rollout_dir / "rejected"
        rejected_dir.mkdir(exist_ok=True)
        old_path = rollout_dir / f"{trajectory['trajectory_id']}.json"
        shutil.move(str(old_path), rejected_dir / old_path.name)
        replacements.append({
            "old_trajectory_id": trajectory["trajectory_id"],
            "new_trajectory_id": replacement["trajectory_id"],
            "policy_id": policy_id,
            "attempts": attempts,
            "old_audit": audit,
        })
        repaired.append(replacement)
    if replacements:
        _write_dialogues(rollout_dir / "dialogues.md", scenario, repaired)
        config_record = deepcopy(manifest.get("config", {}))
        config_record["clean_pool_repair"] = {
            "quality_gate": "distinct_text_v2",
            "replacement_count": len(replacements),
        }
        write_manifest(rollout_dir / "manifest.json", repaired, config_record)
        rejected_manifest = rollout_dir / "rejected" / "manifest.json"
        prior = (
            json.loads(rejected_manifest.read_text(encoding="utf-8"))
            if rejected_manifest.exists()
            else []
        )
        rejected_manifest.write_text(
            json.dumps(prior + replacements, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return {
        "scenario_id": scenario["scenario_id"],
        "replacement_count": len(replacements),
        "replacements": replacements,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", type=Path, default=Path("configs/scenarios"))
    parser.add_argument("--rollout-config", type=Path, required=True)
    parser.add_argument("--scenario-id", dest="scenario_ids", action="append")
    parser.add_argument("--max-attempts", type=int, default=4)
    args = parser.parse_args()
    if args.max_attempts < 1:
        raise ValueError("max-attempts must be positive")
    config = load_rollout_config(args.rollout_config)
    records = select_scenario_records(
        load_scenario_records(args.scenarios),
        args.scenario_ids,
    )
    results = [
        repair_scenario(path, scenario, config, args.max_attempts)
        for path, scenario in records
    ]
    print(json.dumps({
        "scenario_count": len(results),
        "replacement_count": sum(item["replacement_count"] for item in results),
        "scenarios": results,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
