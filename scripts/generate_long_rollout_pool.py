#!/usr/bin/env python3
"""Generate a natural-ending rollout pool capped at 20 turns.

Unlike ``scripts.run_pipeline``, this command never clears an existing bundle.
Every accepted trajectory is written immediately, rejected attempts are retained
under ``rejected/``, and ``--resume`` verifies artifacts before skipping slots.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.instance_quality import audit_trajectory
from evaluation.quality_gates import audit_scenario_gate
from evaluation.review_registry import load_review_registry
from evaluation.rollout_gate import audit_rollout
from evaluation.state_v3_metrics import state_v3_trajectory_metrics
from environment.state_transition_contract import STATE_TRANSITION_STANDARD_V3
from pipeline.artifacts import write_dialogues
from pipeline.constants import ROLLOUT_CONFIG, SCENARIO_ROOT
from pipeline.runtime import (
    assert_development_role_partitioned_rollout_config,
    assert_fable_rollout_config,
    assert_single_model_rollout_config,
    build_environment_factory,
    build_policy,
    iter_policy_specs,
)
from pipeline.scenarios import (
    load_scenario_records,
    require_human_frozen,
    select_scenario_records,
)
from rollout.logger import TrajectoryLogger
from rollout.manifest import write_manifest
from rollout.runner import RolloutRunner
from rollout.configuration import load_rollout_config, public_rollout_config
from schemas.validate import validate_trajectory


MAX_TURNS = 20
MIN_MAIN_TURNS = 10
MAX_REQUESTS_PER_TURN = 18
# Compatibility alias; the contract is a maximum, not an exact target.
TARGET_TURNS = MAX_TURNS
QUALITY_VERSION = "socialflux_semantic_events_state_v3_v1"
_QUALITY_INPUTS = (
    "configs/model_routes.frontier_api.json",
    "environment/appraisal.py",
    "environment/appraisal_normalization.py",
    "environment/calibration.py",
    "environment/env.py",
    "environment/interaction_ledger.py",
    "environment/ledger_events.py",
    "environment/longitudinal.py",
    "environment/observation.py",
    "environment/public_situation.py",
    "environment/response_generator.py",
    "environment/response_validation.py",
    "environment/state_updater.py",
    "environment/state_ontology.py",
    "environment/state_opportunity.py",
    "environment/state_transition_contract.py",
    "environment/factory.py",
    "pipeline/runtime.py",
    "policies/model_policy.py",
    "policies/action_validation.py",
    "providers/anthropic.py",
    "providers/structured.py",
    "providers/text.py",
    "rollout/runner.py",
    "rollout/configuration.py",
    "prompts/loader.py",
    "prompts/manifest.json",
    "prompts/retired.json",
    "prompts/environment_state_appraisal_v1_per_variable.md",
    "prompts/environment_state_appraisal_v6_observed_evidence.md",
    "prompts/environment_interaction_appraisal_v1.md",
    "prompts/state_actor_binding_v1.txt",
    "prompts/interaction_schema_bound_v1.txt",
    "prompts/environment_response_v25.md",
    "prompts/environment_response_v31_contrastive_event_driven.md",
    "prompts/task_t4_action_v21.md",
    "prompts/task_rollout_action_v1.md",
    "prompts/task_rollout_action_v2_decision_continuity.md",
    "prompts/environment_appraisal_v11.md",
    "prompts/environment_appraisal_v12.md",
    "prompts/environment_appraisal_v22_slow_first.md",
    "prompts/environment_appraisal_v36_evidence_grounded_state_interpretation.md",
    "evaluation/instance_quality.py",
    "evaluation/rollout_gate.py",
    "evaluation/state_v3_metrics.py",
)


def _quality_fingerprint():
    digest = hashlib.sha256()
    project_root = Path(__file__).resolve().parents[1]
    for relative in _QUALITY_INPUTS:
        path = project_root / relative
        digest.update(relative.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _scenario_fingerprint(scenario):
    """Pin a trajectory to the exact canonical scenario content it used."""
    payload = json.dumps(
        scenario, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def planned_slots(records, config, *, policy_ids=None):
    """Return deterministic scenario/policy slots for a configured batch."""
    allowed = set(policy_ids or [])
    slots = []
    expanded = list(iter_policy_specs(config))
    expanded.sort(key=lambda item: (
        item[1], config["policies"].index(item[0])
    ))
    for scenario_path, scenario in records:
        for spec, run_index in expanded:
            policy = build_policy(spec, run_index)
            if allowed and policy.policy_id not in allowed:
                continue
            slots.append({
                "slot_id": f"{scenario['scenario_id']}::{policy.policy_id}",
                "scenario_id": scenario["scenario_id"],
                "scenario_directory": scenario_path.parent.name,
                "planned_policy_id": policy.policy_id,
                "spec": spec,
                "run_index": run_index,
            })
    return slots


def _atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _new_progress(
    config_path, output, slots, config, *, retain_all_candidates=False,
):
    return {
        "format": "socialflux_long_rollout_progress_v1",
        "created_at_utc": _utc_now(),
        "updated_at_utc": _utc_now(),
        "status": "in_progress",
        "config_path": str(Path(config_path)),
        "config_sha256": _sha256(config_path),
        "model_routes_sha256": (
            config.get("model_routes_provenance") or {}
        ).get("sha256"),
        "quality_version": QUALITY_VERSION,
        "quality_fingerprint": _quality_fingerprint(),
        "output_root": str(Path(output)),
        "admission_mode": (
            "human_postfilter"
            if retain_all_candidates
            else "machine_precheck"
        ),
        "max_turns": MAX_TURNS,
        "horizon_contract": "natural_end_at_or_before_max",
        "expected_slot_count": len(slots),
        "completed_slot_count": 0,
        "completed_slots": {},
        "attempts": [],
        "quality_summary": {
            "version": QUALITY_VERSION,
            "attempt_count": 0,
            "accepted_attempt_count": 0,
            "attempt_pass_rate": 0.0,
            "residual_reasons": {},
        },
    }


def _load_progress(
    path,
    config_path,
    slots,
    config,
    *,
    retain_all_candidates=False,
    allow_config_migration=False,
    allow_route_migration=False,
    allow_quality_migration=False,
):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("format") != "socialflux_long_rollout_progress_v1":
        raise ValueError("unsupported long-rollout progress format")
    current_config_sha256 = _sha256(config_path)
    if value.get("config_sha256") != current_config_sha256:
        if not allow_config_migration:
            raise ValueError(
                "rollout config changed; use a new output directory or "
                "--allow-config-migration"
            )
        value.setdefault("config_migration_history", []).append({
            "migrated_at_utc": _utc_now(),
            "from_sha256": value.get("config_sha256"),
            "to_sha256": current_config_sha256,
            "reason": "explicit_rollout_contract_migration",
        })
        value["config_sha256"] = current_config_sha256
        value["updated_at_utc"] = _utc_now()
        _atomic_json(path, value)
    current_routes_sha256 = (
        config.get("model_routes_provenance") or {}
    ).get("sha256")
    previous_routes_sha256 = value.get("model_routes_sha256")
    if previous_routes_sha256 != current_routes_sha256:
        if not allow_route_migration:
            raise ValueError(
                "model routes changed; use a new output directory or "
                "--allow-route-migration"
            )
        value.setdefault("model_route_history", []).append({
            "migrated_at_utc": _utc_now(),
            "from_sha256": previous_routes_sha256,
            "to_sha256": current_routes_sha256,
            "reason": "explicit_endpoint_protocol_migration",
        })
        value["model_routes_sha256"] = current_routes_sha256
        value["updated_at_utc"] = _utc_now()
        _atomic_json(path, value)
    if value.get("max_turns") != MAX_TURNS:
        raise ValueError("progress file does not use the natural max-20 contract")
    expected_admission = (
        "human_postfilter" if retain_all_candidates else "machine_precheck"
    )
    if value.get("admission_mode", "machine_precheck") != expected_admission:
        raise ValueError(
            "rollout admission mode changed; use a new output directory"
        )
    current_quality_fingerprint = _quality_fingerprint()
    if (
        value.get("quality_version") != QUALITY_VERSION
        or value.get("quality_fingerprint") != current_quality_fingerprint
    ):
        if not allow_quality_migration:
            raise ValueError(
                "R3 quality implementation changed; preserve this evidence and "
                "use a new versioned output directory or "
                "--allow-quality-migration"
            )
        value.setdefault("quality_migration_history", []).append({
            "migrated_at_utc": _utc_now(),
            "from_version": value.get("quality_version"),
            "from_fingerprint": value.get("quality_fingerprint"),
            "to_version": QUALITY_VERSION,
            "to_fingerprint": current_quality_fingerprint,
            "reason": "explicit_runtime_bugfix_migration",
        })
        value["quality_version"] = QUALITY_VERSION
        value["quality_fingerprint"] = current_quality_fingerprint
        value["updated_at_utc"] = _utc_now()
        _atomic_json(path, value)
    expected = {slot["slot_id"] for slot in slots}
    unknown = set(value.get("completed_slots", {})) - expected
    if unknown:
        raise ValueError(f"progress contains slots outside this run: {sorted(unknown)}")
    previous_expected = value.get("expected_slot_count")
    if previous_expected != len(expected):
        if (
            not isinstance(previous_expected, int)
            or isinstance(previous_expected, bool)
            or previous_expected > len(expected)
        ):
            raise ValueError(
                "resume slot plan cannot shrink or replace the original batch"
            )
        value.setdefault("slot_plan_history", []).append({
            "expanded_at_utc": _utc_now(),
            "from_expected_slot_count": previous_expected,
            "to_expected_slot_count": len(expected),
            "reason": "newly_completed_scenario_added_to_batch",
        })
        value["expected_slot_count"] = len(expected)
        value["updated_at_utc"] = _utc_now()
        _atomic_json(path, value)
    return value


def _candidate_classification(turn_count, ending, checks):
    if ending.get("reason") == "natural_completion" and turn_count < MIN_MAIN_TURNS:
        return "short_natural_trajectory"
    if ending.get("reason") == "max_turns" and turn_count == MAX_TURNS:
        return "budget_truncated"
    if all(checks.values()):
        return "main_candidate"
    return "machine_rejected"


def _machine_precheck(trajectory):
    validate_trajectory(trajectory)
    structural = audit_trajectory(trajectory)
    gate = audit_rollout(trajectory)
    ending = trajectory.get("ending") or {}
    turns = trajectory.get("turns", [])
    turn_count = len(turns)
    expected_ids = [f"t{index}" for index in range(1, turn_count + 1)]
    checks = {
        "turn_count_in_main_10_to_20_window": MIN_MAIN_TURNS <= turn_count <= MAX_TURNS,
        "contiguous_turn_ids": [
            item.get("turn_id") for item in turns
        ] == expected_ids,
        "natural_ending_matches_actual_last_turn": (
            ending.get("turn_id") == turn_count
            and ending.get("reason") == "natural_completion"
        ),
        "structural_quality": structural["passed"],
        "no_machine_hard_reject": not gate["hard_reject_reasons"],
    }
    state_transition_standard = (
        trajectory.get("environment_provenance") or {}
    ).get("state_transition_standard")
    state_v3 = None
    if state_transition_standard == STATE_TRANSITION_STANDARD_V3:
        state_v3 = state_v3_trajectory_metrics(trajectory)
        checks["state_v3_update_integrity"] = (
            state_v3["state_update_integrity_passed"]
        )
        # Coverage remains reported in state_v3_metrics but is not correctness.
    classification = _candidate_classification(turn_count, ending, checks)
    return {
        "passed": all(checks.values()),
        "candidate_classification": classification,
        "checks": checks,
        "structural": structural,
        "hard_reject_reasons": gate["hard_reject_reasons"],
        "state_transition_standard": state_transition_standard,
        "state_v3_metrics": state_v3,
        "evidence_status": "pending_judge_history_and_human_review",
    }


def _attempt_offset(progress, slot_id):
    attempts = [
        int(item.get("attempt", 0))
        for item in progress.get("attempts", [])
        if item.get("slot_id") == slot_id and isinstance(item.get("attempt"), int)
    ]
    return max(attempts, default=0)


def _generation_error_retry_allowed(progress, slot_id):
    attempts = [
        item for item in progress.get("attempts", [])
        if item.get("slot_id") == slot_id
    ]
    return bool(
        attempts
        and attempts[-1].get("status") == "generation_error"
        and not any(item.get("technical_retry") is True for item in attempts)
    )


def _attempts_end_in_provider_overload(attempts):
    if not attempts:
        return False
    latest = attempts[-1]
    message = str(latest.get("error", "")).lower()
    return (
        latest.get("status") == "generation_error"
        and ("http 429" in message or "overloaded" in message)
    )


def _retry_filter_matches(progress, slot_id, error_types):
    """Select only the latest failed slots named by an explicit retry filter."""
    if not error_types:
        return True
    attempts = [
        item for item in progress.get("attempts", [])
        if item.get("slot_id") == slot_id
    ]
    if not attempts:
        return False
    latest = attempts[-1]
    return (
        latest.get("status") == "generation_error"
        and latest.get("error_type") in set(error_types)
    )


def _technical_retry_allowed(
    progress, slot_id, *, retry_generation_errors_once=False, error_types=None,
):
    """Allow only explicitly requested retries of persisted generation errors."""
    if error_types:
        return _retry_filter_matches(progress, slot_id, error_types)
    return bool(
        retry_generation_errors_once
        and _generation_error_retry_allowed(progress, slot_id)
    )


def _quality_rejection_retry_allowed(progress, slot_id):
    """Allow one replacement sample after the latest machine quality rejection."""
    attempts = [
        item for item in progress.get("attempts", [])
        if item.get("slot_id") == slot_id
    ]
    return bool(
        attempts
        and attempts[-1].get("status") == "machine_rejected"
        and not any(item.get("quality_retry") is True for item in attempts)
    )


def _unattempted_filter_matches(progress, slot_id):
    """Select slots that have never produced a persisted attempt."""
    return not any(
        item.get("slot_id") == slot_id
        for item in progress.get("attempts", [])
    )


def _update_quality_summary(progress):
    attempts = progress.get("attempts", [])
    accepted = sum(item.get("status") == "accepted" for item in attempts)
    residual = {}
    for item in attempts:
        if item.get("status") == "accepted":
            continue
        reasons = []
        reasons.extend(item.get("precheck", {}).get("hard_reject_reasons", []))
        if item.get("error"):
            reasons.append(item["error"])
        for reason in reasons or [item.get("status", "unknown")]:
            key = str(reason)
            residual[key] = residual.get(key, 0) + 1
    metrics = [
        item.get("provider_run_metrics") or {}
        for item in attempts
    ]
    usage_keys = {
        key
        for item in metrics
        for key in (item.get("totals", {}).get("usage", {}) or {})
    }
    progress["quality_summary"] = {
        "version": QUALITY_VERSION,
        "attempt_count": len(attempts),
        "accepted_attempt_count": accepted,
        "attempt_pass_rate": round(accepted / len(attempts), 4) if attempts else 0.0,
        "residual_reasons": dict(sorted(
            residual.items(), key=lambda item: (-item[1], item[0])
        )),
        "actual_requests_including_retries": sum(
            int((item.get("actual_request_counts") or {}).get("total") or 0)
            for item in attempts
        ),
        "provider_failed_requests": sum(
            int(item.get("totals", {}).get("failed_request_count", 0) or 0)
            for item in metrics
        ),
        "provider_request_duration_seconds": round(sum(
            float(item.get("totals", {}).get("request_duration_seconds", 0.0) or 0.0)
            for item in metrics
        ), 3),
        "provider_usage": {
            key: sum(
                int(item.get("totals", {}).get("usage", {}).get(key, 0) or 0)
                for item in metrics
            )
            for key in sorted(usage_keys)
        },
    }


def _replacement_spec(spec, attempt_index):
    replacement = deepcopy(spec)
    if attempt_index:
        replacement["policy_id"] = (
            f"{spec['policy_id']}__replacement_{attempt_index + 1}"
        )
        sampling = replacement.setdefault("sampling", {})
        if isinstance(sampling.get("seed"), int):
            sampling["seed"] += attempt_index * 1_000_003
    return replacement


def _accepted_trajectories(scenario_dir, progress, scenario_id):
    trajectories = []
    for slot_id, record in progress.get("completed_slots", {}).items():
        if record.get("scenario_id") != scenario_id:
            continue
        path = scenario_dir / record["trajectory_file"]
        trajectory = json.loads(path.read_text(encoding="utf-8"))
        if (
            progress.get("admission_mode") != "human_postfilter"
            and not _machine_precheck(trajectory)["passed"]
        ):
            raise ValueError(f"completed slot artifact no longer passes: {slot_id}")
        trajectories.append(trajectory)
    trajectories.sort(key=lambda item: item.get("batch_slot_id", ""))
    return trajectories


def _refresh_scenario_bundle(output, scenario, directory_name, progress, config):
    scenario_dir = Path(output) / directory_name
    trajectories = _accepted_trajectories(
        scenario_dir, progress, scenario["scenario_id"]
    )
    write_dialogues(scenario_dir / "dialogues.md", scenario, trajectories)
    write_manifest(
        scenario_dir / "manifest.json",
        trajectories,
        {
            "origin": "free_form_model_interaction",
            "pool_stage": config.get("pool_stage", "development"),
            "rollout_config": public_rollout_config(config),
            "max_turns": MAX_TURNS,
            "horizon_contract": "natural_end_at_or_before_max",
            "generation_status": "in_progress",
            "progress_file": "../progress.json",
            "dialogues": "dialogues.md",
            "task_review": None,
            "quality_version": QUALITY_VERSION,
            "quality_fingerprint": _quality_fingerprint(),
            "scenario_fingerprint": _scenario_fingerprint(scenario),
        },
    )


def _verify_completed_slot(output, slot, record):
    path = Path(output) / slot["scenario_directory"] / record["trajectory_file"]
    if not path.exists():
        raise ValueError(f"completed trajectory is missing: {path}")
    trajectory = json.loads(path.read_text(encoding="utf-8"))
    if trajectory.get("batch_slot_id") != slot["slot_id"]:
        raise ValueError(f"completed trajectory slot mismatch: {path}")
    result = _machine_precheck(trajectory)
    if (
        record.get("admission") != "human_postfilter"
        and not result["passed"]
    ):
        raise ValueError(f"completed trajectory failed resume verification: {path}")


def run_slot(
    slot, scenario, output, retry_limit, attempt_offset=0,
    retain_all_candidates=False, technical_retry=False, quality_retry=False,
):
    if (
        slot["config"].get("candidate_strategy") == "single_first_pass"
        and attempt_offset > 0
        and not (technical_retry or quality_retry)
    ):
        return None, []
    scenario_dir = Path(output) / slot["scenario_directory"]
    scenario_dir.mkdir(parents=True, exist_ok=True)
    environment_factory = build_environment_factory(scenario, slot["config"]["environment"])
    attempt_records = []
    for local_attempt_index in range(retry_limit):
        attempt_number = attempt_offset + local_attempt_index + 1
        replacement = (
            deepcopy(slot["spec"])
            if technical_retry
            else _replacement_spec(slot["spec"], attempt_number - 1)
        )
        policy = build_policy(replacement, slot["run_index"])
        started = _utc_now()
        checkpoint_path = (
            scenario_dir / "in_progress"
            / f"{policy.policy_id}__attempt_{attempt_number}.json"
        )

        def write_checkpoint(snapshot):
            snapshot["batch_slot_id"] = slot["slot_id"]
            snapshot["planned_policy_id"] = slot["planned_policy_id"]
            snapshot["generation_attempt"] = attempt_number
            snapshot["quality_version"] = QUALITY_VERSION
            snapshot["quality_fingerprint"] = _quality_fingerprint()
            snapshot["scenario_fingerprint"] = _scenario_fingerprint(scenario)
            snapshot["checkpoint_updated_at_utc"] = _utc_now()
            _atomic_json(checkpoint_path, snapshot)

        try:
            trajectory = RolloutRunner(
                environment_factory,
                checkpoint_writer=write_checkpoint,
            ).run(
                policy, max_turns=MAX_TURNS
            )
            trajectory["batch_slot_id"] = slot["slot_id"]
            trajectory["planned_policy_id"] = slot["planned_policy_id"]
            trajectory["generation_attempt"] = attempt_number
            trajectory["quality_version"] = QUALITY_VERSION
            trajectory["quality_fingerprint"] = _quality_fingerprint()
            trajectory["scenario_fingerprint"] = _scenario_fingerprint(scenario)
            precheck = _machine_precheck(trajectory)
            classification = precheck["candidate_classification"]
            archive_directory = {
                "short_natural_trajectory": "short_trajectories",
                "budget_truncated": "budget_truncated",
            }.get(classification, "rejected")
            target_logger = TrajectoryLogger(
                scenario_dir
                if precheck["passed"] or retain_all_candidates
                else scenario_dir / archive_directory
            )
            path = target_logger.write(trajectory)
            attempt_record = {
                "slot_id": slot["slot_id"],
                "scenario_id": slot["scenario_id"],
                "planned_policy_id": slot["planned_policy_id"],
                "actual_policy_id": policy.policy_id,
                "attempt": attempt_number,
                "technical_retry": technical_retry,
                "quality_retry": quality_retry,
                "quality_version": QUALITY_VERSION,
                "quality_fingerprint": _quality_fingerprint(),
                "scenario_fingerprint": _scenario_fingerprint(scenario),
                "started_at_utc": started,
                "finished_at_utc": _utc_now(),
                "status": "accepted" if precheck["passed"] else classification,
                "trajectory_id": trajectory["trajectory_id"],
                "trajectory_file": path.name,
                "precheck": precheck,
                "actual_request_counts": deepcopy(
                    trajectory.get("actual_request_counts", {})
                ),
                "provider_run_metrics": deepcopy(
                    trajectory.get("provider_run_metrics", {})
                ),
                "admission": (
                    "machine_precheck"
                    if precheck["passed"]
                    else (
                        "human_postfilter"
                        if retain_all_candidates
                        else "rejected"
                    )
                ),
                "checkpoint_file": str(checkpoint_path.relative_to(scenario_dir)),
            }
            attempt_records.append(attempt_record)
            if precheck["passed"] or retain_all_candidates:
                return trajectory, attempt_records
        except Exception as exc:  # preserve evidence and continue replacement sampling
            partial = getattr(exc, "partial_trajectory", None)
            partial_path = None
            if partial is not None:
                partial["batch_slot_id"] = slot["slot_id"]
                partial["planned_policy_id"] = slot["planned_policy_id"]
                partial["generation_attempt"] = attempt_number
                partial["quality_version"] = QUALITY_VERSION
                partial["quality_fingerprint"] = _quality_fingerprint()
                partial["scenario_fingerprint"] = _scenario_fingerprint(scenario)
                partial_path = TrajectoryLogger(
                    scenario_dir / "rejected"
                ).write(partial)
            attempt_records.append({
                "slot_id": slot["slot_id"],
                "scenario_id": slot["scenario_id"],
                "planned_policy_id": slot["planned_policy_id"],
                "actual_policy_id": policy.policy_id,
                "attempt": attempt_number,
                "technical_retry": technical_retry,
                "quality_retry": quality_retry,
                "quality_version": QUALITY_VERSION,
                "quality_fingerprint": _quality_fingerprint(),
                "scenario_fingerprint": _scenario_fingerprint(scenario),
                "started_at_utc": started,
                "finished_at_utc": _utc_now(),
                "status": "generation_error",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "error_diagnostics": getattr(exc, "diagnostics", []),
                "partial_trajectory_id": (
                    partial.get("trajectory_id") if partial is not None else None
                ),
                "partial_trajectory_file": (
                    partial_path.name if partial_path is not None else None
                ),
                "completed_turns_before_error": (
                    len(partial.get("turns", [])) if partial is not None else 0
                ),
                "actual_request_counts": deepcopy(
                    (partial or {}).get("actual_request_counts", {})
                ),
                "provider_run_metrics": deepcopy(
                    (partial or {}).get("provider_run_metrics", {})
                ),
                "checkpoint_file": str(checkpoint_path.relative_to(scenario_dir)),
            })
    return None, attempt_records


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pipeline rollout")
    parser.add_argument("--rollout-config", type=Path, default=ROLLOUT_CONFIG)
    parser.add_argument("--scenarios", type=Path, default=SCENARIO_ROOT)
    parser.add_argument("--scenario-id", action="append")
    parser.add_argument("--policy-id", action="append")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--retry-limit", type=int, default=3)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--max-slots", type=int)
    parser.add_argument("--request-budget", type=int, default=150000)
    parser.add_argument("--resume", action="store_true")
    resume_filter = parser.add_mutually_exclusive_group()
    resume_filter.add_argument(
        "--retry-error-type",
        action="append",
        help=(
            "on resume, retry only incomplete slots whose latest attempt has "
            "this error type; repeat the option to allow more types"
        ),
    )
    resume_filter.add_argument(
        "--unattempted-only",
        action="store_true",
        help="on resume, process only slots with no persisted attempt",
    )
    resume_filter.add_argument(
        "--retry-generation-errors-once",
        action="store_true",
        help=(
            "on resume, retry each incomplete generation_error slot once with "
            "the original policy id and seed; accepted or quality-rejected "
            "trajectories are never retried"
        ),
    )
    resume_filter.add_argument(
        "--retry-quality-rejections-once",
        action="store_true",
        help=(
            "on resume, generate one replacement candidate only for slots whose "
            "latest attempt is machine_rejected; prior evidence is preserved"
        ),
    )
    parser.add_argument("--allow-route-migration", action="store_true")
    parser.add_argument("--allow-config-migration", action="store_true")
    parser.add_argument("--allow-quality-migration", action="store_true")
    parser.add_argument(
        "--stop-after-consecutive-provider-overloads",
        type=int,
        default=0,
        help=(
            "with one worker, pause the batch after this many consecutive "
            "HTTP 429/overloaded generation errors; zero disables the guard"
        ),
    )
    parser.add_argument(
        "--revalidate-completed",
        action="store_true",
        help="Move completed artifacts that fail current checks to rejected/ and refill them.",
    )
    parser.add_argument("--allow-unreviewed", action="store_true")
    parser.add_argument(
        "--retain-all-candidates",
        action="store_true",
        help=(
            "Retain every schema-valid rollout for later human filtering. "
            "Machine prechecks remain recorded but do not block downstream work."
        ),
    )
    parser.add_argument(
        "--experimental-model",
        help=(
            "explicit one-trajectory development model; requires "
            "candidate_strategy=single_first_pass and --retry-limit 1"
        ),
    )
    parser.add_argument(
        "--development-role-partition",
        action="store_true",
        help=(
            "development-only GPT policy/tasks with Claude appraisal/response; "
            "requires one first-pass rollout and --retry-limit 1"
        ),
    )
    parser.add_argument(
        "--review-registry",
        type=Path,
        help="Human-signed Gate 1 registry; required for production rollout.",
    )
    args = parser.parse_args(argv)

    if args.retry_limit < 1:
        raise ValueError("--retry-limit must be positive")
    if not 1 <= args.workers <= 8:
        raise ValueError("--workers must be between 1 and 8")
    if args.stop_after_consecutive_provider_overloads < 0:
        raise ValueError(
            "--stop-after-consecutive-provider-overloads cannot be negative"
        )
    if args.stop_after_consecutive_provider_overloads and args.workers != 1:
        raise ValueError(
            "provider-overload guard requires --workers 1 for deterministic pausing"
        )
    config = load_rollout_config(args.rollout_config)
    if (
        config.get("candidate_strategy") == "single_first_pass"
        and args.retry_limit != 1
    ):
        raise ValueError(
            "single_first_pass forbids replacement sampling; use --retry-limit 1"
        )
    if args.experimental_model and args.development_role_partition:
        raise ValueError(
            "choose either --experimental-model or --development-role-partition"
        )
    if args.experimental_model:
        if config.get("pool_stage") != "development":
            raise ValueError("experimental single rollout must use development stage")
        if config.get("candidate_strategy") != "single_first_pass":
            raise ValueError(
                "experimental single rollout requires single_first_pass strategy"
            )
        assert_single_model_rollout_config(
            config,
            expected_model=args.experimental_model,
            expected_seed_slots=1,
            context="experimental single-trajectory",
        )
    elif args.development_role_partition:
        if config.get("pool_stage") != "development":
            raise ValueError("role-partitioned audit must use development stage")
        if config.get("candidate_strategy") != "single_first_pass":
            raise ValueError(
                "role-partitioned audit requires single_first_pass strategy"
            )
        if args.retry_limit != 1:
            raise ValueError(
                "role-partitioned audit forbids replacement sampling"
            )
        assert_development_role_partitioned_rollout_config(config)
    else:
        assert_fable_rollout_config(config)
    if config.get("pilot_limits", {}).get("rollout_turns") != MAX_TURNS:
        raise ValueError("long rollout batch requires a maximum of 20 turns")
    if config.get("environment", {}).get("horizon_mode") != "natural_max_20":
        raise ValueError("formal rollout environment must use natural_max_20")
    if any(spec.get("horizon_mode") != "natural_max_20" for spec in config["policies"]):
        raise ValueError("formal rollout policies must use natural_max_20")
    records = select_scenario_records(
        load_scenario_records(args.scenarios), args.scenario_id
    )
    if not args.allow_unreviewed and args.review_registry is None:
        raise ValueError("production rollout requires --review-registry")
    registry = (
        load_review_registry(args.review_registry)
        if args.review_registry is not None else None
    )
    for scenario_path, scenario in records:
        require_human_frozen(scenario, allow_unreviewed=args.allow_unreviewed)
        if not args.allow_unreviewed:
            gate = audit_scenario_gate(scenario, scenario_path, registry)
            if not gate["passed"]:
                raise ValueError(
                    f"Gate 1 has not passed for {scenario['scenario_id']}"
                )
    slots = planned_slots(records, config, policy_ids=args.policy_id)
    if args.max_slots is not None:
        if args.max_slots < 1:
            raise ValueError("--max-slots must be positive")
        slots = slots[:args.max_slots]
    if not slots:
        raise ValueError("no rollout slots selected")
    for slot in slots:
        slot["config"] = config

    args.output.mkdir(parents=True, exist_ok=True)
    progress_path = args.output / "progress.json"
    if progress_path.exists():
        if not args.resume:
            raise ValueError("output has progress.json; pass --resume to continue safely")
        progress = _load_progress(
            progress_path, args.rollout_config, slots, config,
            retain_all_candidates=args.retain_all_candidates,
            allow_config_migration=args.allow_config_migration,
            allow_route_migration=args.allow_route_migration,
            allow_quality_migration=args.allow_quality_migration,
        )
    else:
        progress = _new_progress(
            args.rollout_config, args.output, slots, config,
            retain_all_candidates=args.retain_all_candidates,
        )
        _atomic_json(progress_path, progress)

    scenarios = {scenario["scenario_id"]: scenario for _, scenario in records}
    completed = progress["completed_slots"]
    pending = []
    revalidated_scenarios = set()
    for index, slot in enumerate(slots, start=1):
        if slot["slot_id"] in completed:
            try:
                _verify_completed_slot(
                    args.output, slot, completed[slot["slot_id"]]
                )
                print(f"[{index}/{len(slots)}] resume {slot['slot_id']}", flush=True)
                continue
            except ValueError as exc:
                if not args.revalidate_completed:
                    raise
                record = completed.pop(slot["slot_id"])
                source = (
                    args.output / slot["scenario_directory"] / record["trajectory_file"]
                )
                rejected_dir = args.output / slot["scenario_directory"] / "rejected"
                rejected_dir.mkdir(parents=True, exist_ok=True)
                target = rejected_dir / record["trajectory_file"]
                if source.exists():
                    os.replace(source, target)
                progress["attempts"].append({
                    "slot_id": slot["slot_id"],
                    "scenario_id": slot["scenario_id"],
                    "planned_policy_id": slot["planned_policy_id"],
                    "actual_policy_id": record.get("actual_policy_id"),
                    "status": "revalidation_rejected",
                    "finished_at_utc": _utc_now(),
                    "trajectory_id": record.get("trajectory_id"),
                    "trajectory_file": target.name,
                    "error": str(exc),
                })
                revalidated_scenarios.add(slot["scenario_id"])
                print(
                    f"[{index}/{len(slots)}] revalidation rejected "
                    f"{slot['slot_id']}",
                    flush=True,
                )
        technical_retry = _technical_retry_allowed(
            progress,
            slot["slot_id"],
            retry_generation_errors_once=args.retry_generation_errors_once,
            error_types=args.retry_error_type,
        )
        quality_retry = bool(
            args.retry_quality_rejections_once
            and _quality_rejection_retry_allowed(progress, slot["slot_id"])
        )
        if (
            config.get("candidate_strategy") == "single_first_pass"
            and _attempt_offset(progress, slot["slot_id"]) > 0
            and not (technical_retry or quality_retry)
        ):
            print(
                f"[{index}/{len(slots)}] retain exhausted first pass "
                f"{slot['slot_id']}",
                flush=True,
            )
            continue
        if args.unattempted_only and not _unattempted_filter_matches(
            progress, slot["slot_id"]
        ):
            print(
                "[{}/{}] skip previously attempted {}".format(
                    index, len(slots), slot["slot_id"]
                ),
                flush=True,
            )
            continue
        if not _retry_filter_matches(
            progress, slot["slot_id"], args.retry_error_type
        ):
            print(
                "[{}/{}] skip retry filter {}".format(
                    index, len(slots), slot["slot_id"]
                ),
                flush=True,
            )
            continue
        if args.retry_generation_errors_once and not technical_retry:
            print(
                f"[{index}/{len(slots)}] skip non-generation-error "
                f"{slot['slot_id']}",
                flush=True,
            )
            continue
        if args.retry_quality_rejections_once and not quality_retry:
            print(
                f"[{index}/{len(slots)}] skip non-quality-rejection "
                f"{slot['slot_id']}",
                flush=True,
            )
            continue
        pending.append((index, slot, technical_retry, quality_retry))

    retry_ceiling = (
        len(pending)
        * args.retry_limit
        * MAX_TURNS
        * MAX_REQUESTS_PER_TURN
    )
    if retry_ceiling > args.request_budget:
        raise ValueError(
            f"retry ceiling {retry_ceiling} exceeds request budget "
            f"{args.request_budget}"
        )
    progress["request_budget"] = args.request_budget
    progress["retry_request_ceiling"] = retry_ceiling

    if revalidated_scenarios:
        progress["completed_slot_count"] = len(completed)
        progress["updated_at_utc"] = _utc_now()
        progress["status"] = "in_progress"
        _atomic_json(progress_path, progress)
        for scenario_path, scenario in records:
            if scenario["scenario_id"] in revalidated_scenarios:
                _refresh_scenario_bundle(
                    args.output,
                    scenario,
                    scenario_path.parent.name,
                    progress,
                    config,
                )

    def record_result(index, slot, trajectory, attempts):
        progress["attempts"].extend(attempts)
        _update_quality_summary(progress)
        if trajectory is not None:
            final_attempt = attempts[-1]
            completed[slot["slot_id"]] = {
                "scenario_id": slot["scenario_id"],
                "planned_policy_id": slot["planned_policy_id"],
                "actual_policy_id": trajectory["policy_id"],
                "trajectory_id": trajectory["trajectory_id"],
                "trajectory_file": f"{trajectory['trajectory_id']}.json",
                "turn_count": len(trajectory["turns"]),
                "scenario_fingerprint": trajectory["scenario_fingerprint"],
                "accepted_at_utc": _utc_now(),
                "admission": final_attempt.get("admission"),
                "machine_precheck_passed": bool(
                    final_attempt.get("precheck", {}).get("passed")
                ),
            }
            _refresh_scenario_bundle(
                args.output,
                scenarios[slot["scenario_id"]],
                slot["scenario_directory"],
                progress,
                config,
            )
            outcome = (
                "accepted"
                if final_attempt.get("precheck", {}).get("passed")
                else "retained for human review"
            )
        else:
            outcome = "exhausted retries"
        progress["completed_slot_count"] = len(completed)
        progress["updated_at_utc"] = _utc_now()
        progress["status"] = "in_progress"
        _atomic_json(progress_path, progress)
        print(
            f"[{index}/{len(slots)}] {outcome} {slot['slot_id']} "
            f"({len(completed)}/{len(slots)} complete)",
            flush=True,
        )

    paused_for_provider_overload = False
    if args.workers == 1:
        consecutive_provider_overloads = 0
        for index, slot, technical_retry, quality_retry in pending:
            print(f"[{index}/{len(slots)}] generate {slot['slot_id']}", flush=True)
            trajectory, attempts = run_slot(
                slot,
                scenarios[slot["scenario_id"]],
                args.output,
                args.retry_limit,
                _attempt_offset(progress, slot["slot_id"]),
                args.retain_all_candidates,
                technical_retry,
                quality_retry,
            )
            record_result(index, slot, trajectory, attempts)
            if _attempts_end_in_provider_overload(attempts):
                consecutive_provider_overloads += 1
            else:
                consecutive_provider_overloads = 0
            if (
                args.stop_after_consecutive_provider_overloads
                and consecutive_provider_overloads
                >= args.stop_after_consecutive_provider_overloads
            ):
                paused_for_provider_overload = True
                progress["status"] = "paused_provider_overload"
                progress["provider_overload_pause"] = {
                    "paused_at_utc": _utc_now(),
                    "consecutive_errors": consecutive_provider_overloads,
                    "last_scenario_id": slot["scenario_id"],
                }
                _atomic_json(progress_path, progress)
                print(
                    "paused after consecutive provider overloads: "
                    f"{consecutive_provider_overloads}",
                    flush=True,
                )
                break
    else:
        print(
            f"starting {len(pending)} pending slots with {args.workers} workers",
            flush=True,
        )
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(
                    run_slot,
                    slot,
                    scenarios[slot["scenario_id"]],
                    args.output,
                    args.retry_limit,
                    _attempt_offset(progress, slot["slot_id"]),
                    args.retain_all_candidates,
                    technical_retry,
                    quality_retry,
                ): (index, slot)
                for index, slot, technical_retry, quality_retry in pending
            }
            for future in as_completed(futures):
                index, slot = futures[future]
                trajectory, attempts = future.result()
                record_result(index, slot, trajectory, attempts)

    progress["status"] = (
        "paused_provider_overload"
        if paused_for_provider_overload
        else (
            "completed"
            if len(completed) == len(slots)
            else "incomplete_retry_exhausted"
        )
    )
    progress["completed_slot_count"] = len(completed)
    progress["updated_at_utc"] = _utc_now()
    _update_quality_summary(progress)
    _atomic_json(progress_path, progress)
    for scenario_path, scenario in records:
        _refresh_scenario_bundle(
            args.output, scenario, scenario_path.parent.name, progress, config
        )
    print(json.dumps({
        "status": progress["status"],
        "completed": len(completed),
        "expected": len(slots),
        "max_turns": MAX_TURNS,
        "observed_turn_counts": sorted(
            record.get("turn_count")
            for record in completed.values()
            if isinstance(record.get("turn_count"), int)
        ),
        "progress": str(progress_path),
    }, ensure_ascii=False), flush=True)
    if progress["status"] != "completed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
