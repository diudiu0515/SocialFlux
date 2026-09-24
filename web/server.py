"""Read-only annotation visualizer for scenarios, rollouts, and tasks."""

import argparse
import base64
import hmac
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
from urllib.parse import unquote, urlparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from environment.observation import (
    PRIVATE_AUTHOR_FIELDS,
    PUBLIC_OBSERVATION_FIELDS,
    build_initial_policy_observation,
)
from evaluation.quality_gates import SCENARIO_CHECKS, TASK_REVIEW_RATINGS
from evaluation.rollout_gate import (
    HARD_REJECT_REASONS, QUALITY_DIMENSIONS, infer_observed_outcome,
)
from prompts.loader import get_prompt, render_prompt
from schemas.validate import validate_scenario
from scripts.scenario_docs import discover_scenario_paths

SCENARIO_DIR = ROOT / "configs" / "scenarios"
PIPELINE_DIR = ROOT / "build" / "pipeline_20turn_selected"
ACCEPTANCE_DIR = ROOT / "build" / "acceptance_v2"
STATIC_DIR = Path(__file__).resolve().parent / "static"
MEDIA_MANIFEST = ROOT / "media" / "talking_head" / "manifest.json"
SCREENING_REPORT = ROOT / "build" / "screening_report.json"
LONG_ROLLOUT_ROOT = ROOT / "build" / "rollouts"
# Historical model outputs are archived outside the active data path. New batches
# should be added explicitly through their own manifest instead of implicit globbing.
ROLLOUT_REVIEW_ROOTS = ()
SCENARIO_REVIEW_TEMPLATE = ROOT / "reviews" / "scenario_review_template.json"
ENVIRONMENT_REVIEW_TEMPLATE = ROOT / "reviews" / "environment_evidence_template.json"
FORMAL_ENVIRONMENT_DIR = ROOT / "data" / "formal" / "environment"
HUMAN_REVIEW_PLAN = ROOT / "configs" / "human_review_plan.json"
HUMAN_REVIEW_WORKSPACE = ROOT / "build" / "human_review_workspace.json"
TASK_REVIEW_SAMPLE = ROOT / "reviews" / "task_review_sample_template.json"
MACHINE_TASK_PROPOSALS = ROOT / "build" / "machine_task_proposals.json"
TASK_EXAMPLES = ROOT / "build" / "task_examples_v1" / "examples.json"
TASK_EXAMPLE_MEDIA_ROOT = ROOT / "media" / "task_examples"
QUALITY_GATE_REPORT = ROOT / "build" / "quality_gates" / "report.json"
R3_DIAGNOSTIC_REVIEW = (
    ROOT / "data" / "formal" / "environment" / "r3_current_diagnostic_review.json"
)
SCALE20_PILOT_REVIEW = ROOT / "build" / "scale20_v1" / "pilot_review.json"
SCALE20_FULL20_REVIEW = ROOT / "build" / "scale20_v1" / "full20_human_review.json"
SCALE20_V2_REVIEW = ROOT / "build" / "scale20_v2" / "review.json"
SCALE150_MATRIX = ROOT / "configs" / "scale300_v1" / "design_matrix.json"
GPT50_SCENARIO_ROOTS = (
    ROOT / "data" / "gpt50" / "experiment" / "scenario" / "scenarios",
    ROOT / "data" / "gpt50" / "scenario" / "scenarios",
    ROOT / "data" / "gpt50" / "scenarios",
)
GPT50_EXPECTED_SCENARIO_COUNT = 50
GPT50_MIN_GATE3_TURNS = 10
GPT50_ROLLOUT_ROOT = ROOT / "data" / "gpt50" / "experiment" / "rollouts"
GPT50_GATE2_ROOT = ROOT / "data" / "gpt50" / "experiment" / "gate2"
GPT50_GATE2_EXPERIMENTS = (
    ("E1", "state_transition_agreement.json", "状态转移方向一致性", "review_items"),
    ("E2", "trajectory_plausibility.json", "完整轨迹合理性", "review_items"),
    ("E3", "history_intervention.json", "历史干预敏感性", "records"),
    ("E4", "paraphrase_robustness.json", "释义鲁棒性", "records"),
    ("E5", "local_counterfactual.json", "局部反事实区分度", "records"),
    ("E6", "backbone_sensitivity.json", "双 backbone 敏感性", "records"),
    ("E7", "persona_intervention.json", "Persona 干预敏感性", "records"),
    ("E8", "video_state_consistency.json", "视频状态一致性", "review_items"),
    ("E9", "timescale_validity.json", "状态时间尺度有效性", "review_items"),
)
SCALE150_MODEL_REVIEW_FILES = ()
SCALE300_AUTOMATIC_GATE_AUDIT = ROOT / "build" / "scale300_v1" / "automatic_gate_audit.json"
# Switch to build/scale300_tasks only after its summary covers all 300 ordinals.
SCALE300_TASK_ROOT = ROOT / "build" / "scale300_tasks_v3"
T2_EXPRESSION_DEV_ROOT = ROOT / "build" / "t2_expression_dev_v1"
SCALE150_ROLLOUT_ROOTS = ()

def credentials_match(header, username, password):
    """Validate an HTTP Basic Authorization header without timing leaks."""
    if not header or not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
        supplied_username, supplied_password = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError):
        return False
    return hmac.compare_digest(supplied_username, username) and hmac.compare_digest(
        supplied_password, password
    )


def read_json(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path):
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_r3_diagnostic_review():
    """Load current R3 evidence without treating it as formal acceptance."""
    return read_json(R3_DIAGNOSTIC_REVIEW, {}) or {}


def _active_gpt50_scenario_root():
    """Select one GPT experiment batch without mixing checkpoints or versions."""
    for root in GPT50_SCENARIO_ROOTS:
        if discover_scenario_paths(root):
            return root
    return GPT50_SCENARIO_ROOTS[0]


def _display_path(path):
    try:
        return str(Path(path).relative_to(ROOT))
    except ValueError:
        return str(path)


def load_gpt50_rollout_progress():
    """Expose the resumable GPT rollout batch without implying human approval."""
    progress_path = GPT50_ROLLOUT_ROOT / "progress.json"
    progress = read_json(progress_path, {}) or {}
    if not progress:
        return {
            "available": False,
            "status": "not_started",
            "completed_count": 0,
            "retained_count": 0,
            "short_trajectory_count": 0,
            "expected_count": GPT50_EXPECTED_SCENARIO_COUNT,
            "pending_count": GPT50_EXPECTED_SCENARIO_COUNT,
            "reviewable_count": 0,
            "without_readable_rollout_count": GPT50_EXPECTED_SCENARIO_COUNT,
            "without_accepted_rollout_count": GPT50_EXPECTED_SCENARIO_COUNT,
            "attempt_count": 0,
            "attempt_status_counts": {},
            "updated_at_utc": None,
            "progress_path": _display_path(progress_path),
            "by_scenario": {},
            "recent_errors": [],
        }
    completed = progress.get("completed_slots") or {}
    by_scenario = {}
    for record in completed.values():
        scenario_id = record.get("scenario_id")
        if not scenario_id:
            continue
        turn_count = int(record.get("turn_count") or 0)
        machine_precheck_passed = record.get(
            "machine_precheck_passed"
        ) is True
        gate3_candidate = (
            machine_precheck_passed
            and turn_count >= GPT50_MIN_GATE3_TURNS
        )
        if gate3_candidate:
            rollout_status = "completed"
        elif turn_count < GPT50_MIN_GATE3_TURNS:
            rollout_status = "short_trajectory"
        else:
            rollout_status = "retained_for_review"
        by_scenario[scenario_id] = {
            "status": rollout_status,
            "turn_count": turn_count,
            "accepted_at_utc": record.get("accepted_at_utc"),
            "admission": record.get("admission"),
            "machine_precheck_passed": machine_precheck_passed,
            "gate3_candidate": gate3_candidate,
            "artifact_available": True,
        }
    accepted_scenario_ids = set(by_scenario)
    attempts = progress.get("attempts") or []
    for attempt in attempts:
        status = attempt.get("status", "unknown")
        scenario_id = attempt.get("scenario_id")
        if not scenario_id or scenario_id in accepted_scenario_ids:
            continue
        summary = _gpt50_attempt_summary(attempt)
        previous = by_scenario.get(scenario_id) or {}
        attempt_turns = summary.get("turn_count")
        readable_attempt = bool(
            (
                attempt.get("trajectory_file")
                or attempt.get("partial_trajectory_file")
            )
            and isinstance(attempt_turns, int)
            and attempt_turns > 0
        )
        previous_turns = previous.get("turn_count")
        best_turns = max(
            [
                value for value in (previous_turns, attempt_turns)
                if isinstance(value, int)
            ],
            default=None,
        )
        by_scenario[scenario_id] = {
            "status": status,
            "turn_count": best_turns,
            "latest_attempt_turn_count": attempt_turns,
            "machine_precheck_passed": False,
            "gate3_candidate": False,
            "artifact_available": (
                previous.get("artifact_available") is True
                or readable_attempt
            ),
        }
    latest_attempts = {}
    for attempt in attempts:
        identity = attempt.get("slot_id") or attempt.get("scenario_id")
        if identity:
            latest_attempts[identity] = attempt
    status_counts = {}
    for attempt in latest_attempts.values():
        status = attempt.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    expected = progress.get(
        "expected_slot_count", GPT50_EXPECTED_SCENARIO_COUNT
    )
    retained_count = len(completed)
    completed_count = sum(
        item["gate3_candidate"] for item in by_scenario.values()
    )
    short_trajectory_count = sum(
        item["status"] == "short_trajectory"
        for item in by_scenario.values()
    )
    reviewable_count = sum(
        item.get("artifact_available") is True
        for item in by_scenario.values()
    )
    recent_errors = [
        {
            "scenario_id": attempt.get("scenario_id"),
            "error_type": attempt.get("error_type"),
            "error": str(attempt.get("error", ""))[:300],
            "finished_at_utc": attempt.get("finished_at_utc"),
        }
        for attempt in latest_attempts.values()
        if attempt.get("status") == "generation_error"
    ][-5:]
    raw_status = progress.get("status", "unknown")
    display_status = (
        "regenerating"
        if raw_status == "incomplete_requeued_short_trajectories"
        else raw_status
    )
    return {
        "available": True,
        "status": display_status,
        "raw_status": raw_status,
        "completed_count": completed_count,
        "retained_count": retained_count,
        "short_trajectory_count": short_trajectory_count,
        "expected_count": expected,
        "pending_count": max(0, expected - len(by_scenario)),
        "reviewable_count": reviewable_count,
        "without_readable_rollout_count": max(0, expected - reviewable_count),
        "without_accepted_rollout_count": max(0, expected - retained_count),
        "attempt_count": len(attempts),
        "attempt_status_counts": status_counts,
        "updated_at_utc": progress.get("updated_at_utc"),
        "progress_path": _display_path(progress_path),
        "by_scenario": by_scenario,
        "recent_errors": recent_errors,
        "human_review_required": True,
    }


