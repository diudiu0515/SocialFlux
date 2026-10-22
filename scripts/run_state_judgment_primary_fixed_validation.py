#!/usr/bin/env python3
"""Run the human-confirmed v7 fixed set through independent appraisals only."""

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

from environment.independent_appraisal import ModelInteractionAppraiser, ModelStateAppraiser
from environment.appraisal_context import build_appraisal_context, refreshed_memory
from environment.state_updater import ModelStateUpdater
from providers.factory import build_provider, public_provider_config
from prompts.loader import prompt_manifest
from rollout.configuration import load_rollout_config
from shared.artifacts import atomic_json as atomic


DEFAULT_MANIFEST = (
    ROOT
    / "data/gpt50/experiment/state_v3_validation"
    / "v323_state_judgment_primary/human_confirmed_fixed_set.json"
)
DEFAULT_CONFIG = (
    ROOT
    / "configs/gpt50_experiment"
    / "rollout.state_independent_per_variable_v3_state_judgment_primary_candidate.json"
)
DEFAULT_INTERFACE_AUDIT = (
    ROOT
    / "data/gpt50/experiment/state_v3_validation"
    / "v323_state_judgment_primary/interface_consistency_audit.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "data/gpt50/experiment/state_v3_validation"
    / "v323_state_judgment_primary/human_confirmed_fixed_set_results.json"
)

