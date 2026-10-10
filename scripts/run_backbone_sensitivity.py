#!/usr/bin/env python3
"""Replay matched checkpoints through two different environment backbones."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_VERSION = "gate2_backbone_sensitivity_v2"

from environment.memory import MemoryModule
from environment.appraisal import ModelAppraiser
from environment.state_updater import ModelStateUpdater, apply_transition
from evaluation.backbone_sensitivity import compare_transitions, failed_comparison, summarize_backbone_sensitivity
from providers.factory import build_provider, public_provider_config
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


def resumable_successes(path, config, enabled):
    if not enabled or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected_families = [
        item.get("model_family") for item in config.get("backbones", [])
    ]
    observed_families = [
        item.get("model_family") for item in payload.get("backbones", [])
    ]
    if (
        payload.get("appraisal_prompt_id")
        != config.get("appraisal_prompt_id", "environment_appraisal_v11")
        or payload.get("state_calibration_profile")
        != config.get("state_calibration_profile", "sparse_v1")
        or observed_families != expected_families
    ):
        return {}
    return {
        item["scenario_id"]: item
        for item in payload.get("records", [])
        if item.get("scenario_id")
        and not item.get("replay_errors")
        and not item.get("comparison", {}).get("replay_failed")
    }


def replay_transition(
    scenario, backbone, checkpoint, *, appraisal_prompt_id,
    state_calibration_profile,
):
    """Replay only appraisal/state transition, the quantity E6 compares."""
    snapshot = checkpoint["environment_snapshot_before"]
    action = checkpoint["policy_action"]
    memory = MemoryModule().retrieve(snapshot.get("history", []), action)
    provider = build_provider(backbone["provider"])
    transition = ModelStateUpdater(
        scenario,
        provider,
        backbone.get("sampling", {}),
        appraiser=ModelAppraiser(
            scenario,
            provider,
            backbone.get("sampling", {}),
            prompt_id=appraisal_prompt_id,
        ),
        calibration_profile=state_calibration_profile,
    ).update(
        action=action,
        previous_state=snapshot["state"],
        previous_dynamics=snapshot["dynamics"],
        memory=memory,
    )
    _, _, numeric_state_delta, numeric_dynamics_delta = apply_transition(
        snapshot["state"],
        snapshot["dynamics"],
        transition,
    )
    return {
        "appraisal": transition["appraisal"],
        "evidence_turn_ids": transition["evidence_turn_ids"],
        "calibration": transition.get("calibration", {}),
        "numeric_state_delta": numeric_state_delta,
        "numeric_dynamics_delta": numeric_dynamics_delta,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--scenario-root", type=Path, default=Path("configs/scenarios"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scenario-limit", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    for name in ("raw_root", "config", "scenario_root", "output"):
        path = Path(getattr(args, name)).expanduser()
        setattr(
            args,
            name,
            path.resolve() if path.is_absolute() else (ROOT / path).resolve(),
        )
    config = json.loads(args.config.read_text(encoding="utf-8"))
    appraisal_prompt_id = config.get(
        "appraisal_prompt_id", "environment_appraisal_v11"
    )
    state_calibration_profile = config.get(
        "state_calibration_profile", "sparse_v1"
    )
    backbones = config.get("backbones", [])
    for backbone in backbones:
        backbone.setdefault("sampling", {})["temperature"] = 0
    if len(backbones) != 2:
        raise ValueError("backbone sensitivity requires exactly two backbones")
    models = [item.get("provider", {}).get("model") for item in backbones]
    families = [item.get("model_family") for item in backbones]
    if not all(models) or len(set(models)) != 2 or not all(families) or len(set(families)) != 2:
        raise ValueError("backbones must record two different models and model families")
    scenarios = {item["scenario_id"]: item for item in load_scenarios(args.scenario_root)}
    trajectories = load_records(args.raw_root)
    checkpoints = select_checkpoints(trajectories, args.scenario_limit)
    expected_scenario_ids = sorted(
        trajectory["scenario_id"] for trajectory, _ in checkpoints
    )
    expected_trajectory_ids = sorted(
        trajectory["trajectory_id"] for trajectory, _ in checkpoints
    )
    completed = resumable_successes(args.output, config, args.resume)
    if args.resume and args.output.exists():
        resume_payload = json.loads(args.output.read_text(encoding="utf-8"))
        if (
            resume_payload.get("experiment_version") != EXPERIMENT_VERSION
            or sorted(resume_payload.get("input_scenario_ids", []))
            != expected_scenario_ids
            or sorted(resume_payload.get("input_trajectory_ids", []))
            != expected_trajectory_ids
        ):
            completed = {}
    records = []
    for trajectory, checkpoint in checkpoints:
        if trajectory["scenario_id"] in completed:
            records.append(completed[trajectory["scenario_id"]])
            continue
        outputs = []
        replay_errors = []
        for backbone in backbones:
            try:
                outputs.append(replay_transition(
                    scenarios[trajectory["scenario_id"]],
                    backbone,
                    checkpoint,
                    appraisal_prompt_id=appraisal_prompt_id,
                    state_calibration_profile=state_calibration_profile,
                ))
            except (ValueError, OSError, TimeoutError, RuntimeError) as exc:
                outputs.append(None)
                replay_errors.append({
                    "model_family": backbone["model_family"],
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "validation_error": str(getattr(exc, "last_error", "")),
                    "last_raw": str(getattr(exc, "last_raw", ""))[-2000:],
                })
        comparison = (
            failed_comparison()
            if replay_errors
            else compare_transitions(outputs[0], outputs[1])
        )
        records.append({
            "scenario_id": trajectory["scenario_id"],
            "source_trajectory_id": trajectory["trajectory_id"],
            "checkpoint_turn_id": checkpoint["turn_id"],
            "action": checkpoint["policy_action"]["text"],
            "comparison": comparison,
            "appraisals": [
                output["appraisal"] if output is not None else None
                for output in outputs
            ],
            "calibrations": [
                output["calibration"] if output is not None else None
                for output in outputs
            ],
            "replay_errors": replay_errors,
            "replay_scope": "appraisal_and_state_transition",
        })
        print(json.dumps({
            "progress": len(records),
            "scenario_id": trajectory["scenario_id"],
            "replay_error_count": len(replay_errors),
        }, ensure_ascii=False), file=sys.stderr, flush=True)
    summary = summarize_backbone_sensitivity(records)
    summary["backbone_activity_by_model_family"] = {
        backbones[0]["model_family"]: summary["backbone_activity"]["left"],
        backbones[1]["model_family"]: summary["backbone_activity"]["right"],
    }
    result = {
        "format": "socialflux_backbone_sensitivity_v1",
        "experiment_version": EXPERIMENT_VERSION,
        "input_scenario_ids": expected_scenario_ids,
        "input_trajectory_ids": expected_trajectory_ids,
        "replay_scope": "appraisal_and_state_transition",
        "appraisal_prompt_id": appraisal_prompt_id,
        "state_calibration_profile": state_calibration_profile,
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
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(json.dumps({"output": str(args.output), **summary}, ensure_ascii=False, indent=2))
    if not summary["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