def _gpt50_scenario_records():
    root = _active_gpt50_scenario_root()
    records = []
    errors = []
    seen = set()
    for path in discover_scenario_paths(root):
        try:
            scenario = read_json(path, {}) or {}
            scenario_id = scenario.get("scenario_id")
            if not scenario_id:
                raise ValueError("scenario_id is missing")
            if scenario_id in seen:
                raise ValueError(f"duplicate scenario_id: {scenario_id}")
            seen.add(scenario_id)
            try:
                validate_scenario(scenario)
                schema_status = "valid"
                schema_error = ""
            except (TypeError, ValueError) as exc:
                schema_status = "invalid"
                schema_error = str(exc)
            records.append((path, scenario, schema_status, schema_error))
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append({
                "artifact_path": _display_path(path),
                "error": str(exc),
            })
    return root, records, errors


def _gpt50_gate2_item_status(experiment_id, item):
    if item.get("error") or item.get("replay_errors"):
        return "machine_error"
    automatic = item.get("automatic_screen_passed")
    if isinstance(automatic, bool):
        return "machine_pass" if automatic else "machine_fail"
    if experiment_id == "E6":
        comparison = item.get("comparison") or {}
        if comparison:
            passed = (
                comparison.get("exact_direction_agreement", 0) >= 0.50
                and comparison.get("true_sign_reversal_rate", 1) <= 0.40
                and not comparison.get("replay_failed")
            )
            return "machine_pass" if passed else "machine_fail"
    return "pending_human"


def load_gpt50_gate2(scenario_id=None):
    """Expose Gate 2 evidence without turning sampling absence into rejection."""
    manifest = read_json(GPT50_GATE2_ROOT / "manifest.json", {}) or {}
    intervention_progress = read_json(
        GPT50_GATE2_ROOT / "experiments" / "environment_interventions.json",
        {},
    ) or {}
    progress_records = intervention_progress.get("records") or []
    experiments = []
    by_scenario = {}
    for experiment_id, filename, label, items_key in GPT50_GATE2_EXPERIMENTS:
        payload = read_json(GPT50_GATE2_ROOT / filename, {}) or {}
        raw_items = payload.get(items_key) or []
        if not raw_items and experiment_id in {"E3", "E4", "E5", "E7"}:
            progress_key = experiment_id.lower()
            raw_items = []
            for progress_item in progress_records:
                common = {
                    "scenario_id": progress_item.get("scenario_id"),
                    "source_trajectory_id": progress_item.get(
                        "source_trajectory_id"
                    ),
                    "checkpoint_turn_id": progress_item.get(
                        "checkpoint_turn_id"
                    ),
                }
                if progress_item.get(progress_key):
                    raw_items.append({
                        **common,
                        **progress_item[progress_key],
                        "evidence_stage": "in_progress_checkpoint",
                    })
                elif progress_item.get("error"):
                    raw_items.append({
                        **common,
                        "error": progress_item["error"],
                        "evidence_stage": "in_progress_error",
                    })
        enriched = []
        counts = {}
        for raw in raw_items:
            item = dict(raw)
            status = _gpt50_gate2_item_status(experiment_id, item)
            item["gate2_screen_status"] = status
            counts[status] = counts.get(status, 0) + 1
            item_scenario_id = item.get("scenario_id")
            if item_scenario_id:
                overview = by_scenario.setdefault(item_scenario_id, {
                    "evidence_item_count": 0,
                    "experiment_ids": [],
                    "status_counts": {},
                })
                overview["evidence_item_count"] += 1
                if experiment_id not in overview["experiment_ids"]:
                    overview["experiment_ids"].append(experiment_id)
                overview["status_counts"][status] = (
                    overview["status_counts"].get(status, 0) + 1
                )
            if scenario_id is None or item_scenario_id == scenario_id:
                enriched.append(item)
        record = payload.get("record", payload) if payload else {}
        experiments.append({
            "experiment_id": experiment_id,
            "label": label,
            "filename": filename,
            "available": bool(payload),
            "batch_record": record,
            "item_count": len(raw_items),
            "status_counts": counts,
            "items": enriched if scenario_id is not None else [],
        })
    for item_scenario_id, overview in by_scenario.items():
        counts = overview["status_counts"]
        if counts.get("machine_error"):
            status = "machine_error"
        elif counts.get("machine_fail"):
            status = "machine_flagged"
        elif counts.get("pending_human"):
            status = "pending_human_review"
        elif counts.get("machine_pass"):
            status = "machine_screen_passed"
        else:
            status = "not_sampled"
        overview["status"] = status
        overview["sampled_experiment_count"] = len(overview["experiment_ids"])
    selected_overview = by_scenario.get(scenario_id, {
        "status": "not_sampled",
        "evidence_item_count": 0,
        "sampled_experiment_count": 0,
        "experiment_ids": [],
        "status_counts": {},
    }) if scenario_id is not None else None
    return {
        "format": "socialflux_gpt50_gate2_review_v1",
        "gate": "gate_2_environment_validity",
        "scope": "batch_environment_validity_with_sampled_scenario_evidence",
        "deletion_policy": "retain_all_and_label",
        "manifest": manifest,
        "machine_progress": {
            "target_scenario_count": 50,
            "completed_scenario_count": len(progress_records),
            "successful_scenario_count": sum(
                not item.get("error") for item in progress_records
            ),
            "error_scenario_count": sum(
                bool(item.get("error")) for item in progress_records
            ),
            "last_scenario_id": (
                progress_records[-1].get("scenario_id")
                if progress_records else None
            ),
        },
        "experiments": experiments,
        "by_scenario": by_scenario if scenario_id is None else {},
        "scenario_overview": selected_overview,
        "human_review_required": True,
        "warning": (
            "Gate 2 是 batch-level Environment validity；未抽中不等于失败，"
            "机器标记也不等于人工结论。"
        ),
    }


def load_gpt50_review():
    """Expose the active GPT authoring batch for real, hash-bound Gate 1 review."""
    root, records, errors = _gpt50_scenario_records()
    run_manifest = read_json(root.parent / "run_manifest.json", {}) or {}
    rollout = load_gpt50_rollout_progress()
    gate2 = load_gpt50_gate2()
    candidates = []
    for ordinal, (path, scenario, schema_status, schema_error) in enumerate(records, 1):
        design = scenario.get("narrative_design", {})
        candidates.append({
            "ordinal": ordinal,
            "scenario_id": scenario.get("scenario_id"),
            "title": scenario.get("title", ""),
            "mechanism": scenario.get("mechanism", ""),
            "relationship_structure": design.get("relationship_structure", ""),
            "source_type": scenario.get("source", {}).get("type", ""),
            "construction_status": scenario.get("construction_status", {}),
            "schema_status": schema_status,
            "schema_error": schema_error,
            "scenario_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "artifact_path": _display_path(path),
            "rollout": rollout["by_scenario"].get(
                scenario.get("scenario_id"),
                {"status": "pending", "turn_count": None},
            ),
            "gate2": gate2["by_scenario"].get(
                scenario.get("scenario_id"),
                {
                    "status": "not_sampled",
                    "evidence_item_count": 0,
                    "sampled_experiment_count": 0,
                    "experiment_ids": [],
                    "status_counts": {},
                },
            ),
        })
    scenario_count = len(candidates)
    schema_valid_count = sum(
        item["schema_status"] == "valid" for item in candidates
    )
    if scenario_count == 0:
        batch_status = "missing_formal_batch"
        review_blocker = (
            "正式 GPT50 批次尚未生成；smoke scenario 不会进入人工审核队列。"
        )
    elif scenario_count < GPT50_EXPECTED_SCENARIO_COUNT:
        batch_status = "formal_batch_incomplete"
        review_blocker = (
            f"正式 GPT50 批次生成中：{scenario_count} / "
            f"{GPT50_EXPECTED_SCENARIO_COUNT}。"
        )
    elif scenario_count > GPT50_EXPECTED_SCENARIO_COUNT:
        batch_status = "formal_batch_overfilled"
        review_blocker = (
            f"正式批次包含 {scenario_count} 条，超过预期 "
            f"{GPT50_EXPECTED_SCENARIO_COUNT} 条；请先核对批次边界。"
        )
    elif schema_valid_count != scenario_count or errors:
        batch_status = "formal_batch_invalid"
        review_blocker = "正式批次存在 schema 或加载错误，请修复后再冻结 Gate 1。"
    else:
        batch_status = "ready_for_human_gate1"
        review_blocker = ""
    return {
        "format": "socialflux_gpt50_gate1_review_v1",
        "batch": "gpt50_pipeline_design_audit",
        "batch_status": batch_status,
        "expected_scenario_count": GPT50_EXPECTED_SCENARIO_COUNT,
        "review_ready": batch_status == "ready_for_human_gate1",
        "review_blocker": review_blocker,
        "authoring_model": run_manifest.get("authoring_model", run_manifest.get("model", "unknown")),
        "authoring_status": run_manifest.get("status", "not_started"),
        "active_scenario_root": _display_path(root),
        "scenario_count": scenario_count,
        "schema_valid_count": schema_valid_count,
        "rollout": rollout,
        "gate2": {
            key: value for key, value in gate2.items()
            if key != "by_scenario"
        },
        "candidates": candidates,
        "load_errors": errors,
        "human_review_warning": (
            "机器 schema/quality 检查不构成 Gate 1。只有实名人工审核、完整评分、"
            "initial state 确认和导出的 hash-bound 记录才能冻结场景。"
        ),
    }


