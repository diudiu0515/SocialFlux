#!/usr/bin/env python3
"""Author fresh Claude150 T2 source-adaptation specs for every usable rollout."""

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
from tasks.T2.spec_authoring import author_spec, candidate_windows
from tasks.source_catalog import assess_source, load_source_packages, load_source_reviews


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BATCH = ROOT / "data" / "claude150_v1"
DEFAULT_ROUTES = ROOT / "configs" / "claude150_v1" / "model_routes.json"
ROUTE = "t2_spec_authoring"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def fingerprint():
    paths = (
        "tasks/T2/spec_authoring.py",
        "scripts/author_claude150_t2_specs.py",
    )
    digest = hashlib.sha256()
    for relative in paths:
        digest.update(relative.encode("utf-8"))
        digest.update((ROOT / relative).read_bytes())
    return digest.hexdigest()


def portable(path):
    return str(Path(path).resolve().relative_to(ROOT))


def relationship_label(scenario):
    narrative = scenario.get("narrative_design") or {}
    return narrative.get("relationship_structure") or "two principal characters"


def author_one(
    ordinal, batch, source_record, review, routes, settings, code_sha,
):
    source_path, source_package = source_record
    name = f"scenario_{ordinal:03d}"
    scenario_path = batch / "scenarios" / name / f"{name}.json"
    scenario = load(scenario_path)
    trajectory = load(ROOT / source_package["source_artifact"])
    diagnostic = assess_source(review, source_package, ROOT)
    base = {
        "format": "socialflux_claude150_t2_spec_record_v1",
        "ordinal": ordinal,
        "scenario_id": scenario["scenario_id"],
        "scenario_file": portable(scenario_path),
        "source_package": portable(source_path),
        "source_rollout": source_package["source_artifact"],
        "source_trajectory_id": source_package["source_trajectory_id"],
        "source_quality_diagnostic": diagnostic,
        "admission": "human_postfilter",
        "model_routes_sha256": routes.sha256,
        "code_fingerprint": code_sha,
        "request_count": 0,
        "human_review": "pending",
    }
    windows = candidate_windows(trajectory, **settings)
    if not windows:
        return {
            **base,
            "status": "skipped_no_controlled_window",
            "turn_count": len(trajectory.get("turns", [])),
        }
    config = routes.provider_config(ROUTE)
    provider = build_provider(config)
    try:
        authored, requests = author_spec(
            provider,
            scenario,
            trajectory,
            seed=946000 + ordinal,
            selection_settings=settings,
        )
        if authored is None:
            return {**base, "status": "skipped_no_controlled_window"}
        spec = {
            "ordinal": ordinal,
            "scenario_file": portable(scenario_path),
            "relationship": relationship_label(scenario),
            "source_rollout": source_package["source_artifact"],
            **authored,
            "authoring_provenance": {
                "route": ROUTE,
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
        return {
            **base,
            "status": "authoring_failed",
            "request_count": int(getattr(provider, "_call_index", 0) or 0),
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "last_raw_output": str(getattr(exc, "last_raw", ""))[-4000:],
            },
        }


def reusable_record(record, routes_sha, code_sha):
    """Reuse only successful or structurally terminal records, never API failures."""
    if (
        record.get("model_routes_sha256") != routes_sha
        or record.get("code_fingerprint") != code_sha
    ):
        return False
    if record.get("status") == "skipped_no_controlled_window":
        return True
    return (
        record.get("status") == "authored_pending_pair_construction_and_human_review"
        and isinstance(record.get("spec"), dict)
    )


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-root", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--model-routes", type=Path, default=DEFAULT_ROUTES)
    parser.add_argument("--count", type=int, default=150)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--request-budget", type=int, default=600)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--minimum-shared-prefix-turns", type=int, default=2)
    parser.add_argument("--minimum-branch-turns", type=int, default=2)
    parser.add_argument("--maximum-branch-turns", type=int, default=4)
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 8:
        parser.error("workers must be in 1..8")
    if not 1 <= args.minimum_branch_turns <= args.maximum_branch_turns:
        parser.error("invalid branch turn bounds")
    retry_ceiling = args.count * 2
    if retry_ceiling > args.request_budget:
        raise ValueError(
            f"retry ceiling {retry_ceiling} exceeds budget {args.request_budget}"
        )
    batch = args.batch_root.resolve()
    output = batch / "t2_specs"
    routes = ModelRoutes.load(args.model_routes).require([ROUTE])
    if routes.provider_config(ROUTE)["model"] != "claude-fable-5":
        raise ValueError("T2 spec authoring requires claude-fable-5")
    source = load_source_packages(
        batch / "source_packages",
        expected_count=args.count,
    )
    reviews = load_source_reviews(batch / "source_review.json")
    settings = {
        "minimum_shared_prefix_turns": args.minimum_shared_prefix_turns,
        "minimum_branch_turns": args.minimum_branch_turns,
        "maximum_branch_turns": args.maximum_branch_turns,
    }
    code_sha = fingerprint()
    records = {}
    futures = {}
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for ordinal in range(1, args.count + 1):
            target = output / "records" / f"scenario_{ordinal:03d}.json"
            if args.resume and target.exists():
                saved = load(target)
                if reusable_record(saved, routes.sha256, code_sha):
                    records[ordinal] = saved
                    continue
            future = executor.submit(
                author_one,
                ordinal,
                batch,
                source[ordinal],
                reviews[ordinal],
                routes,
                settings,
                code_sha,
            )
            futures[future] = (ordinal, target)
        for future in as_completed(futures):
            ordinal, target = futures[future]
            record = future.result()
            atomic(target, record)
            records[ordinal] = record
            print(json.dumps({
                "stage": "t2_specs",
                "completed": len(records),
                "expected": args.count,
                "ordinal": ordinal,
                "status": record["status"],
                "requests": record.get("request_count", 0),
            }, ensure_ascii=False), flush=True)
    ordered = [records[ordinal] for ordinal in range(1, args.count + 1)]
    specs = [deepcopy(item["spec"]) for item in ordered if "spec" in item]
    pair_path = output / "pair_specs.json"
    atomic(pair_path, {
        "format": "socialflux_t2_source_adaptation_specs_v2",
        "construction": (
            "fresh Claude rollout A -> Claude-selected controlled fork -> "
            "Claude-authored B -> exact shared ending"
        ),
        "model_routes_sha256": routes.sha256,
        "code_fingerprint": code_sha,
        "admission": "human_postfilter",
        "human_review": "pending",
        "pairs": specs,
    })
    runtime = {
        "format": "socialflux_t2_source_adaptation_config_v2",
        "model_routes": portable(args.model_routes),
        "model_assignment": {
            "strategy": "single_model_all_llm_roles",
            "model": "claude-fable-5",
            "independent_calls": True,
        },
        "pair_spec_source": portable(pair_path),
        "source_selection": {
            "minimum_history_turns": 4,
            "minimum_branch_turns": args.minimum_branch_turns,
            "allowed_generation_statuses": [
                "accepted",
                "short_natural_trajectory",
                "budget_truncated",
                "machine_rejected",
            ],
            "admission_mode": "human_postfilter",
        },
        "construction": (
            "candidate rollout A -> one-call B -> formal A/B replay -> "
            "shared ending -> model reviews -> human post-filter"
        ),
        "quality_policy": {
            "machine_quality": "diagnostic_only",
            "human_review": "pending_until_explicit_human_judgment",
        },
    }
    atomic(output / "runtime_config.json", runtime)
    statuses = {}
    for item in ordered:
        statuses[item["status"]] = statuses.get(item["status"], 0) + 1
    summary = {
        "format": "socialflux_claude150_t2_spec_summary_v1",
        "record_count": len(ordered),
        "authored_spec_count": len(specs),
        "complete": len(specs) == args.count,
        "incomplete_ordinals": [
            int(item["ordinal"]) for item in ordered
            if "spec" not in item
        ],
        "status_counts": statuses,
        "actual_requests_including_retries": sum(
            int(item.get("request_count", 0)) for item in ordered
        ),
        "model": "claude-fable-5",
        "human_review": "pending",
    }
    atomic(output / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.require_complete and not summary["complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
