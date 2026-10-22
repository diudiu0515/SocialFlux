#!/usr/bin/env python3
"""Run the frozen combined-vs-independent state validation exactly once."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from environment.appraisal import ModelAppraiser
from environment.independent_appraisal import ModelInteractionAppraiser, ModelStateAppraiser
from environment.state_updater import ModelStateUpdater
from providers.factory import build_provider, public_provider_config
from rollout.configuration import load_rollout_config
from shared.artifacts import atomic_json as atomic


DEFAULT_MANIFEST = ROOT / "data/gpt50/experiment/state_v3_validation/v3227_independent_per_variable/fixed_set_preregistration.json"
DEFAULT_OUTPUT = ROOT / "data/gpt50/experiment/state_v3_validation/v3227_independent_per_variable/fixed_set_results.json"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def find_turn(source, turn_id):
    return next(item for item in source["turns"] if item["turn_id"] == turn_id)


def delta_for(transition, target):
    family, variable = target.split(".", 1)
    return transition["state_delta"][family][variable]


def target_impact(transition, target):
    return next((
        item for item in transition["appraisal"].get("state_impacts", [])
        if item.get("variable") == target
    ), None)


def target_judgment(transition, target):
    return next((
        item for item in transition.get("state_judgments", [])
        if item.get("variable") == target
    ), None)


def audits_complete(call_records, expected_minimum):
    audits = []
    for record in call_records:
        audits.extend(record.get("provider_audit_records", []))
    return {
        "expected_logical_call_count": expected_minimum,
        "logged_actual_request_count": len(audits),
        "all_actual_requests_complete": bool(audits) and all(
            item.get("complete") is True for item in audits
        ),
        "finish_reasons": [item.get("finish_reason") for item in audits],
        "actual_requests": audits,
    }


def evaluate(case, arm, transition, calls):
    target = case["target"]
    impact = target_impact(transition, target)
    judgment = target_judgment(transition, target)
    final_delta = delta_for(transition, target)
    expected = case["expected_judgment"]
    if arm == "combined":
        observed_judgment = (
            "decisive_new_evidence" if impact and impact.get("evidence_strength") == 2
            else "ordinary_new_evidence" if impact else "no_candidate"
        )
        if case["polarity"] == "positive":
            recognition_pass = impact is not None
            strength_pass = bool(
                impact and impact.get("evidence_strength")
                == case["expected_semantic_strength"]
            )
        else:
            recognition_pass = impact is None
            strength_pass = impact is None
    else:
        observed_judgment = judgment.get("judgment") if judgment else None
        recognition_pass = observed_judgment == expected
        strength_pass = bool(
            judgment
            and judgment.get("semantic_strength")
            == case["expected_semantic_strength"]
        )
    if case["requires_nonzero_final_update"]:
        final_update_pass = final_delta != "similar"
    else:
        final_update_pass = final_delta == "similar"
    completeness = audits_complete(calls, 1 if arm == "combined" else 2)
    return {
        "target": target,
        "expected_judgment": expected,
        "observed_judgment": observed_judgment,
        "target_impact": impact,
        "target_judgment": judgment,
        "variable_recognition_pass": recognition_pass,
        "evidence_strength_pass": strength_pass,
        "final_delta": final_delta,
        "final_update_pass": final_update_pass,
        "call_completeness": completeness,
        "call_completeness_pass": completeness["all_actual_requests_complete"],
    }


def common_kwargs(turn):
    return {
        "action": turn["policy_action"],
        "previous_state": turn["state_before"],
        "previous_dynamics": turn["dynamics_before"],
        "memory": turn["memory_view"],
        "longitudinal_context": (turn.get("observation") or {}).get(
            "longitudinal_context"
        ),
        "interaction_ledger": turn.get("interaction_ledger_before"),
    }


def run_combined(case, scenario, turn, config):
    provider = build_provider(config["environment"]["provider"])
    sampling = dict(config["environment"]["state_appraisal_sampling"])
    updater = ModelStateUpdater(
        scenario, provider, sampling,
        appraiser=ModelAppraiser(
            scenario, provider, sampling,
            prompt_id=config["environment"]["appraisal_prompt_id"],
        ),
        calibration_profile=config["environment"]["state_calibration_profile"],
    )
    try:
        transition = updater.update(**common_kwargs(turn))
    except Exception as exc:
        return error_result(exc, [provider])
    calls = [transition.get("combined_appraisal_call", {})]
    return {
        "status": "completed",
        "evaluation": evaluate(case, "combined", transition, calls),
        "transition": transition,
        "provider_metrics": provider.metrics,
    }


def run_independent(case, scenario, turn, config):
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
            scenario, state_provider, environment["state_appraisal_sampling"],
            prompt_id=environment["state_appraisal_prompt_id"],
        ),
        interaction_appraiser=ModelInteractionAppraiser(
            scenario, interaction_provider,
            environment["interaction_appraisal_sampling"],
            prompt_id=environment["interaction_appraisal_prompt_id"],
        ),
        calibration_profile=environment["state_calibration_profile"],
    )
    try:
        transition = updater.update(**common_kwargs(turn))
    except Exception as exc:
        return error_result(exc, [state_provider, interaction_provider])
    calls = [
        transition.get("state_appraisal_call", {}),
        transition.get("interaction_appraisal_call", {}),
    ]
    return {
        "status": "completed",
        "evaluation": evaluate(case, "independent", transition, calls),
        "transition": transition,
        "provider_metrics": {
            "state": state_provider.metrics,
            "interaction": interaction_provider.metrics,
        },
    }


def error_result(exc, providers):
    audits = []
    metrics = []
    for provider in providers:
        audits.extend(getattr(provider, "audit_records", []))
        metrics.append(getattr(provider, "metrics", {}))
    return {
        "status": "call_failure",
        "error_type": type(exc).__name__,
        "error": str(exc),
        "finish_reasons": [item.get("finish_reason") for item in audits],
        "actual_requests": audits,
        "provider_metrics": metrics,
    }


def summarize(rows, arm):
    evaluations = [
        row[arm]["evaluation"] for row in rows
        if row[arm].get("status") == "completed"
    ]
    total = len(rows)
    def count(field):
        return sum(item.get(field) is True for item in evaluations)
    return {
        "case_count": total,
        "completed_count": len(evaluations),
        "call_failure_count": total - len(evaluations),
        "variable_recognition": {"passed": count("variable_recognition_pass"), "total": total},
        "evidence_strength": {"passed": count("evidence_strength_pass"), "total": total},
        "final_update": {"passed": count("final_update_pass"), "total": total},
        "call_completeness": {"passed": count("call_completeness_pass"), "total": total},
    }


def independent_pass(summary):
    return all(
        summary[name]["passed"] == summary[name]["total"]
        for name in (
            "variable_recognition", "evidence_strength",
            "final_update", "call_completeness",
        )
    ) and summary["call_failure_count"] == 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--resume", action="store_true",
        help="resume an interrupted run from its atomically saved output",
    )
    parser.add_argument(
        "--config", type=Path,
        default=ROOT / "configs/gpt50_experiment/rollout.state_independent_per_variable_v1_candidate.json",
    )
    args = parser.parse_args(argv)
    manifest = load(args.manifest)
    config = load_rollout_config(args.config)
    rows = []
    boundary_rows = []

    result = {
        "format": "socialflux_independent_state_fixed_validation_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "manifest": str(args.manifest.relative_to(ROOT)),
        "config": str(args.config.relative_to(ROOT)),
        "frozen_conditions": {
            "provider": public_provider_config(config["environment"]["provider"]),
            "combined_prompt": config["environment"]["appraisal_prompt_id"],
            "state_prompt": config["environment"]["state_appraisal_prompt_id"],
            "interaction_prompt": config["environment"]["interaction_appraisal_prompt_id"],
            "state_sampling": config["environment"]["state_appraisal_sampling"],
            "interaction_sampling": config["environment"]["interaction_appraisal_sampling"],
            "calibration_profile": config["environment"]["state_calibration_profile"],
            "thresholds_or_budgets_changed": False,
        },
        "fixed_set": rows,
        "boundary_retest": boundary_rows,
    }

    if args.resume and args.output.exists():
        checkpoint = load(args.output)
        expected_manifest = str(args.manifest.relative_to(ROOT))
        expected_config = str(args.config.relative_to(ROOT))
        if checkpoint.get("manifest") != expected_manifest:
            raise ValueError("resume checkpoint uses a different manifest")
        if checkpoint.get("config") != expected_config:
            raise ValueError("resume checkpoint uses a different config")
        rows = checkpoint.get("fixed_set", [])
        boundary_rows = checkpoint.get("boundary_retest", [])
        result = checkpoint
        result["status"] = "running"
        result.setdefault("resume_events", []).append({
            "resumed_at_utc": datetime.now(timezone.utc).isoformat(),
            "reason": "interrupted_process_recovery",
            "completed_fixed_cases_preserved": len(rows),
            "completed_boundary_cases_preserved": len(boundary_rows),
        })
        result["fixed_set"] = rows
        result["boundary_retest"] = boundary_rows

    def save():
        result["combined_summary"] = summarize(rows, "combined") if rows else {}
        result["independent_summary"] = summarize(rows, "independent") if rows else {}
        atomic(args.output, result)

    completed_case_ids = {
        row.get("case", {}).get("case_id") for row in rows
    }
    for case in manifest["cases"]:
        if case["case_id"] in completed_case_ids:
            continue
        scenario = load(ROOT / case["scenario"])
        source = load(ROOT / case["source"])
        turn = find_turn(source, case["turn_id"])
        row = {"case": deepcopy(case)}
        try:
            row["combined"] = run_combined(case, scenario, turn, config)
        except Exception as exc:
            # The constructed provider is internal to run_combined; the raised
            # exception still carries raw truncation/schema evidence when present.
            row["combined"] = {
                "status": "call_failure",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "exception_raw_output": getattr(exc, "raw_output", None),
                "finish_reason": getattr(exc, "finish_reason", None),
                "diagnostics": getattr(exc, "diagnostics", None),
            }
        try:
            row["independent"] = run_independent(case, scenario, turn, config)
        except Exception as exc:
            row["independent"] = {
                "status": "call_failure",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "exception_raw_output": getattr(exc, "raw_output", None),
                "finish_reason": getattr(exc, "finish_reason", None),
                "diagnostics": getattr(exc, "diagnostics", None),
            }
        rows.append(row)
        save()

    case_by_id = {item["case_id"]: item for item in manifest["cases"]}
    completed_boundary_ids = {
        row.get("case_id") for row in boundary_rows
    }
    for case_id in manifest["preplanned_boundary_retest_case_ids"]:
        if case_id in completed_boundary_ids:
            continue
        case = case_by_id[case_id]
        scenario = load(ROOT / case["scenario"])
        source = load(ROOT / case["source"])
        turn = find_turn(source, case["turn_id"])
        row = {"case_id": case_id}
        try:
            row["independent"] = run_independent(case, scenario, turn, config)
        except Exception as exc:
            row["independent"] = {
                "status": "call_failure",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "exception_raw_output": getattr(exc, "raw_output", None),
                "finish_reason": getattr(exc, "finish_reason", None),
                "diagnostics": getattr(exc, "diagnostics", None),
            }
        boundary_rows.append(row)
        save()

    result["combined_summary"] = summarize(rows, "combined")
    result["independent_summary"] = summarize(rows, "independent")
    boundary_completed = [
        row["independent"]["evaluation"] for row in boundary_rows
        if row["independent"].get("status") == "completed"
    ]
    result["boundary_summary"] = {
        "case_count": len(boundary_rows),
        "completed_count": len(boundary_completed),
        "all_four_dimensions_pass": sum(all(item.get(field) is True for field in (
            "variable_recognition_pass", "evidence_strength_pass",
            "final_update_pass", "call_completeness_pass",
        )) for item in boundary_completed),
    }
    result["new_scheme_passed_regression"] = (
        independent_pass(result["independent_summary"])
        and result["boundary_summary"]["all_four_dimensions_pass"]
        == result["boundary_summary"]["case_count"]
    )
    result["status"] = "completed"
    result["human_review"] = "pending"
    save()
    print(json.dumps({
        "output": str(args.output),
        "combined_summary": result["combined_summary"],
        "independent_summary": result["independent_summary"],
        "boundary_summary": result["boundary_summary"],
        "new_scheme_passed_regression": result["new_scheme_passed_regression"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