def _gpt50_trajectory_path(scenario_dir, attempt):
    """Resolve one current attempt artifact without mixing old review archives."""
    names = [
        attempt.get("trajectory_file"),
        attempt.get("partial_trajectory_file"),
    ]
    for name in names:
        if not name:
            continue
        for parent in (
            scenario_dir,
            scenario_dir / "rejected",
            scenario_dir / "budget_truncated",
            scenario_dir / "short_trajectories",
        ):
            target = parent / name
            if target.is_file():
                return target
    return None


def _gpt50_attempt_summary(item):
    precheck = item.get("precheck") or {}
    structural = precheck.get("structural") or {}
    checks = structural.get("checks") or {}
    return {
        "status": item.get("status"),
        "attempt": item.get("attempt"),
        "technical_retry": item.get("technical_retry") is True,
        "error_type": item.get("error_type"),
        "error": str(item.get("error", ""))[:500],
        "finished_at_utc": item.get("finished_at_utc"),
        "completed_turns_before_error": item.get(
            "completed_turns_before_error"
        ),
        "trajectory_id": item.get("trajectory_id"),
        "trajectory_file": item.get("trajectory_file"),
        "partial_trajectory_file": item.get("partial_trajectory_file"),
        "candidate_classification": precheck.get("candidate_classification"),
        "hard_reject_reasons": precheck.get("hard_reject_reasons") or [],
        "false_checks": [key for key, passed in checks.items() if not passed],
        "turn_count": (
            structural.get("turn_count")
            if isinstance(structural.get("turn_count"), int)
            else item.get("completed_turns_before_error")
        ),
    }


def load_gpt50_rollout(scenario_id):
    """Load accepted or rejected GPT dialogue for human inspection."""
    progress = read_json(GPT50_ROLLOUT_ROOT / "progress.json", {}) or {}
    raw_attempts = [
        item for item in progress.get("attempts", [])
        if item.get("scenario_id") == scenario_id
    ]
    attempts = [_gpt50_attempt_summary(item) for item in raw_attempts]
    completed = next(
        (
            item
            for item in (progress.get("completed_slots") or {}).values()
            if item.get("scenario_id") == scenario_id
        ),
        None,
    )
    scenario_record = next(
        (
            item
            for item in _gpt50_scenario_records()[1]
            if item[1].get("scenario_id") == scenario_id
        ),
        None,
    )
    if scenario_record is None:
        return {
            "status": "artifact_missing",
            "scenario_id": scenario_id,
            "record": completed,
            "attempts": attempts[-5:],
            "human_review": "pending",
        }
    directory = scenario_record[0].parent.name
    scenario_dir = GPT50_ROLLOUT_ROOT / directory
    selected_attempt = None
    trajectory_path = None
    artifact_kind = None
    if completed is not None:
        trajectory_path = scenario_dir / completed["trajectory_file"]
        artifact_kind = "accepted"
        selected_attempt = next(
            (
                item for item in reversed(raw_attempts)
                if item.get("trajectory_id") == completed.get("trajectory_id")
            ),
            None,
        )
    else:
        artifact_candidates = []
        for attempt_index, item in enumerate(raw_attempts):
            candidate = _gpt50_trajectory_path(scenario_dir, item)
            if candidate is None:
                continue
            summary = _gpt50_attempt_summary(item)
            turn_count = summary.get("turn_count")
            if not isinstance(turn_count, int):
                candidate_value = read_json(candidate, {}) or {}
                turn_count = len(candidate_value.get("turns", []))
            artifact_candidates.append(
                (turn_count, attempt_index, item, candidate)
            )
        if artifact_candidates:
            _, _, selected_attempt, trajectory_path = max(
                artifact_candidates,
                key=lambda value: (value[0], value[1]),
            )
            artifact_kind = "rejected_or_partial"
    latest_attempt = raw_attempts[-1] if raw_attempts else None
    if trajectory_path is None or not trajectory_path.is_file():
        latest_status = (
            latest_attempt.get("status") if latest_attempt else "pending"
        )
        return {
            "status": latest_status,
            "scenario_id": scenario_id,
            "record": completed,
            "attempts": attempts[-5:],
            "quality_warning": (
                "当前尝试没有形成可展示的完整 rollout 对话。"
                if latest_attempt else "当前场景尚未开始 rollout。"
            ),
            "human_review": "pending",
        }
    trajectory = read_json(trajectory_path, {}) or {}
    if not trajectory:
        return {
            "status": "artifact_missing",
            "scenario_id": scenario_id,
            "record": completed,
            "artifact_path": _display_path(trajectory_path),
            "attempts": attempts[-5:],
            "human_review": "pending",
        }
    turns = []
    for turn in trajectory.get("turns", []):
        action = turn.get("policy_action") or {}
        turns.append({
            "turn_id": turn.get("turn_id"),
            "policy_action": action.get("text", ""),
            "environment_response": turn.get("environment_response", ""),
            "social_act": (turn.get("appraisal") or {}).get("social_act"),
            "speaker_intent": (turn.get("appraisal") or {}).get(
                "speaker_intent"
            ),
            "state_delta": turn.get("state_delta", {}),
            "dynamics_delta": turn.get("dynamics_delta", {}),
            "trigger_events": turn.get("trigger_events", []),
        })
    machine_precheck_passed = bool(
        completed
        and completed.get("machine_precheck_passed") is True
    )
    gate3_candidate = (
        machine_precheck_passed
        and len(turns) >= GPT50_MIN_GATE3_TURNS
    )
    selected_summary = (
        _gpt50_attempt_summary(selected_attempt)
        if selected_attempt else {}
    )
    selected_status = (
        selected_attempt.get("status") if selected_attempt else None
    )
    if not turns:
        rollout_status = selected_status or "artifact_missing"
        quality_warning = (
            "技术失败留下了空检查点，但没有形成任何可展示的对话回合。"
        )
    elif gate3_candidate:
        rollout_status = "completed"
        quality_warning = ""
    elif selected_status == "generation_error":
        rollout_status = selected_status
        quality_warning = (
            f"技术生成在完成 {len(turns)} 轮后中断；以下只是 partial "
            "对话，保留供诊断，不是完整候选。"
        )
    elif selected_attempt:
        rollout_status = selected_status or "retained_for_review"
        quality_warning = (
            "该对话已生成但机器质量门未通过；页面保留完整内容供人工诊断，"
            "不能视为 Gate 3 候选。"
        )
    elif len(turns) < GPT50_MIN_GATE3_TURNS:
        rollout_status = "short_trajectory"
        quality_warning = "该对话不足 10 turn，只能作为失败证据。"
    else:
        rollout_status = "retained_for_review"
        quality_warning = "该对话需要人工诊断，尚未进入 Gate 3。"
    return {
        "status": rollout_status,
        "scenario_id": scenario_id,
        "trajectory_id": trajectory.get("trajectory_id"),
        "policy_id": trajectory.get("policy_id"),
        "policy_prompt_id": (
            trajectory.get("policy_provenance") or {}
        ).get("prompt_id"),
        "minimum_natural_turns": (
            trajectory.get("policy_provenance") or {}
        ).get("minimum_natural_turns"),
        "turn_count": len(turns),
        "turns": turns,
        "machine_precheck_passed": machine_precheck_passed,
        "gate3_candidate": gate3_candidate,
        "quality_warning": quality_warning,
        "ending": trajectory.get("ending", {}),
        "record": completed,
        "artifact_kind": artifact_kind,
        "machine_review": selected_summary,
        "artifact_path": _display_path(trajectory_path),
        "attempts": attempts[-5:],
        "human_review": "pending",
    }


def load_gpt50_scenario(scenario_id):
    root, records, _ = _gpt50_scenario_records()
    record = next(
        (item for item in records if item[1].get("scenario_id") == scenario_id),
        None,
    )
    if record is None:
        return None
    path, scenario, schema_status, schema_error = record
    quality_path = root.parent / "source_quality.json"
    document_path = path.with_suffix(".md")
    return {
        "scenario": scenario,
        "scenario_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "artifact_path": _display_path(path),
        "schema_status": schema_status,
        "schema_error": schema_error,
        "source_quality": read_json(quality_path, {}) or {},
        "authoring_run": read_json(root.parent / "run_manifest.json", {}) or {},
        "documentation": (
            document_path.read_text(encoding="utf-8")
            if document_path.is_file() else ""
        ),
        "rollout": load_gpt50_rollout(scenario_id),
        "gate2": load_gpt50_gate2(scenario_id),
        "human_review": "pending",
    }


