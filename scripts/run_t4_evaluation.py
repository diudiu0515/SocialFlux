#!/usr/bin/env python3
"""Run and score an online T4 episode with a natural 20-turn maximum."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.t4_configuration import (
    T4_JUDGE_PROMPT,
    load_t4_config,
    public_t4_config,
)
from evaluation.t4_evaluation import (
    T4_MAX_TURNS,
    assert_t4_trajectory,
)
from pipeline.constants import SCENARIO_ROOT, T4_CONFIG
from pipeline.runtime import (
    assert_fable_t4_config,
    build_environment_factory,
    build_policy,
)
from pipeline.scenarios import load_scenarios
from providers.factory import build_provider
from providers.structured import StructuredOutputError
from rollout.runner import RolloutRunner
from tasks.T4.answering import generate_judgment


def run_episode(scenario, config):
    environment = config["environment"]
    environment_factory = build_environment_factory(scenario, environment)
    evaluated = config["evaluated_model"]
    policy = build_policy(
        evaluated,
        provenance_extra={"task": "T4", "max_turns": T4_MAX_TURNS},
    )
    trajectory = RolloutRunner(environment_factory).run(
        policy, max_turns=T4_MAX_TURNS
    )
    return assert_t4_trajectory(trajectory)


def judge_episode(trajectory, scenario, config):
    judge = config["judge"]
    provider = build_provider(judge["provider"])
    seed = judge.get("sampling", {}).get("seed", 7401)
    packet, judgment, request_count = generate_judgment(
        provider, trajectory, scenario, seed, max_attempts=5,
    )
    return packet, judgment, request_count


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pipeline t4")
    parser.add_argument("--config", type=Path, default=T4_CONFIG)
    parser.add_argument("--scenarios", type=Path, default=SCENARIO_ROOT)
    parser.add_argument("--scenario-id", action="append")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true", help="reuse a saved valid 20-turn trajectory")
    args = parser.parse_args(argv)

    config = load_t4_config(args.config)
    assert_fable_t4_config(config)
    scenarios = load_scenarios(args.scenarios)
    requested = set(args.scenario_id or [])
    if requested:
        missing = requested - {item["scenario_id"] for item in scenarios}
        if missing:
            raise ValueError("unknown scenario IDs: " + ", ".join(sorted(missing)))
        scenarios = [item for item in scenarios if item["scenario_id"] in requested]

    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    for scenario in scenarios:
        trajectory_path = args.output / f"{scenario['scenario_id']}.trajectory.json"
        if args.resume and trajectory_path.exists():
            trajectory = assert_t4_trajectory(json.loads(
                trajectory_path.read_text(encoding="utf-8")
            ))
        else:
            trajectory = run_episode(scenario, config)
            trajectory_path.write_text(
                json.dumps(trajectory, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        try:
            packet, judgment, judge_requests = judge_episode(
                trajectory, scenario, config
            )
        except StructuredOutputError as exc:
            failure_path = args.output / f"{scenario['scenario_id']}.judge_failure.json"
            failure_path.write_text(
                json.dumps({
                    "format": "socialflux_t4_judge_failure_v1",
                    "scenario_id": scenario["scenario_id"],
                    "trajectory_path": trajectory_path.name,
                    "turns": len(trajectory["turns"]),
                    "judge_prompt_id": T4_JUDGE_PROMPT,
                    "error": str(exc),
                    "last_error": str(exc.last_error),
                    "last_raw_output": exc.last_raw,
                }, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            raise
        record = {
            "format": "socialflux_t4_result_v2",
            "scenario_id": scenario["scenario_id"],
            "max_turns": T4_MAX_TURNS,
            "observed_turns": len(trajectory["turns"]),
            "ending_reason": trajectory["ending"]["reason"],
            "runtime_config": public_t4_config(config),
            "trajectory": trajectory,
            "judge_packet": packet,
            "automatic_judgment": judgment,
            "judge_request_count": judge_requests,
            "human_validation_status": "pending",
        }
        target = args.output / f"{scenario['scenario_id']}.json"
        target.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        records.append({
            "scenario_id": scenario["scenario_id"],
            "trajectory_id": trajectory["trajectory_id"],
            "turns": len(trajectory["turns"]),
            "result": target.name,
        })

    (args.output / "manifest.json").write_text(
        json.dumps({
            "format": "socialflux_t4_results_manifest_v2",
            "max_turns": T4_MAX_TURNS,
            "count": len(records),
            "records": records,
            "human_validation_status": "pending",
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "completed": len(records),
        "max_turns": T4_MAX_TURNS,
        "observed_turns": [record["turns"] for record in records],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
