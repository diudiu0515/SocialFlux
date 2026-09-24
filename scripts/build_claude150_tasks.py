#!/usr/bin/env python3
"""Build Claude150 T1--T4 candidates without gate-order blocking."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.instance_quality import blind_instance_packet
from evaluation.rollout_gate import content_sha256
from providers.model_routes import ModelRoutes
from scripts.audit_active_batch import package_complete
from tasks.package_builder import BUILDER_ID, TaskPackageBuilder
from tasks.source_catalog import load_source_packages, load_source_reviews


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BATCH = ROOT / "data" / "claude150_v1"
DEFAULT_ROUTES = ROOT / "configs" / "claude150_v1" / "model_routes.json"
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
    "scripts/build_claude150_tasks.py",
)


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
        value = load(path)
        ordinal = int(value["ordinal"])
        if ordinal in records:
            raise ValueError(f"duplicate T2 result ordinal: {ordinal}")
        records[ordinal] = value
    return records


def review_record(package, task_name, task):
    instance = task["instance"]
    return {
        "ordinal": package["ordinal"],
        "scenario_id": package["scenario_id"],
        "task_type": task_name,
        "instance_id": instance.get(
            "instance_id",
            f"{package['scenario_id']}:{task_name}",
        ),
        "instance_sha256": content_sha256(instance),
        "blind_packet": blind_instance_packet(instance),
        "machine_proposal": task.get("llm_answer"),
        "machine_proposal_status": task.get("answer_status"),
        "source_trajectory_id": package.get("source_trajectory_id"),
        "reviewer": "",
        "reviewed_at_utc": "",
        "decision": "pending",
        "human_attestation": False,
        "ratings": {
            "source_grounding": None,
            "answer_correctness": None,
            "ambiguity_control": None,
            "leakage_safety": None,
            "research_utility": None,
        },
        "notes": "",
    }


def summarize(packages, routes, output, code_sha):
    task_counts = {name: 0 for name in ("T1", "T2", "T3", "T4")}
    error_counts = {name: 0 for name in ("extraction", "T1", "T2", "T3", "T4")}
    gap_counts = {name: 0 for name in ("T1", "T2", "T3", "T4")}
    status_counts = {}
    review_records = []
    for package in packages:
        status = package["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
        for name, task in package.get("tasks", {}).items():
            task_counts[name] += 1
            review_records.append(review_record(package, name, task))
        for name in package.get("task_errors", {}):
            error_counts[name] = error_counts.get(name, 0) + 1
        for name in package.get("task_gaps", {}):
            gap_counts[name] = gap_counts.get(name, 0) + 1
    complete_ordinals = [
        int(item["ordinal"]) for item in packages if package_complete(item)
    ]
    summary = {
        "format": "socialflux_claude150_task_summary_v1",
        "builder": BUILDER_ID,
        "model": "claude-fable-5",
        "model_routes_sha256": routes.sha256,
        "builder_code_sha256": code_sha,
        "package_count": len(packages),
        "complete_package_count": len(complete_ordinals),
        "complete": len(complete_ordinals) == len(packages),
        "incomplete_ordinals": sorted(set(range(1, len(packages) + 1)) - set(complete_ordinals)),
        "status_counts": status_counts,
        "task_answer_counts": task_counts,
        "task_error_counts": error_counts,
        "task_gap_counts": gap_counts,
        "actual_requests_including_retries": sum(
            int(item.get("request_count", 0)) for item in packages
        ),
        "admission": "generate_all_then_human_postfilter",
        "human_review": "pending",
    }
    atomic(output / "summary.json", summary)
    atomic(output.parent / "human_review" / "gate4_tasks.json", {
        "format": "socialflux_claude150_gate4_full_review_v1",
        "population_count": len(review_records),
        "sample_count": len(review_records),
        "sampling": "full_population",
        "instructions": (
            "Review every generated task candidate. Machine proposals and model "
            "reviews are aids only, never human ground truth."
        ),
        "records": review_records,
    })
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-root", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--model-routes", type=Path, default=DEFAULT_ROUTES)
    parser.add_argument("--t2-run-dir", type=Path)
    parser.add_argument("--count", type=int, default=150)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--request-budget", type=int, default=2400)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 8:
        parser.error("workers must be in 1..8")
    batch = args.batch_root.resolve()
    output = batch / "tasks"
    routes = ModelRoutes.load(args.model_routes).require(REQUIRED_ROUTES)
    if {
        routes.provider_config(name)["model"] for name in REQUIRED_ROUTES
    } != {"claude-fable-5"}:
        raise ValueError("every task role must use claude-fable-5")
    source = load_source_packages(
        batch / "source_packages",
        expected_count=args.count,
    )
    reviews = load_source_reviews(batch / "source_review.json")
    if set(reviews) != set(range(1, args.count + 1)):
        raise ValueError("source reviews do not cover the full candidate population")
    retry_ceiling = args.count * 14
    if retry_ceiling > args.request_budget:
        raise ValueError(
            f"retry ceiling {retry_ceiling} exceeds request budget {args.request_budget}"
        )
    t2_results = load_t2_results(args.t2_run_dir)
    code_sha = fingerprint()
    builder = TaskPackageBuilder(
        ROOT,
        routes,
        t2_results=t2_results,
        candidate_mode=True,
    )
    output.mkdir(parents=True, exist_ok=True)
    packages = {}
    futures = {}
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for ordinal in range(1, args.count + 1):
            target = output / f"scenario_{ordinal:03d}.json"
            if args.resume and target.exists():
                saved = load(target)
                if (
                    saved.get("builder") == BUILDER_ID
                    and saved.get("model_routes_sha256") == routes.sha256
                    and saved.get("builder_code_sha256") == code_sha
                ):
                    enriched = builder.attach_t2(saved)
                    if enriched != saved:
                        atomic(target, enriched)
                    if package_complete(enriched):
                        packages[ordinal] = enriched
                        continue
            name = f"scenario_{ordinal:03d}"
            scenario = load(batch / "scenarios" / name / f"{name}.json")
            source_path, source_package = source[ordinal]
            future = executor.submit(
                builder.build,
                ordinal,
                source_path,
                source_package,
                reviews[ordinal],
                scenario,
            )
            futures[future] = (ordinal, target)
        for future in as_completed(futures):
            ordinal, target = futures[future]
            package = future.result()
            package["model_routes_sha256"] = routes.sha256
            package["builder_code_sha256"] = code_sha
            atomic(target, package)
            packages[ordinal] = package
            print(json.dumps({
                "stage": "tasks",
                "completed": len(packages),
                "expected": args.count,
                "ordinal": ordinal,
                "status": package["status"],
                "tasks": sorted(package.get("tasks", {})),
                "requests": package.get("request_count", 0),
            }, ensure_ascii=False), flush=True)
    ordered = [packages[ordinal] for ordinal in range(1, args.count + 1)]
    actual = sum(int(item.get("request_count", 0)) for item in ordered)
    if actual > args.request_budget:
        raise ValueError(
            f"actual requests {actual} exceeded budget {args.request_budget}"
        )
    summary = summarize(ordered, routes, output, code_sha)
    print(json.dumps(
        summary,
        ensure_ascii=False,
        indent=2,
    ))
    if args.require_complete and not summary["complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
