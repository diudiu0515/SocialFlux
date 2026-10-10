#!/usr/bin/env python3
"""Run one bounded state-only Fable probe on frozen v7 materials."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from environment.calibration import DeterministicStateCalibrator
from environment.independent_appraisal import ModelStateAppraiser
from providers.factory import build_provider, public_provider_config
from prompts.loader import prompt_manifest
from rollout.configuration import load_rollout_config


BASE = ROOT / "data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary"
DEFAULT_POSITIVES = BASE / "human_confirmed_fixed_set.json"
DEFAULT_NEGATIVES = BASE / "negative_control_candidates.json"
DEFAULT_ASTRA_CONFIG = (
    ROOT / "configs/gpt50_experiment"
    / "rollout.state_independent_per_variable_v3_state_judgment_primary_candidate.json"
)
DEFAULT_FABLE_CONFIG = (
    ROOT / "configs/gpt50_experiment"
    / "rollout.state_v3_2_20_claude_independent_appraisal_audit_candidate.json"
)
DEFAULT_PREREG = BASE / "fable_state_only_probe_preregistration.json"
DEFAULT_OUTPUT = BASE / "fable_state_only_probe_results.json"
PROMPT_ID = "environment_state_appraisal_v4_definition_grounded"
PROFILE = "state_judgment_primary_hysteretic_v7"
NEW = {"ordinary_new_evidence", "decisive_new_evidence"}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def atomic(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def sha256(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path):
    return str(path.resolve().relative_to(ROOT))


def find_turn(source: dict, turn_id: str):
    return next(turn for turn in source["turns"] if turn["turn_id"] == turn_id)


def build_cases(positive_path: Path, negative_path: Path):
    positives = load(positive_path)
    negatives = load(negative_path)
    cases = []
    for case in positives["cases"]:
        cases.append({
            "case_id": case["case_id"],
            "label_status": "human_confirmed",
            "scenario": case["scenario"],
            "source": case["source"],
            "turn_id": case["turn_id"],
            "target": case["target"],
            "action_override": None,
            "expected_judgment": case["adjudicated_label"]["judgment"],
        })
    for control in negatives["controls"]:
        cases.append({
            "case_id": control["case_id"],
            "label_status": "provisional_pending_human_confirmation",
            "scenario": negatives["scenario"],
            "source": negatives["source"],
            "turn_id": negatives["base_turn_id"],
            "target": negatives["target"],
            "action_override": control["latest_action_override"],
            "expected_judgment": control["proposed_human_label"]["judgment"],
        })
    return cases


def provider_config(fable_config: Path):
    config = load_rollout_config(fable_config)
    value = deepcopy(config["environment"]["provider"])
    value["max_tokens"] = 6000
    for candidate in value.get("candidates", []):
        candidate["max_tokens"] = 6000
    return value


def build_preregistration(args, cases):
    astra = load_rollout_config(args.astra_config)
    sampling = deepcopy(astra["environment"]["state_appraisal_sampling"])
    return {
        "format": "socialflux_state_appraiser_backbone_probe_preregistration_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "preregistered_before_model_calls",
        "purpose": "same v7 semantics and inputs; replace only the state appraiser backbone",
        "model": "claude-fable-5",
        "state_only": True,
        "interaction_calls": 0,
        "repeat_count": 1,
        "rerun_until_pass_prohibited": True,
        "positive_manifest": relative(args.positives),
        "positive_manifest_sha256": sha256(args.positives),
        "negative_controls": relative(args.negatives),
        "negative_controls_sha256": sha256(args.negatives),
        "negative_label_status": "provisional_pending_human_confirmation",
        "prompt": PROMPT_ID,
        "prompt_sha256": prompt_manifest()["prompts"][PROMPT_ID]["sha256"],
        "calibration_profile": PROFILE,
        "sampling": sampling,
        "provider": public_provider_config(provider_config(args.fable_config)),
        "schedule": [case["case_id"] for case in cases],
        "decision_rule": {
            "positive_recognition_minimum": "7/8",
            "positive_recognized_must_update": "all",
            "provisional_negative_controls": "2/2",
            "candidate_density": "reported_not_optimized",
            "if_passed": "eligible_for_unseen_examples_then_small_rollout_only",
            "full_scale_authorized": False,
        },
    }


def target_judgment(state_result: dict, target: str):
    return next(
        (item for item in state_result.get("state_judgments", []) if item.get("variable") == target),
        None,
    )


def run_case(case, provider_value, sampling):
    scenario = load(ROOT / case["scenario"])
    source = load(ROOT / case["source"])
    turn = find_turn(source, case["turn_id"])
    action = (
        {"text": case["action_override"]}
        if case["action_override"] is not None
        else turn["policy_action"]
    )
    provider = build_provider(deepcopy(provider_value))
    appraiser = ModelStateAppraiser(
        scenario, provider, sampling, prompt_id=PROMPT_ID
    )
    try:
        state_result = appraiser.appraise(
            action=action,
            previous_state=turn["state_before"],
            previous_dynamics=turn["dynamics_before"],
            memory=turn["memory_view"],
            longitudinal_context=(turn.get("observation") or {}).get("longitudinal_context"),
            interaction_ledger=turn.get("interaction_ledger_before"),
        )
        transition = DeterministicStateCalibrator(
            scenario, profile=PROFILE
        ).calibrate(
            state_result["appraisal"],
            turn["state_before"],
            turn["dynamics_before"],
            current_event_id=turn["turn_id"],
        )
        judgment = target_judgment(state_result, case["target"])
        observed = judgment.get("judgment") if judgment else None
        family, variable = case["target"].split(".", 1)
        delta = transition["state_delta"][family][variable]
        expected_new = case["expected_judgment"] in NEW
        observed_new = observed in NEW
        audits = deepcopy(getattr(provider, "audit_records", []))
        return {
            "status": "completed",
            "evaluation": {
                "expected_judgment": case["expected_judgment"],
                "observed_judgment": observed,
                "target_recognition_correct": expected_new == observed_new,
                "exact_judgment_correct": observed == case["expected_judgment"],
                "target_delta": delta,
                "recognized_target_updated": observed_new and delta != "similar",
                "new_state_judgment_count": sum(
                    item.get("judgment") in NEW
                    for item in state_result.get("state_judgments", [])
                ),
                "selected_state_candidate_count": sum(
                    item.get("selected", False)
                    for item in transition["calibration"]["state_impacts"]
                ),
                "call_complete": bool(audits) and all(item.get("complete") is True for item in audits),
            },
            "target_judgment": judgment,
            "state_appraisal": state_result,
            "calibration": transition["calibration"],
            "provider_public_config": public_provider_config(provider_value),
            "provider_metrics": deepcopy(provider.metrics),
        }
    except Exception as exc:
        return {
            "status": "call_failure",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "exception_raw_output": getattr(exc, "raw_output", None),
            "finish_reason": getattr(exc, "finish_reason", None),
            "diagnostics": getattr(exc, "diagnostics", None),
            "actual_requests": deepcopy(getattr(provider, "audit_records", [])),
            "provider_metrics": deepcopy(provider.metrics),
        }


def summarize(rows, corrections=None):
    effective = {row["case_id"]: row for row in rows}
    for row in corrections or []:
        effective[row["case_id"]] = row
    effective_rows = list(effective.values())
    completed = [
        row for row in effective_rows
        if row["result"].get("status") == "completed"
    ]
    positive_rows = [
        row for row in effective_rows
        if row["case"]["label_status"] == "human_confirmed"
    ]
    negative_rows = [
        row for row in effective_rows
        if row["case"]["label_status"].startswith("provisional")
    ]
    positives = [
        row for row in positive_rows
        if row["result"].get("status") == "completed"
    ]
    negatives = [
        row for row in negative_rows
        if row["result"].get("status") == "completed"
    ]
    evaluations = [row["result"]["evaluation"] for row in completed]
    return {
        "scheduled": len(effective_rows),
        "completed": len(completed),
        "call_failures": len(effective_rows) - len(completed),
        "complete_calls": sum(item["call_complete"] for item in evaluations),
        "positive_target_recognition": sum(
            row["result"]["evaluation"]["target_recognition_correct"] for row in positives
        ),
        "positive_recognized": sum(
            row["result"]["evaluation"]["observed_judgment"] in NEW
            for row in positives
        ),
        "positive_total": len(positive_rows),
        "positive_recognized_target_updated": sum(
            (
                row["result"]["evaluation"]["observed_judgment"] in NEW
                and row["result"]["evaluation"]["target_delta"] != "similar"
            )
            for row in positives
        ),
        "provisional_negative_correct": sum(
            row["result"]["evaluation"]["target_recognition_correct"] for row in negatives
        ),
        "provisional_negative_total": len(negative_rows),
        "mean_new_state_judgments": (
            sum(item["new_state_judgment_count"] for item in evaluations) / len(evaluations)
            if evaluations else None
        ),
        "mean_selected_state_candidates": (
            sum(item["selected_state_candidate_count"] for item in evaluations) / len(evaluations)
            if evaluations else None
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--positives", type=Path, default=DEFAULT_POSITIVES)
    parser.add_argument("--negatives", type=Path, default=DEFAULT_NEGATIVES)
    parser.add_argument("--astra-config", type=Path, default=DEFAULT_ASTRA_CONFIG)
    parser.add_argument("--fable-config", type=Path, default=DEFAULT_FABLE_CONFIG)
    parser.add_argument("--preregistration", type=Path, default=DEFAULT_PREREG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--correct-pre-provider-action-shape", action="store_true")
    args = parser.parse_args(argv)
    cases = build_cases(args.positives, args.negatives)
    prereg = build_preregistration(args, cases)
    if args.prepare_only:
        if args.preregistration.exists():
            raise FileExistsError(args.preregistration)
        atomic(args.preregistration, prereg)
        print(json.dumps({"preregistration": str(args.preregistration), "scheduled": len(cases)}, indent=2))
        return
    frozen = load(args.preregistration)
    if frozen["schedule"] != prereg["schedule"]:
        raise ValueError("preregistered schedule differs")
    if args.output.exists() and not args.resume:
        raise FileExistsError(args.output)
    result = {
        "format": "socialflux_state_appraiser_backbone_probe_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "preregistration": relative(args.preregistration),
        "preregistration_sha256": sha256(args.preregistration),
        "model_calls": 0,
        "rows": [],
    }
    if args.resume:
        result = load(args.output)
        result["status"] = "running"
    completed_ids = {row["case_id"] for row in result["rows"]}
    astra = load_rollout_config(args.astra_config)
    sampling = deepcopy(astra["environment"]["state_appraisal_sampling"])
    provider_value = provider_config(args.fable_config)
    for case in cases:
        if case["case_id"] in completed_ids:
            continue
        row = {"case_id": case["case_id"], "case": case, "result": run_case(case, provider_value, sampling)}
        result["rows"].append(row)
        result["model_calls"] += 1
        result["summary"] = summarize(
            result["rows"], result.get("pre_provider_corrections")
        )
        atomic(args.output, result)
    if args.correct_pre_provider_action_shape:
        corrections = result.setdefault("pre_provider_corrections", [])
        corrected_ids = {row["case_id"] for row in corrections}
        case_by_id = {case["case_id"]: case for case in cases}
        for original in result["rows"]:
            failure = original["result"]
            case_id = original["case_id"]
            if (
                case_id in corrected_ids
                or failure.get("status") != "call_failure"
                or failure.get("error_type") != "AttributeError"
                or failure.get("actual_requests")
            ):
                continue
            case = case_by_id[case_id]
            correction = {
                "case_id": case_id,
                "case": case,
                "correction_reason": (
                    "latest_action_override was a string; ModelStateAppraiser "
                    "requires the normal policy-action object shape. No provider "
                    "request occurred in the original attempt."
                ),
                "original_failure": deepcopy(failure),
                "result": run_case(case, provider_value, sampling),
            }
            corrections.append(correction)
            result.setdefault("correction_log", []).append({
                "case_id": case_id,
                "root_cause": "pre-provider action shape mismatch",
                "original_provider_request_count": 0,
                "correction_count": 1,
            })
            result["summary"] = summarize(result["rows"], corrections)
            atomic(args.output, result)
    result["summary"] = summarize(
        result["rows"], result.get("pre_provider_corrections")
    )
    summary = result["summary"]
    positive_gate = (
        summary["positive_target_recognition"] >= 7
        and summary["positive_recognized_target_updated"]
        == summary["positive_recognized"]
    )
    negative_gate = (
        summary["provisional_negative_correct"] == summary["provisional_negative_total"] == 2
    )
    negative_confirmation = load(args.negatives).get("human_confirmation") or {}
    labels_confirmed = negative_confirmation.get("status") == "complete"
    result["post_preregistration_label_confirmation"] = {
        "negative_controls_sha256": sha256(args.negatives),
        "confirmation": negative_confirmation,
        "timing": "confirmed_in_chat_after_preregistration_and_before_provider_calls",
    }
    result["provisional_gate"] = {
        "passed": positive_gate and negative_gate and summary["call_failures"] == 0,
        "label_caveat": (
            "negative controls human-confirmed after preregistration"
            if labels_confirmed
            else "negative controls remain pending human confirmation"
        ),
        "next_step_if_passed": "unseen examples then bounded small rollout; not full scale",
    }
    result["fixed_set_gate"] = {
        "passed": (
            labels_confirmed
            and positive_gate
            and negative_gate
            and summary["call_failures"] == 0
        ),
        "positive_gate": positive_gate,
        "negative_gate": negative_gate,
        "call_completeness_gate": summary["call_failures"] == 0,
        "decision": "stop_before_unseen_and_scale",
    }
    result["status"] = "completed"
    atomic(args.output, result)
    print(json.dumps({"output": str(args.output), "summary": summary, "provisional_gate": result["provisional_gate"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
