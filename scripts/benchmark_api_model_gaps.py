#!/usr/bin/env python3
"""Matched comparison for model roles not covered by the scale-50 benchmark.

This development diagnostic compares scenario authoring, checkpoint/task
extraction, and final rollout quality review. It sends only newly-authored
synthetic briefs or observable scenario/trajectory content. Outputs are model
proposals and model reviews, never human validation or ground truth.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.rollout_gate import public_judge_packet
from prompts.loader import render_prompt
from providers.factory import build_provider, public_provider_config
from providers.structured import complete_json
from evaluation.rollout_semantic_review import (
    deterministic_review_sampling,
    validate_judgment,
)
from tasks.T2.runtime import ROOT, load
from tasks.extraction import generate_extraction
from shared.artifacts import atomic_json as atomic


ROLE_TOKEN_BUDGETS = {
    "scenario_authoring": 3500,
    "task_extraction": 3500,
    "quality_review": 3000,
}


def now():
    return datetime.now(timezone.utc).isoformat()


def provider_config(config, model, role):
    return {
        "provider": "openai_compatible",
        "endpoint": config["endpoint"],
        "use_proxy": False,
        "api_key_env": config["api_key_env"],
        "model": model,
        "timeout": 600,
        "max_tokens": ROLE_TOKEN_BUDGETS[role],
        "stream": bool(config.get("stream", False)),
    }


def package_path(ordinal):
    return ROOT / f"build/scale300_tasks_v3/scenario_{ordinal:03d}.json"


def scenario_path(ordinal):
    return ROOT / (
        f"configs/scale300_v1/scenarios/scenario_{ordinal:03d}/"
        f"scenario_{ordinal:03d}.json"
    )


def trajectory_case(ordinal):
    package = load(package_path(ordinal))
    scenario = load(scenario_path(ordinal))
    trajectory = load(ROOT / package["source_artifact"])
    return package, scenario, trajectory


def scenario_case(config, model, brief, provider):
    prompt = render_prompt("scenario_script_generation_v1", brief)
    output = provider.complete(
        [{"role": "user", "content": prompt}],
        temperature=0.45,
        top_p=0.9,
        seed=210000 + config["scenario_briefs"].index(brief),
    ).strip()
    if len(output) < 500:
        raise ValueError("scenario narrative is too short to assess")
    forbidden = ("latent state", "S0", "D0", "JSON schema", "T1", "T2", "T3")
    if any(marker in output for marker in forbidden):
        raise ValueError("scenario narrative leaked benchmark construction language")
    return output, int(getattr(provider, "_call_index", 0) or 0)


def extraction_case(config, model, ordinal, provider):
    _, scenario, trajectory = trajectory_case(ordinal)
    output = generate_extraction(
        provider,
        scenario,
        trajectory,
        seed=220000 + ordinal,
        max_attempts=config["retry_limit"],
    )
    return output, int(getattr(provider, "_call_index", 0) or 0)


def quality_case(config, model, ordinal, provider):
    _, scenario, trajectory = trajectory_case(ordinal)
    prompt = render_prompt(
        "rollout_quality_judge_v2",
        public_judge_packet(trajectory, scenario),
    )
    turn_ids = {turn["turn_id"] for turn in trajectory["turns"]}
    output = complete_json(
        provider,
        [{"role": "user", "content": prompt}],
        deterministic_review_sampling(
            {"temperature": 0.1, "top_p": 0.9, "seed": 230000},
            trajectory["trajectory_id"],
        ),
        lambda value: validate_judgment(value, trajectory["trajectory_id"], turn_ids),
        context=f"quality review {trajectory['trajectory_id']}",
        max_attempts=config["retry_limit"],
    )
    return output, int(getattr(provider, "_call_index", 0) or 0)


def run_case(config, model, role, case):
    started = time.monotonic()
    provider = build_provider(provider_config(config, model, role))
    try:
        if role == "scenario_authoring":
            output, requests = scenario_case(config, model, case, provider)
            case_id = case["case_id"]
        elif role == "task_extraction":
            output, requests = extraction_case(config, model, case, provider)
            case_id = f"IA_PIPE_{case:03d}"
        elif role == "quality_review":
            output, requests = quality_case(config, model, case, provider)
            case_id = f"IA_PIPE_{case:03d}"
        else:
            raise ValueError(f"unsupported role: {role}")
        return {
            "status": "success",
            "case_id": case_id,
            "output": output,
            "request_count": requests,
            "latency_seconds": round(time.monotonic() - started, 3),
            "provider": public_provider_config(provider_config(config, model, role)),
        }
    except Exception as exc:
        request_count = int(getattr(provider, "_call_index", 0) or 0)
        return {
            "status": "error",
            "case_id": case.get("case_id") if isinstance(case, dict) else f"IA_PIPE_{case:03d}",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "last_validation_error": str(getattr(exc, "last_error", "")),
            "last_raw_output": str(getattr(exc, "last_raw", ""))[-4000:],
            "request_count": request_count,
            "latency_seconds": round(time.monotonic() - started, 3),
            "provider": public_provider_config(provider_config(config, model, role)),
        }


def summarize(records, config):
    groups = {}
    for row in records.values():
        groups.setdefault((row["role"], row["model"]), []).append(row)
    summary = {}
    for (role, model), rows in sorted(groups.items()):
        item = {
            "cases": len(rows),
            "successes": sum(row["status"] == "success" for row in rows),
            "requests": sum(int(row.get("request_count", 0)) for row in rows),
            "mean_latency_seconds": round(statistics.mean(
                row["latency_seconds"] for row in rows
            ), 3),
        }
        if role == "quality_review":
            expectations = config.get("quality_expectations", {})
            expected_rows = [row for row in rows if row["case_id"] in expectations]
            item["known_issue_cases"] = len(expected_rows)
            item["known_issue_detected"] = sum(
                bool(
                    set(row.get("output", {}).get("hard_reject_reasons", []))
                    & set(expectations[row["case_id"]])
                )
                for row in expected_rows
            )
        summary.setdefault(role, {})[model] = item
    return summary


def planned_cases(config, roles):
    result = []
    for role in roles:
        cases = (
            config["scenario_briefs"]
            if role == "scenario_authoring"
            else config["trajectory_cases"]
        )
        for case in cases:
            for model in config["models"]:
                case_id = case["case_id"] if isinstance(case, dict) else f"IA_PIPE_{case:03d}"
                result.append((f"{role}::{model}::{case_id}", model, role, case))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path,
        default=Path("configs/api_model_gap_benchmark_v1.json"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("build/api_model_gap_benchmark_v1/results.json"),
    )
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--role", action="append")
    parser.add_argument("--retry-errors", action="store_true")
    args = parser.parse_args()
    config = load(args.config)
    if config.get("format") != "socialflux_api_model_gap_benchmark_v1":
        raise ValueError("benchmark config format mismatch")
    secret_name = config["api_key_env"]
    if not os.environ.get(secret_name):
        raise ValueError(f"{secret_name} is required")
    roles = tuple(args.role or config["roles"])
    unknown = set(roles) - set(config["roles"])
    if unknown:
        raise ValueError(f"unknown roles: {sorted(unknown)}")
    planned = planned_cases(config, roles)
    output_path = args.output.resolve()
    existing = load(output_path) if output_path.exists() else {
        "format": "socialflux_api_model_gap_benchmark_results_v1",
        "review_status": "development_model_comparison_not_human_validation",
        "config": str(args.config),
        "created_at_utc": now(),
        "data_boundary": "synthetic_briefs_and_observable_authorized_histories_only",
        "records": {},
    }
    records = existing["records"]
    pending = [
        item for item in planned
        if item[0] not in records or (
            args.retry_errors and records[item[0]].get("status") == "error"
        )
    ]
    prior_requests = sum(int(row.get("request_count", 0)) for row in records.values())
    projected = prior_requests + len(pending) * int(config["retry_limit"])
    if projected > int(config["request_budget"]):
        raise ValueError(
            f"projected requests {projected} exceed budget {config['request_budget']}"
        )
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(run_case, config, model, role, case): (key, model, role)
            for key, model, role, case in pending
        }
        for future in as_completed(futures):
            key, model, role = futures[future]
            previous = records.get(key)
            record = {"model": model, "role": role, **future.result()}
            if previous:
                record["attempt_history"] = list(previous.get("attempt_history", [])) + [
                    deepcopy(previous)
                ]
            records[key] = record
            existing["updated_at_utc"] = now()
            existing["actual_request_count"] = sum(
                int(row.get("request_count", 0)) for row in records.values()
            )
            existing["summary"] = summarize(records, config)
            atomic(output_path, existing)
            print({
                "completed": len(records),
                "planned": len(planned),
                "role": role,
                "model": model,
                "case_id": record["case_id"],
                "status": record["status"],
                "requests": record["request_count"],
            }, flush=True)


if __name__ == "__main__":
    main()
