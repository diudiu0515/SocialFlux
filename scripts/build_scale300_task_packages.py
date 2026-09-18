#!/usr/bin/env python3
"""Build current Scale300 T1--T4 machine proposals with active routes."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.model_routes import ModelRoutes
from scripts.t2_common import ROOT, atomic, load, scenario_path
from tasks.package_builder import BUILDER_ID, TaskPackageBuilder
from tasks.source_catalog import (
    assess_source,
    load_source_packages,
    load_source_reviews,
)


DEFAULT_OLD_PACKAGES = ROOT / "build/scale300_tasks_v2"
DEFAULT_REVIEW = ROOT / "build/scale300_v1/review.json"
DEFAULT_ROUTES = ROOT / "configs/model_routes.frontier_api.json"
DEFAULT_OUTPUT = ROOT / "build/scale300_tasks"
REQUIRED_ROUTES = (
    "task_extraction",
    "t1_answer",
    "t3_action_authoring",
    "t3_answer",
    "t4_judge",
)
FINGERPRINT_FILES = (
    "tasks/package_builder.py",
    "tasks/extraction.py",
    "tasks/T1/answering.py",
    "tasks/T3/action_authoring.py",
    "tasks/T3/answering.py",
    "tasks/T4/answering.py",
)


def code_fingerprint():
    digest = hashlib.sha256()
    for relative in FINGERPRINT_FILES:
        digest.update(relative.encode("utf-8"))
        digest.update((ROOT / relative).read_bytes())
    return digest.hexdigest()


def load_t2_results(run_dir):
    if run_dir is None:
        return {}
    records = {}
    for path in sorted((Path(run_dir) / "results").glob("*.json")):
        result = load(path)
        ordinal = int(result["ordinal"])
        if ordinal in records:
            raise ValueError(f"duplicate T2 result ordinal: {ordinal}")
        records[ordinal] = result
    return records


def selected_ordinals(args, source, reviews):
    requested = set(args.ordinal or range(1, 301))
    unknown = requested - set(source)
    if unknown:
        raise ValueError(f"unknown ordinals: {sorted(unknown)}")
    selected = sorted(requested)
    if args.limit is not None:
        selected = selected[: args.limit]
    eligible = [
        ordinal
        for ordinal in selected
        if assess_source(reviews[ordinal], source[ordinal][1], ROOT)["eligible"]
    ]
    return selected, eligible


def summarize(packages, routes, output, builder_code_sha256):
    statuses = {}
    task_counts = {name: 0 for name in ("T1", "T2", "T3", "T4")}
    task_errors = {name: 0 for name in task_counts}
    task_gaps = {name: 0 for name in task_counts}
    for package in packages:
        statuses[package["status"]] = statuses.get(package["status"], 0) + 1
        for name in task_counts:
            task_counts[name] += int(name in package.get("tasks", {}))
            task_errors[name] += int(name in package.get("task_errors", {}))
            task_gaps[name] += int(name in package.get("task_gaps", {}))
    summary = {
        "format": "socialflux_scale300_task_summary_v4",
        "builder": BUILDER_ID,
        "model": "claude-fable-5",
        "model_routes_path": str(routes.source_path.relative_to(ROOT)),
        "model_routes_sha256": routes.sha256,
        "builder_code_sha256": builder_code_sha256,
        "package_count": len(packages),
        "status_counts": statuses,
        "task_answer_counts": task_counts,
        "task_error_counts": task_errors,
        "task_gap_counts": task_gaps,
        "actual_requests_including_retries": sum(
            int(package.get("request_count", 0)) for package in packages
        ),
        "human_review": "pending",
        "output": (
            str(output.relative_to(ROOT))
            if output.is_relative_to(ROOT)
            else str(output)
        ),
    }
    atomic(output / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-packages", type=Path, default=DEFAULT_OLD_PACKAGES)
    parser.add_argument("--reviews", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--model-routes", type=Path, default=DEFAULT_ROUTES)
    parser.add_argument("--t2-run-dir", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ordinal", type=int, action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--request-budget", type=int, default=3600)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    routes = ModelRoutes.load(args.model_routes).require(REQUIRED_ROUTES)
    builder_code_sha256 = code_fingerprint()
    if {
        routes.provider_config(name)["model"] for name in REQUIRED_ROUTES
    } != {"claude-fable-5"}:
        raise ValueError("active task builder requires claude-fable-5 for every role")
    source = load_source_packages(args.source_packages)
    reviews = load_source_reviews(args.reviews)
    t2_results = load_t2_results(args.t2_run_dir)
    selected, eligible = selected_ordinals(args, source, reviews)
    retry_ceiling = len(eligible) * 14
    if retry_ceiling > args.request_budget:
        raise ValueError(
            f"retry ceiling {retry_ceiling} exceeds request budget {args.request_budget}"
        )

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    builder = TaskPackageBuilder(ROOT, routes, t2_results=t2_results)
    packages = {}
    futures = {}
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for ordinal in selected:
            target = output / f"scenario_{ordinal:03d}.json"
            if args.resume and target.is_file():
                saved = load(target)
                if (
                    saved.get("builder") == BUILDER_ID
                    and saved.get("model_routes_sha256") == routes.sha256
                    and saved.get("builder_code_sha256") == builder_code_sha256
                ):
                    enriched = builder.attach_t2(saved)
                    if enriched != saved:
                        atomic(target, enriched)
                    packages[ordinal] = enriched
                    continue
            old_path, old_package = source[ordinal]
            scenario = load(scenario_path(ordinal))
            future = executor.submit(
                builder.build,
                ordinal,
                old_path,
                old_package,
                reviews[ordinal],
                scenario,
            )
            futures[future] = (ordinal, target)

        for future in as_completed(futures):
            ordinal, target = futures[future]
            package = future.result()
            package["model_routes_sha256"] = routes.sha256
            package["builder_code_sha256"] = builder_code_sha256
            atomic(target, package)
            packages[ordinal] = package
            print(json.dumps({
                "completed": len(packages),
                "selected": len(selected),
                "ordinal": ordinal,
                "scenario_id": package["scenario_id"],
                "status": package["status"],
                "requests": package["request_count"],
            }, ensure_ascii=False), flush=True)

    ordered = [packages[ordinal] for ordinal in selected]
    actual = sum(int(package.get("request_count", 0)) for package in ordered)
    if actual > args.request_budget:
        raise ValueError(
            f"actual requests {actual} exceeded request budget {args.request_budget}"
        )
    print(json.dumps(
        summarize(ordered, routes, output, builder_code_sha256),
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
