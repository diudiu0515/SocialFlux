#!/usr/bin/env python3
"""Run one or two turns through the current two-stage environment contract."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from environment.factory import ModelEnvironmentFactory
from rollout.configuration import load_rollout_config
from scripts.run_pipeline import load_scenario_records, select_scenario_records


ROOT = Path(__file__).resolve().parents[1]


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _provider_metrics(provider):
    metrics = getattr(provider, "metrics", None)
    if isinstance(metrics, dict):
        return metrics
    calls = getattr(provider, "_call_index", None)
    return {"request_count": calls} if isinstance(calls, int) else {}


def _environment(config, scenario):
    environment = config["environment"]
    return ModelEnvironmentFactory(
        scenario,
        environment["provider"],
        environment.get("sampling", {}),
        response_provider_config=environment.get("response_provider"),
        response_sampling=environment.get("response_sampling"),
        appraisal_prompt_id=environment["appraisal_prompt_id"],
        response_prompt_id=environment["response_prompt_id"],
        response_validation_profile=environment.get(
            "response_validation_profile", "hard_only"
        ),
        horizon_mode=environment["horizon_mode"],
    )()


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rollout-config", type=Path,
        default=Path("configs/formal_rollout_pool.json"),
    )
    parser.add_argument(
        "--scenarios", type=Path, default=Path("configs/scenarios")
    )
    parser.add_argument("--scenario-id", default="IA_PIPE_001")
    parser.add_argument("--action", required=True)
    parser.add_argument("--followup-action")
    parser.add_argument(
        "--output", type=Path,
        default=Path("build/diagnostics/active_environment_probe.json"),
    )
    args = parser.parse_args()

    config = load_rollout_config(args.rollout_config)
    records = select_scenario_records(
        load_scenario_records(args.scenarios), [args.scenario_id]
    )
    scenario = records[0][1]
    environment = _environment(config, scenario)
    environment.reset(episode_id=f"active-probe-{args.scenario_id}")
    actions = [args.action]
    if args.followup_action:
        actions.append(args.followup_action)

    result = {
        "format": "socialflux_active_environment_probe_v1",
        "created_at_utc": _utc_now(),
        "scenario_id": args.scenario_id,
        "appraisal_prompt_id": config["environment"]["appraisal_prompt_id"],
        "response_prompt_id": config["environment"]["response_prompt_id"],
        "two_independent_environment_stages": True,
        "deterministic_update_between_stages": True,
        "actions": actions,
        "status": "in_progress",
    }
    try:
        turns = []
        for action in actions:
            _, turn = environment.step({"text": action})
            turns.append(turn)
        result.update({
            "status": "completed",
            "turns": turns,
            "appraisal_metrics": _provider_metrics(
                environment.state_updater.provider
            ),
            "response_metrics": _provider_metrics(
                environment.response_generator.provider
            ),
        })
    except Exception as exc:
        result.update({
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "error_diagnostics": list(getattr(exc, "diagnostics", [])),
            "partial_trajectory": environment.private_trajectory(),
            "appraisal_metrics": _provider_metrics(
                environment.state_updater.provider
            ),
            "response_metrics": _provider_metrics(
                environment.response_generator.provider
            ),
        })
    _write(args.output, result)
    print(json.dumps({
        "status": result["status"],
        "scenario_id": result["scenario_id"],
        "turn_count": len(result.get("turns", [])),
        "appraisal_metrics": result["appraisal_metrics"],
        "response_metrics": result["response_metrics"],
        "responses": [
            turn["environment_response"] for turn in result.get("turns", [])
        ],
        "error": result.get("error"),
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    if result["status"] != "completed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
