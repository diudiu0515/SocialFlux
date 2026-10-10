#!/usr/bin/env python3
"""Probe pre-registered turns under a versioned State runtime.

This is diagnostic evidence only: it reuses recorded pre-turn context, makes
one appraisal call per requested turn, and makes zero response calls.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from environment.appraisal import ModelAppraiser  # noqa: E402
from environment.state_transition_contract import validate_state_v3_scenario  # noqa: E402
from providers.factory import build_provider, public_provider_config  # noqa: E402
from rollout.configuration import load_rollout_config  # noqa: E402
from scripts.run_state_v3_shadow_replay import ShadowReplayStateUpdater  # noqa: E402


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def behavioral(items):
    return [
        item for item in (items or [])
        if str(item.get("variable", "")).startswith(
            "behavioral_disposition."
        )
    ]


def summarize(rows):
    completed = [row for row in rows if row["status"] == "completed"]
    return {
        "target_count": len(rows),
        "completed_count": len(completed),
        "error_count": len(rows) - len(completed),
        "baseline_turns_with_selected_behavioral_change": sum(
            any(item.get("selected") for item in row["baseline_behavioral_calibration"])
            for row in rows
        ),
        "new_turns_with_behavioral_candidate": sum(
            bool(row.get("new_behavioral_candidates")) for row in completed
        ),
        "new_turns_with_selected_behavioral_change": sum(
            bool(row.get("new_behavioral_selected")) for row in completed
        ),
        "native_grounding_rejection_turn_count": sum(
            bool(
                row.get("grounding_diagnostic", {}).get(
                    "native_rollout_would_reject_action"
                )
            )
            for row in completed
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--rollout-config", type=Path, required=True)
    parser.add_argument("--turn-ids", required=True)
    parser.add_argument("--selection-basis", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    turn_numbers = [
        int(item.strip().removeprefix("t"))
        for item in args.turn_ids.split(",")
        if item.strip()
    ]
    source = load(args.source)
    scenario = load(args.scenario)
    validate_state_v3_scenario(scenario)
    config = load_rollout_config(args.rollout_config)
    provider_config = config["environment"]["provider"]
    provider = build_provider(provider_config)
    sampling = config["environment"].get("sampling", {})
    prompt_id = config["environment"]["appraisal_prompt_id"]
    profile = config["environment"]["state_calibration_profile"]
    rows = []

    def payload(status):
        return {
            "format": "socialflux_state_behavior_targeted_probe_v2",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "scenario_id": source["scenario_id"],
            "source_trajectory_id": source["trajectory_id"],
            "target_turn_ids": [f"t{number}" for number in turn_numbers],
            "selection_basis": args.selection_basis,
            "single_appraisal_call_per_target_turn": True,
            "response_model_request_count": 0,
            "appraisal_prompt_id": prompt_id,
            "state_calibration_profile": profile,
            "state_transition_runtime_revision": config["environment"].get(
                "state_transition_runtime_revision"
            ),
            "provider": public_provider_config(provider_config),
            "fingerprints": {
                "source_trajectory_sha256": sha256_file(args.source),
                "scenario_sha256": sha256_file(args.scenario),
                "rollout_config_sha256": sha256_file(args.rollout_config),
            },
            "summary": summarize(rows),
            "turns": rows,
            "causal_limitations": [
                "Each target turn reuses its recorded pre-turn state, memory, and ledger.",
                "The probe makes no environment response request.",
                "The artifact is not a native rollout or Gate acceptance evidence.",
            ],
            "provider_metrics": getattr(provider, "metrics", {}),
            "human_review": "pending",
        }

    for number in turn_numbers:
        turn = source["turns"][number - 1]
        row = {
            "turn_id": turn["turn_id"],
            "policy_action": turn["policy_action"],
            "baseline_behavioral_candidates": behavioral(
                turn.get("appraisal", {}).get("state_impacts", [])
            ),
            "baseline_behavioral_calibration": behavioral(
                turn.get("calibration", {}).get("state_impacts", [])
            ),
        }
        updater = ShadowReplayStateUpdater(
            scenario,
            provider,
            sampling,
            appraiser=ModelAppraiser(
                scenario, provider, sampling, prompt_id=prompt_id
            ),
            calibration_profile=profile,
        )
        try:
            transition = updater.update(
                action=turn["policy_action"],
                previous_state=turn["state_before"],
                previous_dynamics=turn["dynamics_before"],
                memory=turn["memory_view"],
                longitudinal_context=(turn.get("observation") or {}).get(
                    "longitudinal_context"
                ),
                interaction_ledger=turn.get("interaction_ledger_before"),
            )
            calibration = transition.get("calibration", {})
            new_behavioral = behavioral(
                transition["appraisal"].get("state_impacts", [])
            )
            behavioral_calibration = behavioral(
                calibration.get("state_impacts", [])
            )
            row.update({
                "status": "completed",
                "new_event_features": transition["appraisal"].get(
                    "event_features", {}
                ),
                "new_state_impacts": transition["appraisal"].get(
                    "state_impacts", []
                ),
                "new_behavioral_candidates": new_behavioral,
                "new_behavioral_calibration": behavioral_calibration,
                "new_behavioral_selected": [
                    item for item in behavioral_calibration
                    if item.get("selected") is True
                ],
                "state_delta": transition["state_delta"],
                "grounding_diagnostic": updater.claim_diagnostics[-1],
            })
        except Exception as exc:
            row.update({
                "status": "error",
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
        rows.append(row)
        atomic(args.output, payload("running"))

    result = payload("diagnostic_only_not_native_rollout")
    atomic(args.output, result)
    print(json.dumps({
        "output": str(args.output),
        **result["summary"],
        "human_review": result["human_review"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
