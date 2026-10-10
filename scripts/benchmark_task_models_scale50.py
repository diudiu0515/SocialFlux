#!/usr/bin/env python3
"""Matched, resumable model comparison for T1--T4 machine proposals.

Only source-version-matched rollouts that passed the saved model semantic
review are used. Outputs remain machine proposals, never human acceptance or GT.
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

from evaluation.t4_evaluation import public_t4_judge_packet, validate_t4_judgment
from prompts.loader import render_prompt
from providers.factory import build_provider, public_provider_config
from providers.structured import complete_json
from tasks.T2.runtime import ROOT, atomic, load
from tasks.T1.answering import generate_answer as generate_t1_answer
from tasks.T2.answering import generate_answer as generate_t2_answer
from tasks.T3.action_authoring import generate_actions
from tasks.T3.answering import generate_answer as generate_t3_answer


def now():
    return datetime.now(timezone.utc).isoformat()


def provider_config(config, model, role):
    token_budgets = {
        "t1_answer": 5000,
        "t2_answer": 5000,
        "t3_action_authoring": 1800,
        "t3_answer": 6500,
        "t4_judge": 3500,
    }
    provider = {
        "provider": "openai_compatible",
        "endpoint": config["endpoint"],
        "use_proxy": False,
        "api_key_env": config["api_key_env"],
        "model": model,
        "timeout": 600,
        "max_tokens": token_budgets[role],
        "stream": bool(config.get("stream", False)),
    }
    if config.get("api_key_file"):
        provider["api_key_file"] = config["api_key_file"]
    return provider


def package_paths():
    return sorted((ROOT / "build/scale300_tasks_v2").glob("shard*/scenario_*.json"))


def turn_bin(count):
    if count < 10:
        return "6-9"
    if count < 15:
        return "10-14"
    return "15-20"


def eligible_cases(config):
    review = {
        row["scenario_id"]: row
        for row in load(ROOT / "build/scale300_v1/review.json")["candidates"]
    }
    matrix = {
        row["scenario_id"]: row
        for row in load(ROOT / "configs/scale300_v1/design_matrix.json")["scenarios"]
    }
    settings = config["selection"]
    allowed = set(settings["generation_statuses"])
    required = set(settings["require_tasks"])
    cases = []
    for path in package_paths():
        package = load(path)
        scenario_id = package["scenario_id"]
        review_row = review.get(scenario_id, {})
        latest = review_row.get("latest_attempt") or {}
        if review_row.get("generation_status") not in allowed:
            continue
        if (review_row.get("model_semantic_review") or {}).get("decision") != settings["model_semantic_decision"]:
            continue
        if int(package.get("turn_count", 0)) < int(settings["minimum_turns"]):
            continue
        if not required <= set(package.get("tasks", {})):
            continue
        if settings.get("require_current_source_artifact") and package.get("source_artifact") != latest.get("artifact_path"):
            continue
        design = matrix[scenario_id]
        ordinal = int(package["ordinal"])
        cases.append({
            "scenario_id": scenario_id,
            "ordinal": ordinal,
            "package": str(path.relative_to(ROOT)),
            "trajectory": package["source_artifact"],
            "scenario": (
                f"configs/scale300_v1/scenarios/scenario_{ordinal:03d}/"
                f"scenario_{ordinal:03d}.json"
            ),
            "turn_count": int(package["turn_count"]),
            "turn_bin": turn_bin(int(package["turn_count"])),
            "generation_status": review_row["generation_status"],
            "conflict_structure": design["conflict_structure"],
            "relationship_category": design["relationship_category"],
            "source_type": design["source_type"],
        })
    return cases


def select_cases(config):
    candidates = eligible_cases(config)
    limit = int(config["scenario_count"])
    frozen_ordinals = config.get("scenario_ordinals")
    if frozen_ordinals is not None:
        if len(frozen_ordinals) != limit or len(set(frozen_ordinals)) != limit:
            raise ValueError("frozen scenario ordinals must match scenario_count")
        by_ordinal = {row["ordinal"]: row for row in candidates}
        missing = sorted(set(frozen_ordinals) - set(by_ordinal))
        if missing:
            raise ValueError(f"frozen scenarios are no longer eligible: {missing}")
        return [by_ordinal[ordinal] for ordinal in frozen_ordinals]

    def quality_key(row):
        return (
            row["generation_status"] != "accepted",
            row["turn_count"] < 10,
            -min(row["turn_count"], 20),
            row["ordinal"],
        )

    grouped = {}
    for row in candidates:
        grouped.setdefault(row["conflict_structure"], []).append(row)
    selected = []
    selected_ids = set()
    for conflict in sorted(grouped):
        row = sorted(grouped[conflict], key=quality_key)[0]
        selected.append(row)
        selected_ids.add(row["scenario_id"])
        if len(selected) == limit:
            break
    if len(selected) < limit:
        for row in sorted(candidates, key=quality_key):
            if row["scenario_id"] in selected_ids:
                continue
            selected.append(row)
            selected_ids.add(row["scenario_id"])
            if len(selected) == limit:
                break
    if len(selected) != limit:
        raise ValueError(f"only {len(selected)} eligible cases for requested {limit}")
    return sorted(selected, key=lambda row: row["ordinal"])


def t2_instance(package):
    instance = deepcopy(package["tasks"]["T2"]["instance"])
    target = instance["target_spec"]
    target["candidate_state_ids"] = list(target.pop("target_state_ids"))
    return instance


def run_role(config, model, role, case):
    started = time.monotonic()
    provider = build_provider(provider_config(config, model, role))
    package = load(ROOT / case["package"])
    try:
        seed = 180000 + case["ordinal"] * 10 + config["roles"].index(role)
        if role == "t1_answer":
            output, requests = generate_t1_answer(
                provider, package["tasks"]["T1"]["instance"], seed,
                max_attempts=config["retry_limit"],
            )
        elif role == "t2_answer":
            output, requests = generate_t2_answer(
                provider, t2_instance(package), seed,
                max_attempts=config["retry_limit"],
            )
        elif role == "t3_action_authoring":
            instance = package["tasks"]["T3"]["instance"]
            output, requests = generate_actions(
                provider,
                {
                    "history": instance["input"]["history"],
                    "current_observation": instance["input"]["current_observation"],
                    "target_spec": instance["target_spec"],
                },
                seed,
                max_attempts=config["retry_limit"],
            )
        elif role == "t3_answer":
            output, requests = generate_t3_answer(
                provider, package["tasks"]["T3"]["instance"], seed,
                max_attempts=config["retry_limit"],
            )
        elif role == "t4_judge":
            trajectory = load(ROOT / case["trajectory"])
            scenario = load(ROOT / case["scenario"])
            packet = public_t4_judge_packet(trajectory, scenario)
            valid_turn_ids = [row["turn_id"] for row in trajectory["turns"]]
            output = complete_json(
                provider,
                [{"role": "user", "content": render_prompt("t4_judge_v2", packet)}],
                {"temperature": 0.1, "top_p": 0.9, "seed": seed},
                lambda value: validate_t4_judgment(value, valid_turn_ids),
                context=f"T4 benchmark judge {case['scenario_id']}",
                max_attempts=config["retry_limit"],
                retry_guidance="Use exactly the five dimensions and cite visible turn IDs only.",
            )
            requests = int(getattr(provider, "_call_index", 0) or 0)
        else:
            raise ValueError(f"unsupported role: {role}")
        return {
            "status": "success",
            "output": output,
            "request_count": requests,
            "latency_seconds": round(time.monotonic() - started, 3),
            "provider": public_provider_config(provider_config(config, model, role)),
        }
    except Exception as exc:
        return {
            "status": "error",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "last_validation_error": str(getattr(exc, "last_error", "")),
            "last_raw_output": str(getattr(exc, "last_raw", ""))[-4000:],
            "request_count": int(getattr(provider, "_call_index", 0) or 0),
            "latency_seconds": round(time.monotonic() - started, 3),
            "provider": public_provider_config(provider_config(config, model, role)),
        }


def cumulative_requests(row):
    return int(row.get("request_count", 0)) + sum(
        int(attempt.get("request_count", 0))
        for attempt in row.get("attempt_history", [])
    )


def cumulative_latency(row):
    return float(row.get("latency_seconds", 0)) + sum(
        float(attempt.get("latency_seconds", 0))
        for attempt in row.get("attempt_history", [])
    )


def summarize(records):
    groups = {}
    for row in records.values():
        groups.setdefault((row["role"], row["model"]), []).append(row)
    summary = {}
    for (role, model), rows in sorted(groups.items()):
        summary.setdefault(role, {})[model] = {
            "cases": len(rows),
            "successes": sum(row["status"] == "success" for row in rows),
            "requests": sum(cumulative_requests(row) for row in rows),
            "mean_latency_seconds": round(statistics.mean(
                cumulative_latency(row) for row in rows
            ), 3),
        }
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/task_model_benchmark_scale50_v1.json"))
    parser.add_argument("--output", type=Path, default=Path("build/task_model_benchmark_scale50_v1/results.json"))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--role", action="append")
    parser.add_argument(
        "--retry-errors", action="store_true",
        help="rerun saved error records while preserving them in attempt_history",
    )
    parser.add_argument(
        "--refresh-summary", action="store_true",
        help="recompute cumulative request/latency totals without model requests",
    )
    args = parser.parse_args()
    config = load(args.config)
    if config.get("format") != "socialflux_task_model_benchmark_v1":
        raise ValueError("benchmark config format mismatch")
    secret_name = config["api_key_env"]
    secret_file = config.get("api_key_file")
    if not os.environ.get(secret_name) and not (
        secret_file and Path(secret_file).expanduser().is_file()
    ):
        raise ValueError(f"{secret_name} or api_key_file is required")
    roles = tuple(args.role or config["roles"])
    unknown = set(roles) - set(config["roles"])
    if unknown:
        raise ValueError(f"unknown roles: {sorted(unknown)}")
    cases = select_cases(config)
    if args.limit is not None:
        cases = cases[:args.limit]
    existing = load(args.output) if args.output.exists() else {
        "format": "socialflux_task_model_benchmark_results_v1",
        "review_status": "development_model_comparison_not_human_validation",
        "config": str(args.config),
        "created_at_utc": now(),
        "sample": cases,
        "records": {},
    }
    if existing.get("sample") != cases:
        raise ValueError("saved benchmark sample differs from current selection")
    records = existing["records"]
    if args.refresh_summary:
        existing["updated_at_utc"] = now()
        existing["actual_request_count"] = sum(
            cumulative_requests(row) for row in records.values()
        )
        existing["summary"] = summarize(records)
        atomic(args.output, existing)
        print({
            "records": len(records),
            "actual_request_count": existing["actual_request_count"],
            "status": "summary_refreshed_without_model_requests",
        })
        return
    pending = []
    for case in cases:
        for role in roles:
            for model in config["models"]:
                key = f"{role}::{model}::{case['scenario_id']}"
                if key not in records or (
                    args.retry_errors and records[key].get("status") == "error"
                ):
                    pending.append((key, model, role, case))
    projected = (
        sum(cumulative_requests(row) for row in records.values())
        + len(pending) * int(config["retry_limit"])
    )
    if projected > int(config["request_budget"]):
        raise ValueError(
            f"projected minimum requests {projected} exceed budget {config['request_budget']}"
        )
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(run_role, config, model, role, case): (key, model, role, case)
            for key, model, role, case in pending
        }
        for future in as_completed(futures):
            key, model, role, case = futures[future]
            previous = records.get(key)
            attempt_history = list((previous or {}).get("attempt_history", []))
            if previous:
                attempt_history.append({
                    field: deepcopy(previous.get(field))
                    for field in (
                        "status", "error_type", "error", "last_validation_error",
                        "last_raw_output", "request_count", "latency_seconds", "provider",
                    )
                    if field in previous
                })
            record = {
                "model": model,
                "role": role,
                "scenario_id": case["scenario_id"],
                "ordinal": case["ordinal"],
                **future.result(),
            }
            if attempt_history:
                record["attempt_history"] = attempt_history
            records[key] = record
            existing["updated_at_utc"] = now()
            existing["actual_request_count"] = sum(
                cumulative_requests(row) for row in records.values()
            )
            existing["summary"] = summarize(records)
            atomic(args.output, existing)
            print({
                "completed": len(records),
                "planned": len(cases) * len(roles) * len(config["models"]),
                "role": role,
                "model": model,
                "scenario_id": case["scenario_id"],
                "status": records[key]["status"],
                "requests": records[key]["request_count"],
            }, flush=True)


if __name__ == "__main__":
    main()