NEW_JUDGMENTS = {"ordinary_new_evidence", "decisive_new_evidence"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative(path):
    return str(Path(path).resolve().relative_to(ROOT))


def find_turn(source, turn_id):
    return next(item for item in source["turns"] if item["turn_id"] == turn_id)


def target_judgment(transition, target):
    return next((
        item for item in transition.get("state_judgments", [])
        if item.get("variable") == target
    ), None)


def target_delta(transition, target):
    family, variable = target.split(".", 1)
    return transition["state_delta"][family][variable]

def target_calibration(transition, target):
    return next((
        item for item in transition.get("calibration", {}).get("state_impacts", [])
        if item.get("variable") == target
    ), None)



def call_completeness(transition):
    logical_calls = [
        transition.get("state_appraisal_call", {}),
        transition.get("interaction_appraisal_call", {}),
    ]
    audits = [
        audit
        for call in logical_calls
        for audit in call.get("provider_audit_records", [])
    ]
    return {
        "expected_logical_call_count": 2,
        "logged_actual_request_count": len(audits),
        "all_actual_requests_complete": bool(audits) and all(
            item.get("complete") is True for item in audits
        ),
        "finish_reasons": [item.get("finish_reason") for item in audits],
        "actual_requests": audits,
    }


def evaluate(case, transition):
    expected = case["adjudicated_label"]
    observed = target_judgment(transition, case["target"])
    observed_judgment = observed.get("judgment") if observed else None
    expected_is_new = expected["judgment"] in NEW_JUDGMENTS
    observed_is_new = observed_judgment in NEW_JUDGMENTS
    final_delta = target_delta(transition, case["target"])
    actual_update = final_delta != "similar"
    calibrated = target_calibration(transition, case["target"])
    calibrated_delta = calibrated.get("final_delta") if calibrated else "similar"
    update_opinion = expected.get("reviewer_update_opinion")
    update_opinion_match = (
        None if update_opinion is None
        else actual_update == update_opinion
    )
    completeness = call_completeness(transition)
    return {
        "target": case["target"],
        "human_adjudicated_label": deepcopy(expected),
        "observed_target_judgment": deepcopy(observed),
        "observed_judgment": observed_judgment,
        "variable_recognition_pass": expected_is_new == observed_is_new,
        "judgment_classification_pass": observed_judgment == expected["judgment"],
        "evidence_strength_pass": bool(
            observed
            and observed.get("semantic_strength") == expected["semantic_strength"]
        ),
        "false_positive": (not expected_is_new) and observed_is_new,
        "false_negative": expected_is_new and (not observed_is_new),
        "final_delta": final_delta,
        "actual_nonzero_update": actual_update,
        "calibration_target_diagnostic": deepcopy(calibrated),
        "final_update_integrity_pass": final_delta == calibrated_delta,
        "reviewer_update_opinion": update_opinion,
        "reviewer_update_opinion_match": update_opinion_match,
        "call_completeness": completeness,
        "call_completeness_pass": completeness["all_actual_requests_complete"],
    }


def common_kwargs(turn, source_turns):
    current_number = int(str(turn["turn_id"]).lstrip("t"))
    prior_turns = [
        item for item in source_turns
        if int(str(item.get("turn_id", "t0")).lstrip("t")) < current_number
    ]
    history = (turn.get("observation") or {}).get("history", [])
    appraisal_context = build_appraisal_context(
        history=history,
        turns=prior_turns,
        action=turn["policy_action"],
        current_turn_id=turn["turn_id"],
        interaction_ledger=turn.get("interaction_ledger_before"),
        longitudinal_context=(turn.get("observation") or {}).get(
            "longitudinal_context"
        ),
    )
    return {
        "action": turn["policy_action"],
        "previous_state": turn["state_before"],
        "previous_dynamics": turn["dynamics_before"],
        "memory": refreshed_memory(turn["memory_view"], appraisal_context),
        "longitudinal_context": (turn.get("observation") or {}).get(
            "longitudinal_context"
        ),
        "interaction_ledger": turn.get("interaction_ledger_before"),
        "current_event_id": turn["turn_id"],
        "appraisal_context": appraisal_context,
    }


def exception_record(exc, providers):
    audits = []
    metrics = []
    for provider in providers:
        audits.extend(deepcopy(getattr(provider, "audit_records", [])))
        metrics.append(deepcopy(getattr(provider, "metrics", {})))
    return {
        "status": "call_failure",
        "error_type": type(exc).__name__,
        "error": str(exc),
        "exception_raw_output": getattr(exc, "raw_output", None),
        "finish_reason": getattr(exc, "finish_reason", None),
        "diagnostics": getattr(exc, "diagnostics", None),
        "actual_requests": audits,
        "provider_metrics": metrics,
    }


def run_independent(case, scenario, turn, config, source_turns):
    environment = config["environment"]
    state_provider = build_provider(
        environment.get("state_appraisal_provider", environment["provider"])
    )
    interaction_provider = build_provider(
        environment.get("interaction_appraisal_provider", environment["provider"])
    )
    updater = ModelStateUpdater(
        scenario,
        state_provider,
        environment["state_appraisal_sampling"],
        state_appraiser=ModelStateAppraiser(
            scenario,
            state_provider,
            environment["state_appraisal_sampling"],
            prompt_id=environment["state_appraisal_prompt_id"],
        ),
        interaction_appraiser=ModelInteractionAppraiser(
            scenario,
            interaction_provider,
            environment["interaction_appraisal_sampling"],
            prompt_id=environment["interaction_appraisal_prompt_id"],
        ),
        calibration_profile=environment["state_calibration_profile"],
    )
    try:
        transition = updater.update(**common_kwargs(turn, source_turns))
    except Exception as exc:
        return exception_record(exc, [state_provider, interaction_provider])
    return {
        "status": "completed",
        "evaluation": evaluate(case, transition),
        "transition": transition,
        "provider_metrics": {
            "state": deepcopy(state_provider.metrics),
            "interaction": deepcopy(interaction_provider.metrics),
        },
    }


def validate_inputs(manifest, config, interface_audit):
    if manifest.get("format") != "socialflux_human_confirmed_state_fixed_set_v1":
        raise ValueError("runner requires a human-confirmed fixed-set manifest")
    confirmation = manifest.get("human_confirmation") or {}
    if confirmation.get("status") != "complete":
        raise ValueError("all fixed-set labels must be confirmed by a human")
    if confirmation.get("confirmed_case_count") != len(manifest.get("cases", [])):
        raise ValueError("human confirmation case count is incomplete")
    if any(
        case.get("human_confirmation") != "complete"
        or not case.get("adjudicated_label")
        for case in manifest["cases"]
    ):
        raise ValueError("runner refuses pending or unadjudicated labels")

    environment = config["environment"]
    required = {
        "independent_appraisals": True,
        "interaction_appraisal_prompt_id": "environment_interaction_appraisal_v1",
        "state_calibration_profile": "state_judgment_primary_hysteretic_v7",
        "state_transition_runtime_revision": "v3.2.24",
    }
    mismatches = {
        name: {"expected": expected, "actual": environment.get(name)}
        for name, expected in required.items()
        if environment.get(name) != expected
    }
    if mismatches:
        raise ValueError(f"config is not the audited v7 independent interface: {mismatches}")
    audited_state_prompt = (interface_audit.get("prompt_roles") or {}).get(
        "new_scheme_state"
    )
    if environment.get("state_appraisal_prompt_id") != audited_state_prompt:
        raise ValueError(
            "state prompt does not match the audited independent interface"
        )
    if interface_audit.get("independent_interface_passed") is not True:
        raise ValueError("v7 interface consistency audit did not pass")
    policy = (interface_audit.get("combined_baseline") or {}).get("execution_policy", "")
    if "do_not_call_in_v7_fixed_set" not in policy:
        raise ValueError("interface audit does not prohibit combined baseline calls")


def summarize(rows):
    evaluations = [
        row["result"]["evaluation"]
        for row in rows
        if row["result"].get("status") == "completed"
    ]
    total = len(rows)

    def metric(field):
        return {
            "passed": sum(item.get(field) is True for item in evaluations),
            "total": total,
        }

    return {
        "case_count": total,
        "completed_count": len(evaluations),
        "call_failure_count": total - len(evaluations),
        "variable_recognition": metric("variable_recognition_pass"),
        "judgment_classification": metric("judgment_classification_pass"),
        "evidence_strength": metric("evidence_strength_pass"),
        "false_positive_count": sum(
            item.get("false_positive") is True for item in evaluations
        ),
        "false_negative_count": sum(
            item.get("false_negative") is True for item in evaluations
        ),
        "final_update_observed": {
            "changed": sum(
                item.get("actual_nonzero_update") is True for item in evaluations
            ),
            "unchanged": sum(
                item.get("actual_nonzero_update") is False for item in evaluations
            ),
            "total": len(evaluations),
        },
        "final_update_integrity": metric("final_update_integrity_pass"),
        "reviewer_update_opinion": {
            "provided": sum(item.get("reviewer_update_opinion") is not None for item in evaluations),
            "matched": sum(item.get("reviewer_update_opinion_match") is True for item in evaluations),
        },
        "call_completeness": metric("call_completeness_pass"),
    }


def summary_passes(summary):
    return (
        summary["call_failure_count"] == 0
        and summary["false_positive_count"] == 0
        and summary["false_negative_count"] == 0
        and all(
            summary[name]["passed"] == summary[name]["total"]
            for name in (
                "variable_recognition",
                "judgment_classification",
                "evidence_strength",
                "final_update_integrity",
                "call_completeness",
            )
        )
    )


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--interface-audit", type=Path, default=DEFAULT_INTERFACE_AUDIT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--state-prompt-id")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)

    manifest = load(args.manifest)
    config = load_rollout_config(args.config)
    if args.state_prompt_id:
        config["environment"]["state_appraisal_prompt_id"] = args.state_prompt_id
    interface_audit = load(args.interface_audit)
    validate_inputs(manifest, config, interface_audit)
    if args.output.exists() and not args.resume:
        raise FileExistsError(
            f"refusing to overwrite one-run evidence artifact: {args.output}"
        )

    environment = config["environment"]
    result = {
        "format": "socialflux_state_judgment_primary_fixed_validation_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "execution_policy": {
            "independent_appraisals_only": True,
            "combined_appraisal_calls": 0,
            "all_results_retained": True,
            "rerun_until_pass_prohibited": True,
            "full_scale_authorized": False,
        },
        "manifest": relative(args.manifest),
        "manifest_sha256": sha256(args.manifest),
        "config": relative(args.config),
        "config_sha256": sha256(args.config),
        "interface_audit": relative(args.interface_audit),
        "config_runtime_overrides": {
            "state_appraisal_prompt_id": args.state_prompt_id,
        } if args.state_prompt_id else {},
        "interface_audit_sha256": sha256(args.interface_audit),
        "human_confirmation": deepcopy(manifest["human_confirmation"]),
        "frozen_conditions": {
            "provider": public_provider_config(environment["provider"]),
            "state_prompt": environment["state_appraisal_prompt_id"],
            "interaction_prompt": environment["interaction_appraisal_prompt_id"],
            "state_sampling": environment["state_appraisal_sampling"],
            "state_prompt_sha256": prompt_manifest()["prompts"][
                environment["state_appraisal_prompt_id"]
            ]["sha256"],
            "interaction_sampling": environment["interaction_appraisal_sampling"],
            "calibration_profile": environment["state_calibration_profile"],
            "runtime_revision": environment["state_transition_runtime_revision"],
            "combined_prompt": {
                "id": environment["appraisal_prompt_id"],
                "role": "frozen_reference_only_not_called",
            },
        },
        "fixed_set": [],
        "preplanned_boundary_retest": [],
    }
    if args.resume:
        if not args.output.exists():
            raise FileNotFoundError("--resume requires an existing output artifact")
        checkpoint = load(args.output)
        if checkpoint.get("manifest_sha256") != result["manifest_sha256"]:
            raise ValueError("resume manifest hash differs")
        if checkpoint.get("config_sha256") != result["config_sha256"]:
            raise ValueError("resume config hash differs")
        result = checkpoint
        result["status"] = "running"
        result.setdefault("resume_events", []).append({
            "resumed_at_utc": datetime.now(timezone.utc).isoformat(),
            "reason": "interrupted_process_recovery_only",
        })

    def save():
        result["fixed_set_summary"] = summarize(result["fixed_set"])
        result["boundary_retest_summary"] = summarize(
            result["preplanned_boundary_retest"]
        )
        result["all_counted_results_summary"] = summarize(
            result["fixed_set"] + result["preplanned_boundary_retest"]
        )
        atomic(args.output, result)

    case_by_id = {case["case_id"]: case for case in manifest["cases"]}
    completed_fixed = {row["case_id"] for row in result["fixed_set"]}
    for case in manifest["cases"]:
        if case["case_id"] in completed_fixed:
            continue
        scenario = load(ROOT / case["scenario"])
        source = load(ROOT / case["source"])
        turn = find_turn(source, case["turn_id"])
        row = {
            "case_id": case["case_id"],
            "case": deepcopy(case),
            "result": run_independent(case, scenario, turn, config, source["turns"]),
        }
        result["fixed_set"].append(row)
        save()

    completed_boundary = {
        row["case_id"] for row in result["preplanned_boundary_retest"]
    }
    for case_id in manifest.get("preplanned_boundary_retest_case_ids", []):
        if case_id in completed_boundary:
            continue
        case = case_by_id[case_id]
        scenario = load(ROOT / case["scenario"])
        source = load(ROOT / case["source"])
        turn = find_turn(source, case["turn_id"])
        row = {
            "case_id": case_id,
            "case": deepcopy(case),
            "retest_reason": "preplanned_boundary_retest",
            "result": run_independent(case, scenario, turn, config, source["turns"]),
        }
        result["preplanned_boundary_retest"].append(row)
        save()

    save()
    ambiguous = result["human_confirmation"].get("ambiguous_case_ids", [])
    all_summary = result["all_counted_results_summary"]
    passed = not ambiguous and summary_passes(all_summary)
    result["fixed_set_passed"] = passed
    result["gate_decision"] = (
        "eligible_for_unseen_and_small_rollout_validation"
        if passed
        else "stop_and_report_fixed_set_evidence"
    )
    result["full_scale_authorized"] = False
    result["status"] = "completed"
    save()
    print(json.dumps({
        "output": str(args.output),
        "fixed_set_summary": result["fixed_set_summary"],
        "boundary_retest_summary": result["boundary_retest_summary"],
        "all_counted_results_summary": all_summary,
        "ambiguous_case_ids": ambiguous,
        "fixed_set_passed": passed,
        "gate_decision": result["gate_decision"],
        "full_scale_authorized": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
