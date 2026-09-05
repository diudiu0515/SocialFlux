#!/usr/bin/env python3
"""Replay matched checkpoints through two different environment backbones."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from environment.factory import ModelEnvironmentFactory
from evaluation.backbone_sensitivity import compare_transitions, summarize_backbone_sensitivity
from providers.factory import public_provider_config
from scripts.audit_formal_rollout_pool import load_records
from scripts.run_pipeline import load_scenarios


def select_checkpoints(trajectories, scenario_limit=None):
    selected = []
    seen = set()
    for trajectory in sorted(trajectories, key=lambda item: item["trajectory_id"]):
        scenario_id = trajectory["scenario_id"]
        if scenario_id in seen or not trajectory.get("turns"):
            continue
        turn = trajectory["turns"][len(trajectory["turns"]) // 2]
        selected.append((trajectory, turn))
        seen.add(scenario_id)
        if scenario_limit and len(selected) >= scenario_limit:
            break
    return selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scenario-limit", type=int)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    backbones = config.get("backbones", [])
    if len(backbones) != 2:
        raise ValueError("backbone sensitivity requires exactly two backbones")
    models = [item.get("provider", {}).get("model") for item in backbones]
    families = [item.get("model_family") for item in backbones]
    if not all(models) or len(set(models)) != 2 or not all(families) or len(set(families)) != 2:
        raise ValueError("backbones must record two different models and model families")
    scenarios = {item["scenario_id"]: item for item in load_scenarios("configs/scenarios")}
    records = []
    for trajectory, checkpoint in select_checkpoints(load_records(args.raw_root), args.scenario_limit):
        outputs = []
        for backbone in backbones:
            environment = ModelEnvironmentFactory(
                scenarios[trajectory["scenario_id"]],
                backbone["provider"],
                backbone.get("sampling", {}),
            )()
            environment.restore(checkpoint["environment_snapshot_before"])
            _, replay = environment.step(checkpoint["policy_action"])
            outputs.append(replay)
        records.append({
            "scenario_id": trajectory["scenario_id"],
            "source_trajectory_id": trajectory["trajectory_id"],
            "checkpoint_turn_id": checkpoint["turn_id"],
            "action": checkpoint["policy_action"]["text"],
            "comparison": compare_transitions(outputs[0], outputs[1]),
            "responses": [output["environment_response"] for output in outputs],
        })
    summary = summarize_backbone_sensitivity(records)
    result = {
        "format": "socialflux_backbone_sensitivity_v1",
        "backbones": [
            {
                "model_family": item["model_family"],
                "provider": public_provider_config(item["provider"]),
                "sampling": item.get("sampling", {}),
            }
            for item in backbones
        ],
        "record": summary,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), **summary}, ensure_ascii=False, indent=2))
    if not summary["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
