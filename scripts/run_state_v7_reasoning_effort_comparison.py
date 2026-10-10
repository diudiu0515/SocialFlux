#!/usr/bin/env python3
"""Preregister and run a state-only low/medium reasoning comparison."""

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


BASE = (
    ROOT / "data/gpt50/experiment/state_v3_validation"
    / "v323_state_judgment_primary"
)
DEFAULT_MANIFEST = BASE / "human_confirmed_fixed_set.json"
DEFAULT_CONFIG = (
    ROOT / "configs/gpt50_experiment"
    / "rollout.state_independent_per_variable_v3_state_judgment_primary_candidate.json"
)
DEFAULT_AUDIT = BASE / "interface_consistency_audit_single_correction.json"
DEFAULT_PREREGISTRATION = BASE / "reasoning_effort_comparison_preregistration.json"
DEFAULT_OUTPUT = BASE / "reasoning_effort_comparison_results.json"
PROMPT_ID = "environment_state_appraisal_v4_definition_grounded"
PROFILE = "state_judgment_primary_hysteretic_v7"
EFFORTS = ("low", "medium")
NEW_JUDGMENTS = {"ordinary_new_evidence", "decisive_new_evidence"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative(path):
    return str(Path(path).resolve().relative_to(ROOT))


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def find_turn(source, turn_id):
    return next(item for item in source["turns"] if item["turn_id"] == turn_id)


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


def schedule(case_ids):
    rows = []
    for repeat, efforts in ((1, EFFORTS), (2, tuple(reversed(EFFORTS)))):
        for case_id in case_ids:
            for effort in efforts:
                rows.append({
                    "observation_id": f"{case_id}__{effort}__r{repeat}",
                    "case_id": case_id,
                    "reasoning_effort": effort,
                    "repeat": repeat,
                })
    return rows


def validate_frozen_inputs(manifest, config, audit):
    confirmation = manifest.get("human_confirmation") or {}
    if confirmation.get("status") != "complete":
        raise ValueError("fixed labels must be human-confirmed")
    environment = config["environment"]
    required = {
        "independent_appraisals": True,
        "state_calibration_profile": PROFILE,
        "state_transition_runtime_revision": "v3.2.24",
    }
    mismatches = {
        key: {"expected": value, "actual": environment.get(key)}
        for key, value in required.items() if environment.get(key) != value
    }
    if mismatches:
        raise ValueError(f"frozen v7 config mismatch: {mismatches}")
    if (audit.get("prompt_roles") or {}).get("new_scheme_state") != PROMPT_ID:
        raise ValueError("single-correction interface audit does not freeze v4")
    if audit.get("independent_interface_passed") is not True:
        raise ValueError("single-correction interface audit did not pass")


def build_preregistration(manifest_path, config_path, audit_path):
    manifest = load(manifest_path)
    config = load_rollout_config(config_path)
    audit = load(audit_path)
    validate_frozen_inputs(manifest, config, audit)
    case_ids = [case["case_id"] for case in manifest["cases"]]
    return {
        "format": "socialflux_state_v7_reasoning_effort_preregistration_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "preregistered_before_model_calls",
        "model": "gpt-6-astra",
        "state_only": True,
        "interaction_calls": 0,
        "manifest": relative(manifest_path),
        "manifest_sha256": sha256(manifest_path),
        "config": relative(config_path),
        "config_sha256": sha256(config_path),
        "interface_audit": relative(audit_path),
        "interface_audit_sha256": sha256(audit_path),
        "frozen_prompt": PROMPT_ID,
        "frozen_prompt_sha256": prompt_manifest()["prompts"][PROMPT_ID]["sha256"],
        "frozen_calibration_profile": PROFILE,
        "frozen_sampling": deepcopy(
            config["environment"]["state_appraisal_sampling"]
        ),
        "only_independent_variable": "provider.reasoning_effort",
        "reasoning_efforts": list(EFFORTS),
        "repeats_per_case_per_effort": 2,
        "case_ids": case_ids,
        "focus_cases": {
            "costly_honesty": ["trust_gpt003__positive"],
            "same_topic_new_behavior": [
                "trust_gpt002_historical_anchor__negative",
                "trust_gpt003__negative",
            ],
            "power_context_pressure": ["safety_claude030__negative"],
        },
        "schedule": schedule(case_ids),
        "retention_policy": {
            "keep_every_logical_result": True,
            "keep_every_actual_request_and_raw_output": True,
            "rerun_until_pass_prohibited": True,
            "schema_repairs_are_logged_not_hidden": True,
        },
        "predeclared_decision_rule": {
            "complete_calls_required_per_effort": len(case_ids) * 2,
            "medium_positive_recognition_min": 14,
            "medium_exact_four_way_min": 12,
            "costly_honesty_decisive_required": "2/2",
            "same_topic_new_recognition_required": "at_least_3/4",
            "material_improvement": (
                "medium exact-four-way exceeds low by at least 2 observations, "
                "or medium fixes both focus failure types without worsening "
                "overall recognition"
            ),
            "negative_control_requirement": (
                "separately human-confirmed irrelevant and repeated controls "
                "must be correct on every predeclared medium repeat"
            ),
            "if_passed": "unseen_examples_then_small_rollout_validation",
            "if_failed": "same_material_different_appraiser_backbone",
            "full_scale_authorized_by_this_comparison": False,
        },
    }


def target_judgment(result, target):
    return next((
        item for item in result.get("state_judgments", [])
        if item.get("variable") == target
    ), None)


def run_observation(item, case, config):
    environment = config["environment"]
    provider_config = deepcopy(
        environment.get("state_appraisal_provider", environment["provider"])
    )
    provider_config["reasoning_effort"] = item["reasoning_effort"]
    provider = build_provider(provider_config)
    scenario = load(ROOT / case["scenario"])
    source = load(ROOT / case["source"])
    turn = find_turn(source, case["turn_id"])
    sampling = deepcopy(environment["state_appraisal_sampling"])
    appraiser = ModelStateAppraiser(
        scenario, provider, sampling, prompt_id=PROMPT_ID
    )
    try:
        state_result = appraiser.appraise(**common_kwargs(turn))
        transition = DeterministicStateCalibrator(
            scenario, profile=PROFILE
        ).calibrate(
            state_result["appraisal"], turn["state_before"],
            turn["dynamics_before"], current_event_id=turn["turn_id"],
        )
        observed = target_judgment(state_result, case["target"])
        expected = case["adjudicated_label"]
        observed_label = observed.get("judgment") if observed else None
        expected_new = expected["judgment"] in NEW_JUDGMENTS
        observed_new = observed_label in NEW_JUDGMENTS
        family, variable = case["target"].split(".", 1)
        audits = deepcopy(getattr(provider, "audit_records", []))
        return {
            "status": "completed",
            "evaluation": {
                "target": case["target"],
                "human_judgment": expected["judgment"],
                "human_strength": expected["semantic_strength"],
                "observed_judgment": observed_label,
                "observed_strength": (
                    observed.get("semantic_strength") if observed else None
                ),
                "variable_recognition_pass": expected_new == observed_new,
                "exact_four_way_pass": observed_label == expected["judgment"],
                "strength_pass": bool(
                    observed and observed.get("semantic_strength")
                    == expected["semantic_strength"]
                ),
                "false_negative": expected_new and not observed_new,
                "false_positive": (not expected_new) and observed_new,
                "final_delta": transition["state_delta"][family][variable],
                "call_complete": bool(audits) and all(
                    audit.get("complete") is True for audit in audits
                ),
            },
            "state_appraisal": state_result,
            "calibration": transition["calibration"],
            "provider_public_config": public_provider_config(provider_config),
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
            "provider_public_config": public_provider_config(provider_config),
            "provider_metrics": deepcopy(provider.metrics),
        }


def summarize(observations, preregistration):
    result = {}
    focus = preregistration["focus_cases"]
    for effort in EFFORTS:
        rows = [
            row for row in observations if row["reasoning_effort"] == effort
        ]
        completed = [
            row for row in rows if row["result"].get("status") == "completed"
        ]
        evaluations = [row["result"]["evaluation"] for row in completed]

        def count(field):
            return sum(value.get(field) is True for value in evaluations)

        costly = [
            row for row in completed if row["case_id"] in focus["costly_honesty"]
        ]
        same_topic = [
            row for row in completed
            if row["case_id"] in focus["same_topic_new_behavior"]
        ]
        pressure = [
            row for row in completed
            if row["case_id"] in focus["power_context_pressure"]
        ]
        result[effort] = {
            "scheduled": len(rows),
            "completed": len(completed),
            "call_failures": len(rows) - len(completed),
            "complete_calls": count("call_complete"),
            "variable_recognition": count("variable_recognition_pass"),
            "exact_four_way": count("exact_four_way_pass"),
            "strength": count("strength_pass"),
            "false_negatives": count("false_negative"),
            "false_positives": count("false_positive"),
            "costly_honesty_decisive": sum(
                row["result"]["evaluation"]["observed_judgment"]
                == "decisive_new_evidence" for row in costly
            ),
            "costly_honesty_total": len(costly),
            "same_topic_new_recognized": sum(
                row["result"]["evaluation"]["observed_judgment"]
                in NEW_JUDGMENTS for row in same_topic
            ),
            "same_topic_new_total": len(same_topic),
            "power_context_pressure_recognized": sum(
                row["result"]["evaluation"]["observed_judgment"]
                in NEW_JUDGMENTS for row in pressure
            ),
            "power_context_pressure_total": len(pressure),
        }
    low = result["low"]
    medium = result["medium"]
    focus_fix = (
        medium["costly_honesty_decisive"] == 2
        and medium["same_topic_new_recognized"] >= 3
        and medium["variable_recognition"] >= low["variable_recognition"]
    )
    medium_semantic_gate = (
        medium["completed"] == medium["scheduled"] == 16
        and medium["complete_calls"] == 16
        and medium["variable_recognition"] >= 14
        and medium["exact_four_way"] >= 12
        and medium["costly_honesty_decisive"] == 2
        and medium["same_topic_new_recognized"] >= 3
    )
    material_improvement = (
        medium["exact_four_way"] - low["exact_four_way"] >= 2
        or focus_fix
    )
    return {
        "by_effort": result,
        "medium_semantic_gate_without_negative_controls": medium_semantic_gate,
        "material_improvement_over_low": material_improvement,
        "positive_set_provisional_pass": (
            medium_semantic_gate and material_improvement
        ),
        "negative_control_gate": "pending_human_confirmation",
        "full_decision": "pending_negative_controls",
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--interface-audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--preregistration", type=Path, default=DEFAULT_PREREGISTRATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)

    expected_prereg = build_preregistration(
        args.manifest, args.config, args.interface_audit
    )
    if args.prepare_only:
        if args.preregistration.exists():
            raise FileExistsError("refusing to overwrite preregistration")
        atomic(args.preregistration, expected_prereg)
        print(json.dumps({
            "preregistration": str(args.preregistration),
            "scheduled_calls": len(expected_prereg["schedule"]),
            "prompt_sha256": expected_prereg["frozen_prompt_sha256"],
        }, ensure_ascii=False, indent=2))
        return

    if not args.preregistration.exists():
        raise FileNotFoundError("run --prepare-only before any model call")
    prereg = load(args.preregistration)
    immutable_fields = (
        "manifest_sha256", "config_sha256", "interface_audit_sha256",
        "frozen_prompt", "frozen_prompt_sha256", "frozen_calibration_profile",
        "frozen_sampling", "reasoning_efforts", "repeats_per_case_per_effort",
        "case_ids", "focus_cases", "schedule", "predeclared_decision_rule",
    )
    mismatches = [
        field for field in immutable_fields
        if prereg.get(field) != expected_prereg.get(field)
    ]
    if mismatches:
        raise ValueError(f"preregistration no longer matches inputs: {mismatches}")
    if args.output.exists() and not args.resume:
        raise FileExistsError("refusing to overwrite retained comparison results")

    manifest = load(args.manifest)
    config = load_rollout_config(args.config)
    cases = {case["case_id"]: case for case in manifest["cases"]}
    output = {
        "format": "socialflux_state_v7_reasoning_effort_comparison_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "preregistration": relative(args.preregistration),
        "preregistration_sha256": sha256(args.preregistration),
        "frozen_conditions": deepcopy(prereg),
        "observations": [],
    }
    if args.resume:
        output = load(args.output)
        if output.get("preregistration_sha256") != sha256(args.preregistration):
            raise ValueError("resume preregistration hash differs")
        output["status"] = "running"
        output.setdefault("resume_events", []).append({
            "at_utc": datetime.now(timezone.utc).isoformat(),
            "reason": "interrupted_process_recovery_only",
        })

    completed_ids = {row["observation_id"] for row in output["observations"]}
    total = len(prereg["schedule"])
    for index, item in enumerate(prereg["schedule"], start=1):
        if item["observation_id"] in completed_ids:
            continue
        case = cases[item["case_id"]]
        row = {
            **deepcopy(item),
            "case": deepcopy(case),
            "result": run_observation(item, case, config),
        }
        output["observations"].append(row)
        output["summary"] = summarize(output["observations"], prereg)
        atomic(args.output, output)
        observed = (row["result"].get("evaluation") or {}).get(
            "observed_judgment", row["result"].get("status")
        )
        print(
            f"[{index}/{total}] {item['case_id']} {item['reasoning_effort']} "
            f"r{item['repeat']}: {observed}",
            flush=True,
        )

    output["summary"] = summarize(output["observations"], prereg)
    output["status"] = "completed"
    output["full_scale_authorized"] = False
    atomic(args.output, output)
    print(json.dumps({
        "output": str(args.output),
        "summary": output["summary"],
        "full_scale_authorized": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
