#!/usr/bin/env python3
"""Matched, resumable API-model comparison for SocialFlux model roles.

This is a development diagnostic. It never labels its output human review or GT.
Each role reuses the canonical prompt, validator, and data owner for that role.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from environment.appraisal import ModelAppraiser
from environment.env import StatefulEnvironment
from environment.longitudinal import public_longitudinal_view
from environment.memory import MemoryModule
from environment.response_generator import ModelResponseGenerator
from environment.state_updater import ModelStateUpdater, validate_transition
from evaluation.rollout_gate import public_judge_packet
from policies.model_policy import ModelPolicy
from prompts.loader import render_prompt
from providers.factory import build_provider, public_provider_config
from providers.structured import complete_json
from providers.text import normalize_text
from evaluation.rollout_semantic_review import (
    deterministic_review_sampling,
    validate_judgment,
)
from scripts.t2_common import ROOT, atomic, load, scenario_path
from tasks.T2.answering import generate_answer
from tasks.T2.branch_authoring import author_branch
from tasks.T2.pair_builder import public_source_turn
from tasks.T2.source_selection import source_index


ROLES = (
    "policy", "appraisal", "response", "task_construction",
    "task_answer", "semantic_judge",
)


def now():
    return datetime.now(timezone.utc).isoformat()


def provider_config(config, model, role):
    budgets = {
        "policy": 1200,
        "appraisal": 3500,
        "response": 1800,
        "task_construction": 5000,
        "task_answer": 5000,
        "semantic_judge": 3000,
    }
    return {
        "provider": "openai_compatible",
        "endpoint": config["endpoint"],
        "use_proxy": False,
        "api_key_env": config["api_key_env"],
        "model": model,
        "timeout": 600,
        "max_tokens": budgets[role],
        "stream": bool(config.get("stream", False)),
    }


def checkpoint_case(case):
    scenario = load(ROOT / case["scenario"])
    trajectory = load(ROOT / case["trajectory"])
    turn = trajectory["turns"][case["turn_index"]]
    return scenario, trajectory, turn


def policy_case(config, model, case, provider=None):
    _, _, turn = checkpoint_case(case)
    provider = provider or build_provider(provider_config(config, model, "policy"))
    policy = ModelPolicy(
        f"benchmark_{model}", provider,
        prompt_id="task_t4_action_v21",
        sampling={"temperature": 0.4, "top_p": 0.9, "seed": 11001},
        validation_profile="hard_only",
        horizon_mode="natural_max_20",
    )
    return policy.generate(deepcopy(turn["observation"])), provider


def appraisal_case(config, model, case, provider=None):
    scenario, _, turn = checkpoint_case(case)
    snapshot = turn["environment_snapshot_before"]
    action = deepcopy(turn["policy_action"])
    memory = MemoryModule().retrieve(snapshot.get("history", []), action)
    normalized = normalize_text(action["text"])
    memory["deterministic_surface_duplicate_ids"] = [
        f"t{item['turn_id']}" for item in snapshot.get("history", [])
        if item.get("role") == "evaluated_agent"
        and normalize_text(item.get("text", "")) == normalized
    ]
    provider = provider or build_provider(
        provider_config(config, model, "appraisal")
    )
    updater = ModelStateUpdater(
        scenario, provider,
        {"temperature": 0.1, "top_p": 0.9, "seed": 12001},
        appraiser=ModelAppraiser(
            scenario, provider,
            {"temperature": 0.1, "top_p": 0.9, "seed": 12001},
            prompt_id="environment_appraisal_v11",
        ),
    )
    output = updater.update(
        action=action,
        previous_state=snapshot["state"],
        previous_dynamics=snapshot["dynamics"],
        memory=memory,
        longitudinal_context=public_longitudinal_view(snapshot),
        interaction_ledger=snapshot.get("interaction_ledger", {}),
    )
    return output, provider


class FixedTransitionUpdater:
    """Diagnostic-only fixed appraisal for isolating the response model."""

    provenance = {"provider": "saved_transition", "model": "fixed"}

    def __init__(self, transition, state, dynamics):
        self.transition = validate_transition(deepcopy(transition), state, dynamics)

    def update(self, **_):
        return deepcopy(self.transition)


def response_case(config, model, case, provider=None):
    scenario, _, turn = checkpoint_case(case)
    snapshot = turn["environment_snapshot_before"]
    transition = {
        "appraisal": deepcopy(turn["appraisal"]),
        "state_delta": deepcopy(turn["state_delta"]),
        "interaction_dynamics_delta": deepcopy(turn["dynamics_delta"]),
        "evidence_turn_ids": deepcopy(turn.get("evidence_turn_ids", [])),
    }
    provider = provider or build_provider(provider_config(config, model, "response"))
    environment = StatefulEnvironment(
        scenario,
        state_updater=FixedTransitionUpdater(
            transition, snapshot["state"], snapshot["dynamics"],
        ),
        response_generator=ModelResponseGenerator(
            provider,
            {"temperature": 0.25, "top_p": 0.9, "seed": 13001},
            prompt_id="environment_response_v25",
            validation_profile="hard_only",
            horizon_mode="natural_max_20",
        ),
    )
    environment.restore(snapshot, episode_id=f"response-benchmark-{case['case_id']}")
    _, log = environment.step(deepcopy(turn["policy_action"]))
    return {
        "environment_response": log["environment_response"],
        "ledger_events": log.get("environment_response_ledger_events"),
        "ledger_event_normalizations": log.get(
            "environment_response_ledger_event_normalizations"
        ),
        "observable_expression": log.get("observable_expression"),
    }, provider


def construction_case(config, model, spec_index, provider=None):
    specs = load(ROOT / "configs/t2_source_adaptation_dev_v1.json")["pairs"]
    spec = specs[spec_index]
    scenario = load(scenario_path(spec["ordinal"]))
    source = load(ROOT / spec["source_rollout"])
    indexes = source_index(source)
    fork = indexes[spec["fork_turn_id"]]
    ending = indexes[spec["ending_turn_id"]]
    turns = source["turns"]
    prefix = [public_source_turn(item) for item in turns[:fork]]
    tail = [public_source_turn(item) for item in turns[fork:ending]]
    ending_turn = turns[ending]
    shared_ending = {
        "turn_id": ending_turn["turn_id"],
        "evaluated_agent": ending_turn["policy_action"]["text"],
        "environment_character": ending_turn["environment_response"],
        "observable_expression": deepcopy(spec["shared_ending_behavior"]),
    }
    provider = provider or build_provider(
        provider_config(config, model, "task_construction")
    )
    output, _ = author_branch(
        provider, spec, scenario, prefix, tail, shared_ending,
        14001 + spec_index,
    )
    return output, provider


def answer_case(config, model, result_path, provider=None):
    result = load(ROOT / result_path)
    instance = result["pair"]["instance"]
    provider = provider or build_provider(
        provider_config(config, model, "task_answer")
    )
    output, _ = generate_answer(provider, instance, 15001)
    return output, provider


def judge_case(config, model, case, provider=None):
    scenario, trajectory, _ = checkpoint_case(case)
    provider = provider or build_provider(
        provider_config(config, model, "semantic_judge")
    )
    prompt = render_prompt(
        "rollout_quality_judge_v2",
        public_judge_packet(trajectory, scenario),
    )
    turn_ids = {item["turn_id"] for item in trajectory["turns"]}
    output = complete_json(
        provider,
        [{"role": "user", "content": prompt}],
        deterministic_review_sampling(
            {"temperature": 0.1, "top_p": 0.9, "seed": 16001},
            trajectory["trajectory_id"],
        ),
        lambda value: validate_judgment(
            value, trajectory["trajectory_id"], turn_ids,
        ),
        context=f"benchmark quality judgment {trajectory['trajectory_id']}",
        max_attempts=3,
    )
    return output, provider


def execute(config, model, role, case):
    started = time.monotonic()
    provider = build_provider(provider_config(config, model, role))
    try:
        if role == "policy":
            output, provider = policy_case(config, model, case, provider)
        elif role == "appraisal":
            output, provider = appraisal_case(config, model, case, provider)
        elif role == "response":
            output, provider = response_case(config, model, case, provider)
        elif role == "task_construction":
            output, provider = construction_case(config, model, case, provider)
        elif role == "task_answer":
            output, provider = answer_case(config, model, case, provider)
        elif role == "semantic_judge":
            output, provider = judge_case(config, model, case, provider)
        else:
            raise ValueError(f"unsupported role: {role}")
        return {
            "status": "success",
            "output": output,
            "request_count": int(getattr(provider, "_call_index", 0) or 0),
            "latency_seconds": round(time.monotonic() - started, 3),
            "provider": public_provider_config(provider_config(config, model, role)),
        }
    except Exception as exc:
        return {
            "status": "error",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "last_validation_error": str(getattr(exc, "last_error", "")),
            "attempt_count": len(getattr(exc, "diagnostics", []) or []),
            "last_raw_output": str(getattr(exc, "last_raw", ""))[-4000:],
            "request_count": int(getattr(provider, "_call_index", 0) or 0),
            "latency_seconds": round(time.monotonic() - started, 3),
            "provider": public_provider_config(
                provider_config(config, model, role)
            ),
        }


def item_id(role, case):
    if role in {"policy", "appraisal", "response", "semantic_judge"}:
        return case["case_id"]
    if role == "task_construction":
        return f"spec_{case:03d}"
    return Path(case).stem


def work_items(config, roles):
    checkpoint_cases = config["checkpoint_cases"]
    judge_ids = set(config["judge_case_ids"])
    cases = {
        "policy": checkpoint_cases,
        "appraisal": checkpoint_cases,
        "response": checkpoint_cases,
        "task_construction": config["task_construction_spec_indexes"],
        "task_answer": config["task_answer_results"],
        "semantic_judge": [
            case for case in checkpoint_cases if case["case_id"] in judge_ids
        ],
    }
    return [
        (model, role, case)
        for role in roles for model in config["models"] for case in cases[role]
    ]


def summarize(records):
    summary = {}
    for record in records.values():
        key = (record["role"], record["model"])
        summary.setdefault(key, []).append(record)
    return {
        role: {
            model: {
                "cases": len(rows),
                "successes": sum(row["status"] == "success" for row in rows),
                "requests": sum(int(row.get("request_count", 0)) for row in rows),
                "mean_latency_seconds": round(statistics.mean(
                    row["latency_seconds"] for row in rows
                ), 3),
            }
            for (row_role, model), rows in summary.items() if row_role == role
        }
        for role in ROLES if any(key[0] == role for key in summary)
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path,
        default=Path("configs/api_model_role_benchmark_v1.json"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("build/api_model_role_benchmark_v1/results.json"),
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--role", action="append", choices=ROLES)
    args = parser.parse_args()
    config = load(args.config)
    if config.get("format") != "socialflux_api_model_role_benchmark_v1":
        raise ValueError("benchmark config format mismatch")
    secret_name = config["api_key_env"]
    if not os.environ.get(secret_name):
        raise ValueError(f"{secret_name} is required")
    roles = tuple(args.role or ROLES)
    existing = load(args.output) if args.output.exists() else {
        "format": "socialflux_api_model_role_benchmark_results_v1",
        "review_status": "development_model_comparison_not_human_validation",
        "config": str(args.config),
        "created_at_utc": now(),
        "records": {},
    }
    records = existing["records"]
    pending = []
    for model, role, case in work_items(config, roles):
        identifier = item_id(role, case)
        key = f"{role}::{model}::{identifier}"
        if key not in records:
            pending.append((key, model, role, case, identifier))
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(execute, config, model, role, case):
            (key, model, role, identifier)
            for key, model, role, case, identifier in pending
        }
        for future in as_completed(futures):
            key, model, role, identifier = futures[future]
            result = future.result()
            records[key] = {
                "model": model,
                "role": role,
                "case_id": identifier,
                **result,
            }
            existing["updated_at_utc"] = now()
            existing["actual_request_count"] = sum(
                int(row.get("request_count", 0)) for row in records.values()
            )
            existing["summary"] = summarize(records)
            atomic(args.output, existing)
            print(json.dumps({
                "completed": len(records),
                "pending": len(pending) - sum(
                    item in records for item, *_ in pending
                ),
                "role": role,
                "model": model,
                "case_id": identifier,
                "status": result["status"],
                "latency_seconds": result["latency_seconds"],
            }, ensure_ascii=False), flush=True)
    print(json.dumps(existing["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