def load_scale20_pilot_review():
    """Load the bounded Scale20 pilot and attach each immutable trajectory artifact."""
    review = read_json(SCALE20_PILOT_REVIEW, {}) or {}
    enriched = []
    for candidate in review.get("candidates", []):
        item = dict(candidate)
        relative = Path(item.get("artifact_path", ""))
        target = (ROOT / relative).resolve()
        if ROOT in target.parents and target.is_file():
            trajectory = read_json(target, {}) or {}
            trajectory["screening"] = {
                "automatic_decision": "REJECT",
                "candidate_classification": item.get("classification", "diagnostic"),
                "source_root": "scale20_v1_bounded_pilot",
                "human_review_reasons": [
                    issue.get("issue", "") for issue in item.get("issues", [])
                ],
            }
            trajectory["diagnostic_review"] = {
                "review_type": "model_semantic_review",
                "status": item.get("model_semantic_review", "pending"),
                "human_review": item.get("human_review", "pending"),
                "issues": item.get("issues", []),
            }
            item["trajectory"] = trajectory
        else:
            item["trajectory_error"] = "artifact_missing_or_outside_workspace"
        enriched.append(item)
    return {**review, "candidates": enriched}


def load_scale20_full20_review():
    """Load all 20 one-attempt trajectories for human review."""
    review = read_json(SCALE20_FULL20_REVIEW, {}) or {}
    enriched = []
    for candidate in review.get("candidates", []):
        item = dict(candidate)
        relative = Path(item.get("artifact_path", ""))
        target = (ROOT / relative).resolve()
        if ROOT in target.parents and target.is_file():
            trajectory = read_json(target, {}) or {}
            semantic = item.get("model_semantic_review", {})
            semantic_label = semantic.get("label", "pending") if isinstance(semantic, dict) else str(semantic)
            semantic_note = semantic.get("note", "") if isinstance(semantic, dict) else ""
            machine_decision = "PASS" if item.get("generation_status") == "accepted" else "REVIEW"
            trajectory["screening"] = {
                "automatic_decision": machine_decision,
                "candidate_classification": item.get("generation_status", "diagnostic"),
                "source_root": "scale20_v1_full20_one_attempt",
                "human_review_reasons": [semantic_note] if semantic_note else [],
            }
            trajectory["diagnostic_review"] = {
                "review_type": "model_semantic_review",
                "status": semantic_label,
                "human_review": item.get("human_review", "pending"),
                "issues": [semantic_note] if semantic_note else [],
            }
            item["trajectory"] = trajectory
        else:
            item["trajectory_error"] = "artifact_missing_or_outside_workspace"
        enriched.append(item)
    return {**review, "candidates": enriched}


def load_scale20_combined_review():
    """Keep v1 full20 evidence and append clearly versioned v2 pilots."""
    review = load_scale20_full20_review()
    v2 = read_json(SCALE20_V2_REVIEW, {}) or {}
    enriched = []
    for candidate in v2.get("candidates", []):
        item = dict(candidate)
        target = (ROOT / Path(item.get("artifact_path", ""))).resolve()
        if ROOT in target.parents and target.is_file():
            trajectory = read_json(target, {}) or {}
            semantic = item.get("model_semantic_review", {})
            trajectory["screening"] = {
                "automatic_decision": "REVIEW",
                "candidate_classification": item.get("generation_status", "diagnostic"),
                "source_root": "scale20_v2_representative_pilot",
                "human_review_reasons": [semantic.get("note", "")],
            }
            trajectory["diagnostic_review"] = {
                "review_type": "model_semantic_review",
                "status": semantic.get("label", "pending"),
                "human_review": item.get("human_review", "pending"),
                "issues": item.get("issues", []),
            }
            item["trajectory"] = trajectory
        else:
            item["trajectory_error"] = "artifact_missing_or_outside_workspace"
        enriched.append(item)
    return {
        **review,
        "candidates": review.get("candidates", []),
        "v2_candidates": enriched,
        "v2_revision": {key: value for key, value in v2.items() if key != "candidates"},
    }



