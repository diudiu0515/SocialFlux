#!/usr/bin/env python3
"""Archive the four fixed failures and replay their saved appraisals with v6.

This script makes no model or network request. Historical raw assistant text was
not retained by the prior runner; that absence is recorded rather than filled.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from environment.appraisal import ModelAppraiser
from environment.calibration import DeterministicStateCalibrator
from providers.base import ModelProvider
from shared.artifacts import atomic_json as atomic
SOURCE_DIR = ROOT / "data/gpt50/experiment/state_v3_validation/v3226_v328_restored_multiscenario"
OUTPUT_DIR = ROOT / "data/gpt50/experiment/state_v3_validation/v3227_independent_per_variable"
ARTIFACTS = {
    "trust_gpt002_historical_anchor": "positive_trust_gpt002_t3.json",
    "trust_gpt003": "positive_trust_gpt003_t2.json",
    "fairness_gpt026": "positive_fairness_gpt026_t9.json",
    "safety_claude030": "positive_safety_claude030_t6.json",
}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class CaptureOnlyProvider(ModelProvider):
    def __init__(self):
        self.request = None

    def complete(self, messages, **generation):
        self.request = {
            "messages": messages,
            "generation": generation,
        }
        raise RuntimeError("capture only: no provider request made")


def find_turn(trajectory, turn_id):
    return next(turn for turn in trajectory["turns"] if turn["turn_id"] == turn_id)


def main():
    manifest = load(SOURCE_DIR / "manifest.json")
    active_config_path = ROOT / manifest["runtime"]["active_config"]
    active_config = load(active_config_path)
    sampling = active_config["environment"].get("sampling", {})
    archived_cases = []
    replay_cases = []

    for registration in manifest["cases"]:
        pair_id = registration["pair_id"]
        artifact_path = SOURCE_DIR / ARTIFACTS[pair_id]
        artifact = load(artifact_path)
        scenario_path = ROOT / registration["scenario"]
        source_path = ROOT / registration["source"]
        scenario = load(scenario_path)
        trajectory = load(source_path)
        turn_id = registration["positive"]["turn_id"]
        turn = find_turn(trajectory, turn_id)

        capture = CaptureOnlyProvider()
        appraiser = ModelAppraiser(
            scenario, capture, sampling, prompt_id=artifact["appraisal_prompt_id"]
        )
        try:
            appraiser.appraise(
                action=turn["policy_action"],
                previous_state=turn["state_before"],
                previous_dynamics=turn["dynamics_before"],
                memory=turn["memory_view"],
                longitudinal_context=(turn.get("observation") or {}).get(
                    "longitudinal_context"
                ),
                interaction_ledger=turn.get("interaction_ledger_before"),
            )
        except RuntimeError as exc:
            if "capture only" not in str(exc):
                raise

        saved_turn = artifact["turns"][0]
        novelty = (
            turn.get("appraisal", {})
            .get("dialogue_diagnostics", {})
            .get("substantive_novelty", {})
        )
        replay_appraisal = {
            "event_features": saved_turn["new_event_features"],
            "state_impacts": saved_turn["new_state_impacts"],
            "dynamics_impacts": [],
            "dialogue_diagnostics": {"substantive_novelty": novelty},
        }
        replay = DeterministicStateCalibrator(
            scenario, profile="evidence_causal_slow_priority_hysteretic_v6"
        ).calibrate(
            replay_appraisal,
            turn["state_before"],
            turn["dynamics_before"],
        )
        target = registration["positive"]["target"]
        target_diagnostic = next(
            (
                item for item in replay["calibration"]["state_impacts"]
                if item["variable"] == target
            ),
            None,
        )
        archived_cases.append({
            "pair_id": pair_id,
            "turn_id": turn_id,
            "target": target,
            "scenario_path": registration["scenario"],
            "scenario_sha256": digest(scenario_path),
            "source_path": registration["source"],
            "source_sha256": digest(source_path),
            "checkpoint_path": str(artifact_path.relative_to(ROOT)),
            "checkpoint_sha256": digest(artifact_path),
            "run_configuration": {
                "artifact_provider": artifact["provider"],
                "sampling": sampling,
                "prompt_id": artifact["appraisal_prompt_id"],
                "calibration_profile": artifact["state_calibration_profile"],
                "runtime_revision": artifact["state_transition_runtime_revision"],
                "active_config_path": manifest["runtime"]["active_config"],
                "active_config_sha256_at_registration": manifest["runtime"]["active_config_sha256"],
                "active_config_current_sha256": digest(active_config_path),
            },
            "request_reconstruction": {
                "status": "reconstructed_from_frozen_scenario_trajectory_prompt_and_builder",
                "actual_historical_request_was_not_logged": True,
                "request": capture.request,
            },
            "raw_output": {
                "status": "unavailable_not_recorded_by_prior_runner",
                "recoverable": False,
                "parsed_output_retained_below": True,
            },
            "parsed_output": {
                "event_features": saved_turn["new_event_features"],
                "state_impacts": saved_turn["new_state_impacts"],
                "state_delta": saved_turn["state_delta"],
            },
            "provider_metrics": artifact.get("provider_metrics", {}),
            "pre_update_snapshot": {
                "state": turn["state_before"],
                "dynamics": turn["dynamics_before"],
                "memory": turn["memory_view"],
                "longitudinal_context": (turn.get("observation") or {}).get(
                    "longitudinal_context"
                ),
                "interaction_ledger": turn.get("interaction_ledger_before"),
                "policy_action": turn["policy_action"],
            },
        })
        replay_cases.append({
            "pair_id": pair_id,
            "turn_id": turn_id,
            "target": target,
            "semantic_novelty": novelty,
            "raw_candidates": saved_turn["new_state_impacts"],
            "calibration_profile": "evidence_causal_slow_priority_hysteretic_v6",
            "calibration": replay["calibration"],
            "state_delta": replay["state_delta"],
            "target_diagnostic": target_diagnostic,
            "target_selected": bool(target_diagnostic and target_diagnostic["selected"]),
        })

    created = datetime.now(timezone.utc).isoformat()
    atomic(OUTPUT_DIR / "baseline_archive.json", {
        "format": "socialflux_state_failure_baseline_archive_v1",
        "created_at_utc": created,
        "network_requests": 0,
        "historical_limitation": (
            "The prior runner retained parsed appraisals and aggregate finish reasons, "
            "but not raw assistant text or serialized request bodies. Those fields are "
            "explicitly unavailable; reconstructed requests are not mislabeled as logs."
        ),
        "registered_manifest": manifest,
        "active_config": active_config,
        "cases": archived_cases,
    })
    atomic(OUTPUT_DIR / "deterministic_replay_v6.json", {
        "format": "socialflux_saved_appraisal_v6_replay_v1",
        "created_at_utc": created,
        "network_requests": 0,
        "thresholds_or_budgets_changed": False,
        "cases": replay_cases,
        "scenario_003_trust_proof": next(
            case for case in replay_cases if case["pair_id"] == "trust_gpt003"
        ),
    })
    print(json.dumps({
        "baseline_archive": str(OUTPUT_DIR / "baseline_archive.json"),
        "replay": str(OUTPUT_DIR / "deterministic_replay_v6.json"),
        "scenario_003_trust_selected": next(
            case["target_selected"] for case in replay_cases
            if case["pair_id"] == "trust_gpt003"
        ),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
