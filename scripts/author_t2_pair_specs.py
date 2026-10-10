#!/usr/bin/env python3
"""Author source-bound T2 adaptation specs with the active model route.

This stage selects a controlled fork and shared ending from each eligible real
rollout.  It does not construct History B or replay either branch; those remain
the responsibility of the source-adapted T2 builder.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.factory import build_provider, public_provider_config
from providers.model_routes import ModelRoutes
from tasks.T2.runtime import ROOT, atomic, load, now, scenario_path
from tasks.T2.spec_authoring import author_spec, candidate_windows
from tasks.source_catalog import (
    assess_source,
    load_source_packages,
    load_source_reviews,
)


DEFAULT_SOURCE_PACKAGES = ROOT / "build/scale300_tasks_v2"
DEFAULT_REVIEWS = ROOT / "build/scale300_v1/review.json"
DEFAULT_ROUTES = ROOT / "configs/model_routes.frontier_api.json"
DEFAULT_OUTPUT = ROOT / "build/t2_pair_specs"
ROUTE_NAME = "t2_spec_authoring"
SPEC_FORMAT = "socialflux_t2_source_adaptation_specs_v2"
AUTHORING_FORMAT = "socialflux_t2_spec_authoring_run_v1"
FINGERPRINT_FILES = (
    "tasks/T2/spec_authoring.py",
    "tasks/source_catalog.py",
    "scripts/author_t2_pair_specs.py",
)


def code_fingerprint():
    digest = hashlib.sha256()
    for relative in FINGERPRINT_FILES:
        digest.update(relative.encode("utf-8"))
        digest.update((ROOT / relative).read_bytes())
    return digest.hexdigest()


def relationship_label(scenario):
    narrative = scenario.get("narrative_design") or {}
    label = narrative.get("relationship_structure")
    if label:
        return label
    evaluated = scenario.get("evaluated_agent_role") or {}
    target = (scenario.get("environment_agent") or {}).get("persona") or {}
    return f"{evaluated.get('name', '受评角色')}—{target.get('name', '目标角色')}"


def portable_path(path):
    path = Path(path).resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def error_record(error, provider=None):
    return {
        "type": type(error).__name__,
        "message": str(error),
        "last_validation_error": str(getattr(error, "last_error", "")),
        "last_raw_output": str(getattr(error, "last_raw", ""))[-4000:],
        "request_count": int(getattr(provider, "_call_index", 0) or 0),
    }


def author_one(
    ordinal,
    source_record,
    review,
    routes,
    selection_settings,
    fingerprint,
):
    source_path, source_package = source_record
    scenario = load(scenario_path(ordinal))
    assessment = assess_source(review, source_package, ROOT)
    base = {
        "format": AUTHORING_FORMAT,
        "created_at_utc": now(),
        "ordinal": ordinal,
        "scenario_id": scenario["scenario_id"],
        "source_package": str(source_path.relative_to(ROOT)),
        "source_rollout": source_package.get("source_artifact"),
        "source_trajectory_id": source_package.get("source_trajectory_id"),
        "source_quality": assessment,
        "model_routes_sha256": routes.sha256,
        "code_fingerprint": fingerprint,
        "request_count": 0,
    }
    if not assessment["eligible"]:
        return {**base, "status": "skipped_source_quality"}

    trajectory = load(ROOT / source_package["source_artifact"])
    windows = candidate_windows(trajectory, **selection_settings)
    if not windows:
        return {
            **base,
            "status": "skipped_no_controlled_window",
            "turn_count": len(trajectory.get("turns", [])),
        }

    config = routes.provider_config(ROUTE_NAME)
    provider = build_provider(config)
    try:
        authored, requests = author_spec(
            provider,
            scenario,
            trajectory,
            seed=460000 + ordinal,
            selection_settings=selection_settings,
        )
        if authored is None:
            return {**base, "status": "skipped_no_controlled_window"}
        spec = {
            "ordinal": ordinal,
            "relationship": relationship_label(scenario),
            "source_rollout": source_package["source_artifact"],
            **authored,
            "authoring_provenance": {
                "route": ROUTE_NAME,
                "provider": public_provider_config(config),
                "request_count": requests,
                "human_review": "pending",
            },
        }
        return {
            **base,
            "status": "authored_pending_pair_construction_and_human_review",
            "request_count": requests,
            "candidate_window_count": len(windows),
            "spec": spec,
        }
    except Exception as exc:
        failure = error_record(exc, provider)
        return {
            **base,
            "status": "authoring_failed",
            "request_count": failure["request_count"],
            "error": failure,
        }


def summarize(records, routes, output, fingerprint, selection_settings):
    statuses = {}
    for record in records:
        status = record["status"]
        statuses[status] = statuses.get(status, 0) + 1
    specs = [deepcopy(record["spec"]) for record in records if "spec" in record]
    pair_document = {
        "format": SPEC_FORMAT,
        "construction": (
            "eligible real rollout A -> model-selected checkpoint fork -> "
            "authored B -> formal A/B replay -> exact shared ending"
        ),
        "model_routes_sha256": routes.sha256,
        "code_fingerprint": fingerprint,
        "human_review": "pending",
        "pairs": specs,
    }
    atomic(output / "pair_specs.json", pair_document)
    runtime_config = {
        "format": "socialflux_t2_source_adaptation_config_v2",
        "model_routes": str(routes.source_path.relative_to(ROOT)),
        "model_assignment": {
            "strategy": "single_model_all_llm_roles",
            "model": "claude-fable-5",
            "independent_calls": True,
        },
        "pair_spec_source": portable_path(output / "pair_specs.json"),
        "source_selection": {
            "minimum_history_turns": 4,
            "minimum_branch_turns": selection_settings["minimum_branch_turns"],
            "allowed_generation_statuses": [
                "accepted",
                "short_natural_trajectory",
                "budget_truncated",
            ],
        },
        "construction": (
            "eligible real rollout A -> one-call complete B history -> formal A/B "
            "replay -> exact shared ending -> pair review -> LLM answer -> answer review"
        ),
        "quality_policy": {
            "low_quality_source": "skip_and_record",
            "environment_quality_problem": "annotate_by_side_and_turn_do_not_rewrite",
            "human_review": "pending_until_explicit_human_judgment",
        },
    }
    atomic(output / "runtime_config.json", runtime_config)
    summary = {
        "format": AUTHORING_FORMAT,
        "created_at_utc": now(),
        "record_count": len(records),
        "authored_spec_count": len(specs),
        "status_counts": statuses,
        "actual_requests_including_retries": sum(
            int(record.get("request_count", 0)) for record in records
        ),
        "model": "claude-fable-5",
        "model_routes_sha256": routes.sha256,
        "code_fingerprint": fingerprint,
        "selection_settings": selection_settings,
        "human_review": "pending",
    }
    atomic(output / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-packages", type=Path, default=DEFAULT_SOURCE_PACKAGES)
    parser.add_argument("--reviews", type=Path, default=DEFAULT_REVIEWS)
    parser.add_argument("--model-routes", type=Path, default=DEFAULT_ROUTES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ordinal", type=int, action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--request-budget", type=int, default=600)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--minimum-shared-prefix-turns", type=int, default=2)
    parser.add_argument("--minimum-branch-turns", type=int, default=2)
    parser.add_argument("--maximum-branch-turns", type=int, default=4)
    args = parser.parse_args()

    routes = ModelRoutes.load(args.model_routes).require([ROUTE_NAME])
    config = routes.provider_config(ROUTE_NAME)
    if config["model"] != "claude-fable-5":
        raise ValueError("active T2 spec authoring requires claude-fable-5")
    source = load_source_packages(args.source_packages)
    reviews = load_source_reviews(args.reviews)
    selected = sorted(set(args.ordinal or range(1, 301)))
    unknown = set(selected) - set(source)
    if unknown:
        raise ValueError(f"unknown ordinals: {sorted(unknown)}")
    if args.limit is not None:
        selected = selected[:args.limit]
    selection_settings = {
        "minimum_shared_prefix_turns": args.minimum_shared_prefix_turns,
        "minimum_branch_turns": args.minimum_branch_turns,
        "maximum_branch_turns": args.maximum_branch_turns,
    }
    if args.minimum_shared_prefix_turns < 1:
        parser.error("minimum shared prefix must be positive")
    if not 1 <= args.minimum_branch_turns <= args.maximum_branch_turns:
        parser.error("branch turn bounds are invalid")

    eligible_count = sum(
        assess_source(reviews[ordinal], source[ordinal][1], ROOT)["eligible"]
        for ordinal in selected
    )
    retry_ceiling = eligible_count * 2
    if retry_ceiling > args.request_budget:
        raise ValueError(
            f"retry ceiling {retry_ceiling} exceeds request budget {args.request_budget}"
        )

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    fingerprint = code_fingerprint()
    records = {}
    futures = {}
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for ordinal in selected:
            target = output / "records" / f"scenario_{ordinal:03d}.json"
            if args.resume and target.is_file():
                saved = load(target)
                if (
                    saved.get("model_routes_sha256") == routes.sha256
                    and saved.get("code_fingerprint") == fingerprint
                ):
                    records[ordinal] = saved
                    continue
            future = executor.submit(
                author_one,
                ordinal,
                source[ordinal],
                reviews[ordinal],
                routes,
                selection_settings,
                fingerprint,
            )
            futures[future] = (ordinal, target)

        for future in as_completed(futures):
            ordinal, target = futures[future]
            record = future.result()
            atomic(target, record)
            records[ordinal] = record
            print(json.dumps({
                "completed": len(records),
                "selected": len(selected),
                "ordinal": ordinal,
                "status": record["status"],
                "requests": record["request_count"],
            }, ensure_ascii=False), flush=True)

    ordered = [records[ordinal] for ordinal in selected]
    actual = sum(int(record.get("request_count", 0)) for record in ordered)
    if actual > args.request_budget:
        raise ValueError(
            f"actual requests {actual} exceeded request budget {args.request_budget}"
        )
    print(json.dumps(
        summarize(ordered, routes, output, fingerprint, selection_settings),
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