def load_scale150_review():
    """Return a compact, live Scale200 index without embedding trajectory bodies."""
    matrix = read_json(SCALE150_MATRIX, {}) or {}
    automatic_gate_records = {
        item.get("scenario_id"): item
        for item in (read_json(SCALE300_AUTOMATIC_GATE_AUDIT, {}) or {}).get("records", [])
        if item.get("scenario_id")
    }
    attempts = {}
    semantic_reviews = {}
    for review_path in SCALE150_MODEL_REVIEW_FILES:
        semantic_reviews.update({
            item.get("trajectory_id"): item
            for item in (read_json(review_path, {}) or {}).get("records", [])
            if item.get("trajectory_id")
        })
    shard_status = {}
    for stack_name, rollout_root in SCALE150_ROLLOUT_ROOTS:
        for shard in range(1, 5):
            progress_path = rollout_root / f"shard{shard}" / "progress.json"
            progress = read_json(progress_path, {}) or {}
            shard_status[f"{stack_name}.shard{shard}"] = {
                "status": progress.get("status", "not_started"),
                "attempt_count": len(progress.get("attempts", [])),
                "accepted_count": progress.get("completed_slot_count", 0),
                "expected_count": progress.get("expected_slot_count", 0),
                "quality_summary": progress.get("quality_summary", {}),
            }
            for attempt in progress.get("attempts", []):
                attempts.setdefault(attempt.get("scenario_id"), []).append(
                    (stack_name, rollout_root, shard, attempt)
                )
    candidates = []
    status_counts = {}
    generated_count = 0
    for row in matrix.get("scenarios", []):
        item = {
            "scenario_id": row["scenario_id"],
            "ordinal": row.get("ordinal"),
            "title": row.get("title"),
            "relationship_category": row.get("relationship_category"),
            "conflict_structure": row.get("conflict_structure"),
            "source_type": row.get("source_type"),
            "source_work": row.get("source_work"),
            "configuration_status": row.get("configuration_status"),
            "generation_status": "pending_generation",
            "human_review": "pending",
            "automatic_gate_audit": automatic_gate_records.get(row["scenario_id"], {}),
            "gate_status": {
                "gate1": "pending_human_review",
                "gate2": "pending_or_machine_evidence_only",
                "gate3": "pending_rollout_semantic_review",
                "gate4": "not_constructed",
            },
        }
        scenario_path = (
            SCALE150_MATRIX.parent / "scenarios"
            / f"scenario_{int(row['ordinal']):03d}"
            / f"scenario_{int(row['ordinal']):03d}.json"
        )
        current_scenario = read_json(scenario_path, {}) or {}
        current_fingerprint = hashlib.sha256(json.dumps(
            current_scenario, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        item["scenario_fingerprint"] = current_fingerprint
        attempt_history = attempts.get(row["scenario_id"], [])
        item["attempt_history_count"] = len(attempt_history)
        item["stale_attempt_count"] = sum(
            record[3].get("scenario_fingerprint") != current_fingerprint
            for record in attempt_history
        )
        record = next(
            (
                value for value in reversed(attempt_history)
                if value[3].get("scenario_fingerprint") == current_fingerprint
            ),
            None,
        )
        if record:
            stack_name, rollout_root, shard, attempt = record
            status = attempt.get("status", "unknown")
            item["generation_status"] = status
            item["scenario_version_matches_current"] = (
                attempt.get("scenario_fingerprint") == current_fingerprint
            )
            if not item["scenario_version_matches_current"]:
                item["gate_status"]["gate3"] = "stale_scenario_version_regeneration_required"
            item["trajectory_id"] = (
                attempt.get("trajectory_id") or attempt.get("partial_trajectory_id")
            )
            item["turn_count"] = (
                attempt.get("completed_turns_before_error")
                or (attempt.get("precheck", {}).get("structural", {}).get("turn_count"))
                or 0
            )
            item["ending"] = attempt.get("precheck", {}).get("structural", {}).get("ending")
            item["machine_precheck"] = attempt.get("precheck")
            scenario_dir = (
                rollout_root / f"shard{shard}"
                / f"scenario_{int(row['ordinal']):03d}"
            )
            filename = (
                attempt.get("partial_trajectory_file")
                if status == "generation_error"
                else attempt.get("trajectory_file")
            )
            if filename:
                subdirectory = {
                    "generation_error": "rejected",
                    "short_natural_trajectory": "short_trajectories",
                    "budget_truncated": "budget_truncated",
                    "machine_rejected": "rejected",
                }.get(status, "")
                target = scenario_dir / subdirectory / filename
                if target.is_file():
                    item["artifact_path"] = str(target.relative_to(ROOT))
            item["model_stack"] = stack_name
            item["model_semantic_review"] = semantic_reviews.get(
                item.get("trajectory_id"), {"decision": "pending"}
            )
            if item["model_semantic_review"].get("decision") == "reject":
                item["gate_status"]["gate3"] = "model_semantic_reject_human_pending"
            generated_count += 1
        status_counts[item["generation_status"]] = (
            status_counts.get(item["generation_status"], 0) + 1
        )
        candidates.append(item)
    return {
        "format": "socialflux_scale300_live_review_v1",
        "configuration_version": "scale300_v1",
        "scenario_count": matrix.get("scenario_count", 0),
        "source_counts": matrix.get("source_counts", {}),
        "design_contract": matrix.get("design_contract", {}),
        "generated_scenario_count": generated_count,
        "pending_scenario_count": max(0, matrix.get("scenario_count", 0) - generated_count),
        "generation_status_counts": status_counts,
        "shards": shard_status,
        "candidates": candidates,
        "human_review_warning": "模型与机器检查不是人工验收；短轨迹、截断和失败样本均保留。",
    }


def load_scale150_scenario(scenario_id):
    """Load one exact Scale200 scenario for Gate 1 review."""
    matrix = read_json(SCALE150_MATRIX, {}) or {}
    row = next(
        (
            item for item in matrix.get("scenarios", [])
            if item.get("scenario_id") == scenario_id
        ),
        None,
    )
    if row is None:
        return None
    ordinal = int(row.get("ordinal", 0))
    target = (
        SCALE150_MATRIX.parent / "scenarios" / f"scenario_{ordinal:03d}"
        / f"scenario_{ordinal:03d}.json"
    ).resolve()
    if ROOT not in target.parents or not target.is_file():
        return None
    scenario = read_json(target, {}) or {}
    if scenario.get("scenario_id") != scenario_id:
        return None
    return {
        "matrix_record": row,
        "scenario": scenario,
        "artifact_path": str(target.relative_to(ROOT)),
        "scenario_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "human_review": "pending",
    }


def load_scale150_trajectory(trajectory_id):
    review = load_scale150_review()
    candidate = next(
        (
            item for item in review.get("candidates", [])
            if item.get("trajectory_id") == trajectory_id
        ),
        None,
    )
    if not candidate or not candidate.get("artifact_path"):
        return None
    target = (ROOT / candidate["artifact_path"]).resolve()
    if ROOT not in target.parents or not target.is_file():
        return None
    trajectory = read_json(target, {}) or {}
    trajectory["screening"] = {
        "automatic_decision": (
            "PASS" if candidate.get("generation_status") == "accepted" else "REVIEW"
        ),
        "candidate_classification": candidate.get("generation_status"),
        "source_root": candidate.get("model_stack", "scale150_v1"),
        "human_review_reasons": [],
    }
    semantic_review = candidate.get("model_semantic_review", {"decision": "pending"})
    trajectory["diagnostic_review"] = {
        "review_type": "model_semantic_review_not_human",
        "status": semantic_review.get("decision", "pending"),
        "issues": semantic_review.get("issues", []),
        "summary": semantic_review.get("summary", ""),
        "human_review": "pending",
    }
    return {"candidate": candidate, "trajectory": trajectory}


def load_scale300_task_review():
    """Return live, compact T1-T4 construction status for all Scale300 scenarios."""
    review = load_scale150_review()
    progress_by_scenario = {}
    answer_counts = {name: 0 for name in ("T1", "T2", "T3", "T4")}
    for target in sorted(SCALE300_TASK_ROOT.glob("scenario_*.json")):
        package = read_json(target, {}) or {}
        scenario_id = package.get("scenario_id")
        if not scenario_id:
            continue
        tasks = package.get("tasks", {})
        for name in answer_counts:
            answer_counts[name] += int(bool((tasks.get(name) or {}).get("llm_answer")))
        progress_by_scenario[scenario_id] = {
            "status": package.get("status", "pending"),
            "turn_count": package.get("turn_count"),
            "task_statuses": package.get("task_statuses", {}),
            "source_quality": package.get("source_quality", {}),
            "request_accounting": package.get("request_accounting", {}),
        }
    candidates = []
    semantic_counts = {}
    for candidate in review.get("candidates", []):
        item = {
            key: candidate.get(key)
            for key in (
                "scenario_id", "ordinal", "title", "relationship_category",
                "conflict_structure", "generation_status", "turn_count",
                "trajectory_id", "artifact_path", "model_semantic_review",
            )
        }
        item["task_construction"] = progress_by_scenario.get(
            candidate.get("scenario_id"), {"status": "pending"}
        )
        semantic_decision = (candidate.get("model_semantic_review") or {}).get(
            "decision", "pending"
        )
        semantic_counts[semantic_decision] = (
            semantic_counts.get(semantic_decision, 0) + 1
        )
        candidates.append(item)
    task_summary = read_json(SCALE300_TASK_ROOT / "summary.json", {}) or {}
    task_summary["answer_counts"] = answer_counts
    automatic_gate_summary = (read_json(SCALE300_AUTOMATIC_GATE_AUDIT, {}) or {}).get("summary", {})
    return {
        "format": "socialflux_scale300_task_review_live_v1",
        "background": read_json(SCALE300_TASK_ROOT / "background_status.json", {}) or {},
        "summary": task_summary,
        "processed": len(progress_by_scenario),
        "total_scenarios": len(candidates),
        "shards": [],
        "candidates": candidates,
        "big_progress": {
            "configured": review.get("scenario_count", 0),
            "rollouts_generated": review.get("generated_scenario_count", 0),
            "rollout_status_counts": review.get("generation_status_counts", {}),
            "model_semantic_review_counts": semantic_counts,
            "automatic_gate_summary": automatic_gate_summary,
            "strict_machine_and_model_gate3_pass_human_pending": sum(
                candidate.get("generation_status") == "accepted"
                and (candidate.get("model_semantic_review") or {}).get("decision") == "approve"
                for candidate in review.get("candidates", [])
            ),
            "human_ground_truth_completed": task_summary.get(
                "human_ground_truth_completed", 0
            ),
        },
        "annotation_notice": (
            "LLM answers are review aids, not ground truth. T2 controlled pairs and "
            "T3 branches remain pending human/branch validation where marked."
        ),
    }


def load_scale300_task_package(scenario_id):
    """Load one generated task package without allowing arbitrary path access."""
    review = load_scale150_review()
    candidate = next(
        (item for item in review.get("candidates", []) if item.get("scenario_id") == scenario_id),
        None,
    )
    if not candidate:
        return None
    ordinal = int(candidate.get("ordinal", 0))
    target = (SCALE300_TASK_ROOT / f"scenario_{ordinal:03d}.json").resolve()
    if SCALE300_TASK_ROOT.resolve() not in target.parents or not target.is_file():
        return {
            "scenario_id": scenario_id,
            "ordinal": ordinal,
            "status": "pending",
            "human_review": "pending",
        }
    payload = read_json(target, {}) or {}
    payload["artifact_path"] = str(target.relative_to(ROOT))
    return payload



def _r3_diagnostic_trajectory(scenario_id):
    review = load_r3_diagnostic_review()
    candidate = review.get("human_review_candidate", {})
    if candidate.get("scenario_id") != scenario_id:
        return None
    relative = Path(candidate.get("artifact_path", ""))
    target = (ROOT / relative).resolve()
    if ROOT not in target.parents or not target.is_file():
        return None
    trajectory = read_json(target, {}) or {}
    if not trajectory.get("turns"):
        return None
    trajectory["diagnostic_review"] = candidate
    trajectory["screening"] = {
        "automatic_decision": "REJECT",
        "scores": {},
        "source_stage": "r3_diagnostic_rejected_evidence",
        "observed_outcome": infer_observed_outcome(trajectory),
        "judge_rationale": candidate.get("known_issue", ""),
        "hard_failures": ["unusable_trajectory"],
        "missing_evidence": list(QUALITY_DIMENSIONS),
        "protocol_contract_warnings": [
            "predates_current_quality_version",
            "diagnostic_human_feedback_only",
            "cannot_be_promoted_to_formal_pool",
        ],
        "provisional_selected": False,
        "human_review_required": True,
        "human_review_reasons": [
            "请判断 t11–t17 是不可接受的车轱辘话，还是自然的必要确认。",
            "请逐轮核对提案、承诺、付款、请求的说话人和 action_owner。",
            "该轨迹在 t20 前因旧 closure validator 失败；既非自然结束，也非达到上限。",
        ],
        "precheck": {
            "quality_version": candidate.get("quality_version"),
            "classification": candidate.get("classification"),
            "fixed_since_candidate": candidate.get("fixed_since_candidate", []),
        },
    }
    return trajectory


def annotation_contract():
    return {
        "format": "socialflux_annotation_ui_v1",
        "storage": "browser_local_draft",
        "scenario_checks": list(SCENARIO_CHECKS),
        "scenario_rating_scale": {
            "minimum": 1,
            "maximum": 5,
            "dimensions": [
                "social_plausibility",
                "character_coherence",
                "tradeoff_quality",
                "history_necessity",
                "interaction_richness",
                "t1_t4_suitability",
            ],
        },
        "rollout_quality_dimensions": list(QUALITY_DIMENSIONS),
        "rollout_hard_reject_reasons": list(HARD_REJECT_REASONS),
        "rollout_screening": {
            "protocol": "SocialFlux Rollout Screening Protocol v1",
            "automatic_decisions": ["PASS", "REVIEW", "REJECT"],
            "final_per_scenario": 1,
            "human_audit_questions": [
                "automatic_decision_correct", "incorrect_dimensions", "error_reason",
                "issue_scope", "rule_or_prompt_revision",
            ],
            "winner_requires_human_confirmation": True,
        },
        "task_review_ratings": {
            task_type: sorted(ratings)
            for task_type, ratings in TASK_REVIEW_RATINGS.items()
        },
        "human_review_plan": read_json(HUMAN_REVIEW_PLAN, {}) or {},
        "gate4_review": {
            "format": "socialflux_gate4_double_audit_v2",
            "same_deterministic_sample": True,
            "independent_reviewers": 2,
            "third_reviewer_only_for_disagreement": True,
            "machine_proposal_is_ground_truth": False,
        },
        "task_label_contracts": {
            "T1_state_tracking": {"value_scale": [0, 10], "requires_evidence": True},
            "T2_history_sensitive_merge": {
                "choices": ["A_higher", "similar", "B_higher", "cannot_determine"],
                "requires_evidence": True,
            },
            "T3_counterfactual_choice_effect": {
                "choices": ["decrease", "similar", "increase", "cannot_determine"],
                "horizons": ["immediate", "delayed"],
                "requires_evidence": True,
            },
        },
        "warning": (
            "Browser records are review drafts only. They are not signed Gate 1 "
            "approval or formal human ground truth."
        ),
    }


def load_scenario_records():
    return [(path, read_json(path)) for path in discover_scenario_paths(SCENARIO_DIR)]


def scenario_review_packet(scenario_id):
    registry = read_json(SCENARIO_REVIEW_TEMPLATE, {}) or {}
    return next(
        (item for item in registry.get("records", [])
         if item.get("scenario_id") == scenario_id),
        None,
    )


def load_scenarios():
    return [scenario for _, scenario in load_scenario_records()]


def load_media_assets():
    manifest = read_json(MEDIA_MANIFEST, {}) or {}
    return manifest.get("assets", [])


def load_task_examples():
    """Load T1–T3 review examples without promoting machine answers to GT."""
    packet = read_json(TASK_EXAMPLES, {}) or {}
    examples = []
    for source in packet.get("examples", []):
        item = dict(source)
        media = dict(item.get("media", {}))
        target = (ROOT / Path(media.get("path", ""))).resolve()
        media_root = TASK_EXAMPLE_MEDIA_ROOT.resolve()
        if media_root in target.parents and target.is_file():
            checksum = hashlib.sha256(target.read_bytes()).hexdigest()
            media.update({"status": "generated", "video_sha256": checksum,
                          "url": f"/task-media/{target.name}?v={checksum[:12]}"})
        elif ((ROOT / "media" / "talking_head" / "assets").resolve() in target.parents
              and target.is_file()):
            checksum = hashlib.sha256(target.read_bytes()).hexdigest()
            manifest_record = next(
                (record for record in load_media_assets()
                 if record.get("asset_id") == media.get("asset_id")),
                {},
            )

            media.update({"status": "generated", "video_sha256": checksum,
                          "quality_status": manifest_record.get("quality_status"),
                          "quality_checks": manifest_record.get("quality_checks", {})})
        elif media.get("shown_to_model"):
            media["status"] = "pending_generation"
        item["media"] = media
        examples.append(item)
    return {**packet, "examples": examples}


def load_t2_expression_dev():
    """Load bounded T2 pairs with program, model, and Codex reviews separated."""
    review_packet = read_json(
        T2_EXPRESSION_DEV_ROOT / "codex_semantic_reviews.json", {}
    ) or {}
    reviews = {
        item.get("scenario_id"): item
        for item in review_packet.get("records", [])
    }
    pairs = []
    for path in sorted(T2_EXPRESSION_DEV_ROOT.glob("pair_*.json")):
        pair = read_json(path, {}) or {}
        pair["codex_semantic_review"] = reviews.get(pair.get("scenario_id"), {})
        pairs.append(pair)
    codex_counts = {}
    for pair in pairs:
        decision = pair["codex_semantic_review"].get("decision", "pending")
        codex_counts[decision] = codex_counts.get(decision, 0) + 1
    return {
        "format": "socialflux_t2_expression_human_review_v1",
        "summary": read_json(T2_EXPRESSION_DEV_ROOT / "summary.json", {}) or {},
        "pairs": pairs,
        "codex_semantic_review_counts": codex_counts,
        "human_review": "pending",
        "media_status": "not_generated",
    }


def load_screening_report():
    return read_json(SCREENING_REPORT, {}) or {}


def load_long_rollout_progress():
    return read_json(LONG_ROLLOUT_ROOT / "progress.json", {}) or {}


def long_rollout_summary(scenario_id=None):
    progress = load_long_rollout_progress()
    completed = list(progress.get("completed_slots", {}).values())
    attempts = progress.get("attempts", [])
    if scenario_id:
        completed = [item for item in completed if item.get("scenario_id") == scenario_id]
        attempts = [item for item in attempts if item.get("scenario_id") == scenario_id]
        expected = (
            progress.get("expected_slot_count", 0) // max(len(load_scenarios()), 1)
            if progress else 0
        )
    else:
        expected = progress.get("expected_slot_count", 0)
    return {
        "status": progress.get("status") or (
            "in_progress" if progress else "not_started"
        ),
        "required_turns": progress.get("required_turns", 20),
        "expected_slot_count": expected,
        "completed_slot_count": len(completed),
        "visible_attempt_count": sum(
            bool(item.get("trajectory_file") or item.get("partial_trajectory_file"))
            for item in attempts
        ),
        "machine_rejected_attempt_count": sum(
            str(item.get("status", "")).endswith("rejected") for item in attempts
        ),
        "generation_error_count": sum(
            item.get("status") == "generation_error" for item in attempts
        ),
        "updated_at_utc": progress.get("updated_at_utc", ""),
        "evidence_status": "development_raw_pending_judge_history_and_human_review",
    }


def _review_file_status(path):
    value = read_json(path, {}) or {}
    record = value.get("record", value)
    return {
        "exists": path.exists(),
        "human_attestation": record.get("human_attestation") is True,
        "reviewers": record.get("reviewers", []),
        "reviewed_at_utc": record.get("reviewed_at_utc", ""),
    }


def human_review_workspace():
    value = read_json(HUMAN_REVIEW_WORKSPACE, {}) or {}
    if value.get("format") != "socialflux_human_review_workspace_v1":
        return {
            "format": "socialflux_human_review_workspace_v1",
            "staffing_plan": read_json(HUMAN_REVIEW_PLAN, {}) or {},
            "gate2": {},
            "gate4": read_json(TASK_REVIEW_SAMPLE, {}) or {},
            "warning": "Run scripts/prepare_human_review_workspace.py to materialize review packets.",
        }
    return value


def manual_review_catalog():
    """Expose every human-facing stage, including not-yet-generated packets."""
    screening = load_screening_report()
    summary = screening.get("summary", {})
    scenario_records = (read_json(SCENARIO_REVIEW_TEMPLATE, {}) or {}).get("records", [])
    media_count = len(load_media_assets())
    task_count = sum(len(load_instances(item["scenario_id"])) for item in load_scenarios())
    workspace = human_review_workspace()
    task_sample = workspace.get("gate4", {}).get("sampling", {}).get("sample_count", 0)
    gate3_primary = workspace.get("gate3", {}).get("primary_count", summary.get("active_candidate_count", 0))
    gate3_secondary = workspace.get("gate3", {}).get("secondary_audit_count", 0)
    environment_files = {
        name: _review_file_status(FORMAL_ENVIRONMENT_DIR / name)
        for name in (
            "state_transition_agreement.json", "trajectory_plausibility.json",
            "history_intervention.json", "paraphrase_robustness.json",
            "local_counterfactual.json", "backbone_sensitivity.json",
            "persona_intervention.json", "video_state_consistency.json",
            "timescale_validity.json",
        )
    }
    long_summary = long_rollout_summary()
    quality_report = read_json(QUALITY_GATE_REPORT, {}) or {}
    quality_status = {
        key: value.get("status", "pending")
        for key, value in quality_report.get("gates", {}).items()
    }
    gate3_required = long_summary.get("expected_slot_count", 0)
    gate4_plan = workspace.get("staffing_plan", {}).get("gate4", {})
    gate4_target = 3 * max(
        gate4_plan.get("minimum_sample_per_task_type", 2),
        math.ceil(len(scenario_records) * gate4_plan.get("sample_fraction_per_task_type", 0.1)),
    )
    categories = [
        ["long_rollout_generation", "最多20轮自然结束候选池",
         long_summary["visible_attempt_count"], long_summary["expected_slot_count"],
         long_summary["status"], "每个 approved scenario 只生成 1 条自然 rollout；失败计入产率，不补抽。", "Rollout筛选"],
        ["scale20_pilot", "历史 Scale20 审核框架",
         0, 0, "archived",
         "旧模型 rollout 已归档；页面和标注合同保留，等待新批次 manifest。", "历史人审"],
        ["gate1_scenario", "Gate 1 · Scenario 与 initial state 冻结", len(scenario_records), len(scenario_records),
         quality_status.get("gate_1_scenario_quality", "pending"), "人物、冲突、initial state、视频阈值、来源原创化及姓名/时间/哈希；runtime dynamics seed 仅做机器校验。", "Scenario 情节"],
        ["gate2_environment", "Gate 2 · Environment Validity（1 人实验复核）",
         sum(value["exists"] for value in environment_files.values()), 9,
         quality_status.get("gate_2_environment_validity", "pending"), "E1/E2 为确定性抽样；E3/E4/E5/E7 自动干预后由 1 人复核；E6 双 backbone；E8 视频状态一致性；E9 timescale validity。", "人审工作台 · Gate 2"],
        ["gate3_rollout", "Gate 3 · Rollout Screening",
         gate3_primary, gate3_required,
         quality_status.get("gate_3_rollout_quality", "pending"), f"主审优先看 {gate3_primary} 条 active candidates；第二人确定性 audit {gate3_secondary} 条。Archive 同步可见，人工可复核，但不会被自动伪装成通过。", "Rollout 筛选 + 人审工作台 audit 清单"],
        ["gate4_tasks", "Gate 4 · 两人同样本独立抽查", task_sample, gate4_target,
         quality_status.get("gate_4_task_instance_quality", "pending"), f"当前 {task_count} 个机器建议答案；目标按 task type 确定性抽取 {gate4_target} 个。两人看同一批，分歧才交第三人。", "人审工作台 · Gate 4"],
        ["media", "Talking Head · 可选媒体审核", media_count, media_count,
         "no_active_assets" if media_count == 0 else "pending_human",
         "旧素材与本地引擎已永久删除；接入外部 API 并生成新批次后，再审核人物连续性、语音自然度和多模态信息效用。", "Scenario 情节"],
        ["filter_holdout", "筛选器校准与 Holdout", 0, 1,
         "pending_split_and_labels", "检查误收/误拒、人机一致性；holdout 通过后才 freeze。", "本页协议"],
        ["dataset_audit", "原创性、污染与公开信息泄漏", 20, 20,
         "pending_human", "影视只保留高层机制，无角色/台词/情节复制；公开输入不泄漏私有状态。", "Scenario 与原始材料"],
    ]
    return {
        "format": "socialflux_manual_review_catalog_v1",
        "categories": [
            dict(zip(("id", "title", "available", "required", "status", "description", "location"), item))
            for item in categories
        ],
        "environment_files": environment_files,
        "screening_summary": summary,
        "long_rollout_generation": long_summary,
        "staffing_plan": workspace.get("staffing_plan", {}),
        "model_stack": workspace.get("model_stack", {}),
        "r3_current_diagnostic_review": load_r3_diagnostic_review(),
        "protocol_document": (ROOT / "docs" / "protocols" / "SocialFlux_Rollout_Screening_Protocol_v1.md").read_text(encoding="utf-8"),
        "warning": "未生成、未实名签署或仅有开发数据的项目明确保持 pending。",
    }


def _scenario_record(scenario_id):
    return next(
        (
            (path, scenario)
            for path, scenario in load_scenario_records()
            if scenario["scenario_id"] == scenario_id
        ),
        None,
    )


def load_instances(scenario_id):
    proposals = {
        item.get("instance_id"): item.get("proposal")
        for item in (read_json(MACHINE_TASK_PROPOSALS, {}) or {}).get("records", [])
    }
    interventions = read_json(
        PIPELINE_DIR / scenario_id / "validation" / "local_action_interventions.json",
        [],
    ) or []
    by_checkpoint = {}
    for branch in interventions:
        key = (branch.get("source_trajectory_id"), branch.get("checkpoint_turn_id"))
        by_checkpoint.setdefault(key, []).append(branch)
    records = []
    for item in read_jsonl(PIPELINE_DIR / scenario_id / "offline" / "instances.jsonl"):
        metadata = item.get("metadata", {})
        key = (metadata.get("source_trajectory_id"), metadata.get("checkpoint_turn_id"))
        records.append({
            **item,
            "machine_proposal": proposals.get(item.get("instance_id"), {
                "status": "not_generated"
            }),
            "counterfactual_diagnostics": by_checkpoint.get(key, []),
        })
    return records

def _pipeline_summary(scenario_id):
    return read_json(PIPELINE_DIR / scenario_id / "pipeline_manifest.json", {}) or {}


def scenario_summary(scenario, source_path):
    pipeline = _pipeline_summary(scenario["scenario_id"])
    bundle = source_path.parent
    active_rollouts = long_rollout_summary(scenario["scenario_id"])["completed_slot_count"]
    trajectory_count = pipeline.get("trajectory_count", active_rollouts)
    screening = load_screening_report().get("scenarios", {}).get(scenario["scenario_id"], {})
    return {
        "scenario_id": scenario["scenario_id"],
        "title": scenario["title"],
        "mechanism": scenario["mechanism"],
        "source_type": scenario["source"]["type"],
        "quality_gate": scenario["construction_status"]["quality_gate"],
        "initial_state_status": scenario["construction_status"]["initial_state"],
        "background": scenario["background"],
        "persona": scenario["environment_agent"].get("persona", {}),
        "selected_state_variables": scenario.get("selected_state_variables", {}),
        "trigger_count": len(scenario.get("video_triggers", [])),
        "max_turns": scenario["max_turns"],
        "task_count": sum(pipeline.get(key, 0) for key in ("t1", "t2", "t3")),
        "scenario_bundle": bundle.relative_to(ROOT).as_posix(),
        "rollout_bundle": (bundle / "rollouts").relative_to(ROOT).as_posix(),
        "pipeline": {
            "trajectory_count": trajectory_count,
            "t1": pipeline.get("t1", 0),
            "t2": pipeline.get("t2", 0),
            "t3": pipeline.get("t3", 0),
            "available": bool(pipeline),
        },
        "screening": {
            "candidate_count": screening.get("candidate_count", trajectory_count),
            "final_trajectory_count": 1 if screening.get("provisional_selected_id") else 0,
            "provisional_selected_id": screening.get("provisional_selected_id"),
            "selection_status": screening.get("selection_status", "not_generated"),
        },
    }


def acceptance_report():
    return read_json(ACCEPTANCE_DIR / "acceptance_report.json", {
        "criteria": [],
        "gate": {
            "automated_artifacts_ready": False,
            "research_acceptance": False,
        },
    })


def _legacy_rollouts(scenario_id):
    screening_records = [
        item for item in load_screening_report().get("records", [])
        if item.get("scenario_id") == scenario_id and item.get("human_review_required")
    ]
    if screening_records:
        rollouts = []
        for item in sorted(screening_records, key=lambda value: (
            not value.get("provisional_selected", False),
            value.get("source_stage") != "active_candidate",
            value.get("automatic_decision") != "REVIEW",
            value.get("trajectory_id", ""),
        )):
            target = (ROOT / item["trajectory_path"]).resolve()
            if ROOT not in target.parents or not target.is_file():
                continue
            trajectory = read_json(target)
            if trajectory:
                trajectory["screening"] = item
                rollouts.append(trajectory)
        return rollouts
    record = _scenario_record(scenario_id)
    if record is None:
        return []
    rollout_dir = record[0].parent / "rollouts"
    manifest = read_json(rollout_dir / "manifest.json", {}) or {}
    if manifest.get("config", {}).get("origin") != "free_form_model_interaction":
        return []
    rollouts = []
    for trajectory_id in manifest.get("trajectory_ids", []):
        trajectory = read_json(rollout_dir / f"{trajectory_id}.json")
        if trajectory:
            trajectory.setdefault("screening", {
                "automatic_decision": "UNSCREENED",
                "candidate_classification": "legacy_manifest_candidate",
                "human_review_required": True,
                "human_review_reasons": [
                    "Legacy free-form rollout has no bound screening record."
                ],
            })
            rollouts.append(trajectory)
    return rollouts


def _scenario_fingerprint(scenario):
    payload = json.dumps(
        scenario, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_long_rollouts(scenario_id):
    record = _scenario_record(scenario_id)
    if record is None:
        return []
    current_scenario_fingerprint = _scenario_fingerprint(record[1])
    rollouts = []
    seen = set()
    for rollout_root in ROLLOUT_REVIEW_ROOTS:
        scenario_dir = rollout_root / record[0].parent.name
        progress = read_json(rollout_root / "progress.json", {}) or {}
        attempts = {}
        for item in progress.get("attempts", []):
            if item.get("scenario_id") != scenario_id:
                continue
            for key in ("trajectory_id", "partial_trajectory_id"):
                trajectory_id = item.get(key)
                if trajectory_id:
                    attempts[trajectory_id] = item
        paths = sorted(scenario_dir.glob("*.json"))
        for archive in ("short_trajectories", "budget_truncated", "rejected"):
            paths += sorted((scenario_dir / archive).glob("*.json"))
        for path in paths:
            if path.name == "manifest.json":
                continue
            trajectory = read_json(path)
            trajectory_id = (trajectory or {}).get("trajectory_id")
            if not trajectory or not trajectory.get("turns") or trajectory_id in seen:
                continue
            seen.add(trajectory_id)
            trajectory["scenario_version_matches_current"] = (
                trajectory.get("scenario_fingerprint")
                == current_scenario_fingerprint
            )
            attempt = attempts.get(trajectory_id, {})
            classification = attempt.get("status") or {
                "short_trajectories": "short_natural_trajectory",
                "budget_truncated": "budget_truncated",
                "rejected": "machine_rejected",
            }.get(path.parent.name, "unknown")
            accepted = classification == "accepted" and path.parent == scenario_dir
            source_stage = {
                "accepted": "newrequest_main_candidate_10_to_20",
                "short_natural_trajectory": "newrequest_short_natural_archive",
                "budget_truncated": "newrequest_budget_truncated_archive",
                "generation_error": "newrequest_partial_generation_error",
            }.get(classification, "newrequest_machine_rejected_attempt")
            rationale = {
                "accepted": "10–20 turn natural-ending machine precheck passed; semantic and human review pending.",
                "short_natural_trajectory": "Conversation ended naturally before turn 10; retained for review, not padded.",
                "budget_truncated": "Generation reached the 20-turn budget without a natural ending.",
                "generation_error": "A complete partial trajectory was retained before generation stopped.",
            }.get(classification, "Generation attempt failed a hard machine check.")
            precheck = attempt.get("precheck", {})
            hard = precheck.get("hard_reject_reasons", [])
            trajectory["screening"] = {
                "automatic_decision": "PENDING" if accepted else "REVIEW",
                "scores": {},
                "mean_quality_score": None,
                "source_stage": source_stage,
                "source_root": str(rollout_root.relative_to(ROOT)),
                "candidate_classification": classification,
                "observed_outcome": infer_observed_outcome(trajectory),
                "turn_evidence": {"judge_turn_evidence_complete": False},
                "judge_rationale": rationale,
                "hard_failures": hard,
                "missing_evidence": list(QUALITY_DIMENSIONS),
                "protocol_contract_warnings": [
                    "pending_rollout_judge_v2", "pending_history_dependence",
                    "pending_human_comparative_review",
                ],
                "provisional_selected": False,
                "human_review_required": True,
                "human_review_reasons": [
                    "Raw candidate is visible for semantic and human review; machine status is not human acceptance."
                ],
                "generation_attempt": attempt.get("attempt"),
                "precheck": precheck,
            }
            rollouts.append(trajectory)
    return rollouts


def load_rollouts(scenario_id):
    if load_long_rollout_progress():
        rollouts = load_long_rollouts(scenario_id)
    else:
        rollouts = _legacy_rollouts(scenario_id)
    diagnostic = _r3_diagnostic_trajectory(scenario_id)
    if diagnostic and not any(
        item.get("trajectory_id") == diagnostic.get("trajectory_id") for item in rollouts
    ):
        if any(item.get("scenario_version_matches_current") for item in rollouts):
            rollouts.append(diagnostic)
        else:
            rollouts.insert(0, diagnostic)
    return rollouts


def scenario_detail(scenario_id):
    record = _scenario_record(scenario_id)
    if record is None:
        return None
    source_path, scenario = record
    active_bundle = LONG_ROLLOUT_ROOT / source_path.parent.name
    dialogue_path = active_bundle / "dialogues.md"
    task_review_path = PIPELINE_DIR / scenario_id / "tasks.md"
    screening = load_screening_report()
    initial_observation = build_initial_policy_observation(scenario)
    prompt_id = "task_t4_action_v21"
    model_contract = {
        "prompt_id": prompt_id,
        "horizon_turns": 20,
        "role_card": scenario["evaluated_agent_role"],
        "public_observation_fields": list(PUBLIC_OBSERVATION_FIELDS),
        "private_author_fields_excluded": list(PRIVATE_AUTHOR_FIELDS),
        "initial_observation": initial_observation,
        "prompt_template": get_prompt(prompt_id),
        "rendered_initial_prompt": render_prompt(prompt_id, initial_observation),
        "boundary_note": (
            "网页向研究者展示 persona/hidden intention/initial state/runtime dynamics seed；这些作者侧私有信息"
            "不会进入被测模型 observation。"
        ),
    }
    return {
        "summary": scenario_summary(scenario, source_path),
        "evaluated_model_contract": model_contract,
        "scenario": scenario,
        "gate1_review_packet": scenario_review_packet(scenario_id),
        "documentation": source_path.with_suffix(".md").read_text(encoding="utf-8"),
        "rollout_dialogues": (
            dialogue_path.read_text(encoding="utf-8")
            if dialogue_path.exists()
            and "Free-form Rollout Dialogues" in dialogue_path.read_text(encoding="utf-8")
            else ""
        ),
        "task_review": (
            task_review_path.read_text(encoding="utf-8")
            if task_review_path.exists()
            and "T1/T2/T3 人工抽查包" in task_review_path.read_text(encoding="utf-8")
            else ""
        ),
        "rollouts": load_rollouts(scenario_id),
        "instances": load_instances(scenario_id),
        "task_source_selection": _pipeline_summary(scenario_id).get(
            "task_source_selection", {}
        ),
        "screening": screening.get("scenarios", {}).get(scenario_id, {}),
        "long_rollout_generation": long_rollout_summary(scenario_id),
        "media_assets": [
            {
                **asset,
                "url": (
                    f"/media/{asset['asset_id']}?v="
                    f"{asset.get('video_sha256', 'pending')[:12]}"
                ),
            }
            for asset in load_media_assets()
            if asset.get("scenario_id") == scenario_id
        ],
    }

def api_payload(path):
    parts = [unquote(part) for part in path.strip("/").split("/") if part]
    # GPT50 is the active workbench. Resolve it before loading the unrelated
    # legacy scenario catalog so rollout polling stays lightweight.
    if parts == ["api", "gpt50-review"]:
        return load_gpt50_review()
    if parts == ["api", "gpt50-rollout"]:
        return load_gpt50_rollout_progress()
    if len(parts) == 3 and parts[:2] == ["api", "gpt50-rollout"]:
        return load_gpt50_rollout(parts[2])
    if len(parts) == 3 and parts[:2] == ["api", "gpt50-scenario"]:
        return load_gpt50_scenario(parts[2])
    records = load_scenario_records()
    catalog = read_json(SCENARIO_DIR / "manifest.json", {}) or {}
    if parts == ["api", "health"]:
        return {"ok": True, "scenario_count": len(records), "pipeline_version": "20turn-selected-v1", "site_mode": "annotation_workbench"}
    if parts == ["api", "annotation-contract"]:
        return annotation_contract()
    if parts == ["api", "task-examples"]:
        return load_task_examples()
    if parts == ["api", "t2-expression-dev"]:
        return load_t2_expression_dev()
    if parts == ["api", "gate1-review"]:
        return read_json(SCENARIO_REVIEW_TEMPLATE, {}) or {}
    if parts == ["api", "manual-review"]:
        return manual_review_catalog()
    if parts == ["api", "scale20-pilot"]:
        return load_scale20_pilot_review()
    if parts == ["api", "scale20-review"]:
        return load_scale20_combined_review()
    if parts == ["api", "gpt50-review"]:
        return load_gpt50_review()
    if parts == ["api", "gpt50-rollout"]:
        return load_gpt50_rollout_progress()
    if len(parts) == 3 and parts[:2] == ["api", "gpt50-scenario"]:
        return load_gpt50_scenario(parts[2])
    if parts == ["api", "scale150-review"]:
        return load_scale150_review()
    if parts == ["api", "scale300-tasks"]:
        return load_scale300_task_review()
    if len(parts) == 3 and parts[:2] == ["api", "scale300-task"]:
        return load_scale300_task_package(parts[2])
    if len(parts) == 3 and parts[:2] == ["api", "scale150-scenario"]:
        return load_scale150_scenario(parts[2])
    if len(parts) == 3 and parts[:2] == ["api", "scale150-trajectory"]:
        return load_scale150_trajectory(parts[2])
    if parts == ["api", "review-workspace"]:
        return human_review_workspace()
    if parts == ["api", "summary"]:
        return {
            "scenario_count": len(records),
            "source_counts": catalog.get("source_counts", {}),
            "scenarios": [scenario_summary(scenario, path) for path, scenario in records],
            "pipeline_manifest": read_json(PIPELINE_DIR / "manifest.json", {}) or {},
            "acceptance": acceptance_report(),
            "quality_gates": read_json(QUALITY_GATE_REPORT, {}) or {},
            "screening": load_screening_report().get("summary", {}),
            "long_rollout_generation": long_rollout_summary(),
            "manual_review": manual_review_catalog(),
            "review_workspace": human_review_workspace(),
            "scale20_pilot": {
                key: value for key, value in load_scale20_pilot_review().items()
                if key in {"status", "quality_version", "configuration_summary", "generation_summary", "request_budget", "task_availability"}
            },
            "scale20_review": {
                key: value for key, value in load_scale20_full20_review().items()
                if key in {"status", "quality_version", "generated_scenario_count", "selected_trajectory_count", "total_turns", "generation_status_counts", "model_semantic_review_counts", "actual_request_counts"}
            },
        }
    if parts == ["api", "scenarios"]:
        return {
            "scenarios": [
                scenario_summary(scenario, path)
                for path, scenario in records
            ]
        }
    if len(parts) == 3 and parts[:2] == ["api", "scenarios"]:
        return scenario_detail(parts[2])
    return None


class App(SimpleHTTPRequestHandler):
    auth_username = None
    auth_password = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def end_headers(self):
        static_path = urlparse(self.path).path
        if static_path.endswith((".html", ".js", ".css")):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def authenticate(self):
        if self.auth_username is None or self.auth_password is None:
            return True
        if credentials_match(
            self.headers.get("Authorization"),
            self.auth_username,
            self.auth_password,
        ):
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="SocialFlux", charset="UTF-8"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def do_GET(self):
        if not self.authenticate():
            return
        parsed = urlparse(self.path)
        if parsed.path.startswith("/task-media/"):
            filename = unquote(parsed.path.removeprefix("/task-media/"))
            target = (TASK_EXAMPLE_MEDIA_ROOT / filename).resolve()
            media_root = TASK_EXAMPLE_MEDIA_ROOT.resolve()
            if (
                target.parent != media_root
                or target.suffix.lower() != ".mp4"
                or not target.is_file()
            ):
                self.send_error(404, "task media not found")
                return
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(target.stat().st_size))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            with target.open("rb") as stream:
                shutil.copyfileobj(stream, self.wfile)
            return
        if parsed.path.startswith("/media/"):
            asset_id = unquote(parsed.path.removeprefix("/media/"))
            asset = next(
                (item for item in load_media_assets() if item.get("asset_id") == asset_id),
                None,
            )
            if not asset or asset.get("status") != "generated":
                self.send_error(404, "media asset not found")
                return
            target = (ROOT / asset["video_path"]).resolve()
            asset_root = (ROOT / "media" / "talking_head" / "assets").resolve()
            if asset_root not in target.parents or not target.is_file():
                self.send_error(404, "media asset not found")
                return
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(target.stat().st_size))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            with target.open("rb") as stream:
                shutil.copyfileobj(stream, self.wfile)
            return
        if parsed.path.startswith("/api/"):
            payload = api_payload(parsed.path)
            self.send_json(payload if payload is not None else {"error": "not found"},
                           200 if payload is not None else 404)
            return
        legacy_review_pages = {
            "/index.html",
            "/review.html",
            "/scale150.html",
            "/scale300_tasks.html",
            "/t2_dev_review.html",
        }
        if parsed.path in ("/", "", "/gpt50", "/gpt50/"):
            self.path = "/gpt50_gate1.html"
        elif parsed.path in legacy_review_pages:
            self.path = "/gpt50_gate1.html"
        super().do_GET()

    def log_message(self, format, *args):
        print("[web] " + format % args)


def main():
    parser = argparse.ArgumentParser(description="Serve the SocialFlux annotation workbench")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--username", default="socialflux")
    parser.add_argument("--password-file", type=Path)
    args = parser.parse_args()
    if args.password_file:
        password = args.password_file.read_text(encoding="utf-8").strip()
        if not password:
            parser.error("--password-file must not be empty")
        App.auth_username = args.username
        App.auth_password = password
    elif args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("public binding requires --password-file")
    server = ThreadingHTTPServer((args.host, args.port), App)
    print(f"SocialFlux Annotation Studio: http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
