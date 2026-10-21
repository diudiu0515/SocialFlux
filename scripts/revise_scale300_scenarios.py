#!/usr/bin/env python3
"""Create a versioned Claude revision candidate set from Scale300."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prompts.loader import prompt_manifest
from providers.factory import build_provider, public_provider_config
from providers.model_routes import ModelRoutes
from scenario_design.revision import apply_revision, generate_revision
from schemas.validate import validate_scenario
from scripts.run_pipeline import load_scenario_records, select_scenario_records
from scenario_design.catalog import write_catalog, write_document
from shared.artifacts import atomic_json


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "configs" / "scale300_v1" / "scenarios"
DEFAULT_MATRIX = ROOT / "configs" / "scale300_v1" / "design_matrix.json"
DEFAULT_ROUTES = ROOT / "configs" / "model_routes.frontier_api.json"


def now():
    return datetime.now(timezone.utc).isoformat()


def scenario_ordinal(path):
    return int(path.parent.name.rsplit("_", 1)[-1])


def scenario_target(output, ordinal):
    name = f"scenario_{ordinal:03d}"
    return Path(output) / "scenarios" / name / f"{name}.json"


def provider_request_count(provider):
    metrics = getattr(provider, "metrics", {})
    value = metrics.get("request_count") if isinstance(metrics, dict) else None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return int(getattr(provider, "_call_index", 0) or 0)


def revise_one(
    path, scenario, output, route_config, retry_limit, run_attempt,
):
    ordinal = scenario_ordinal(path)
    proposal_path = Path(output) / "proposals" / f"scenario_{ordinal:03d}.json"
    target = scenario_target(output, ordinal)
    provider = build_provider(deepcopy(route_config))
    started = now()
    try:
        revision = generate_revision(
            provider,
            scenario,
            seed=520000 + ordinal,
            max_attempts=retry_limit,
        )
        revised = apply_revision(scenario, revision)
        atomic_json(proposal_path, revision)
        atomic_json(target, revised)
        write_document(target)
        return {
            "scenario_id": scenario["scenario_id"],
            "ordinal": ordinal,
            "run_attempt": run_attempt,
            "status": "completed",
            "decision": revision["decision"],
            "estimated_natural_turn_range": revision[
                "estimated_natural_turn_range"
            ],
            "uses_longitudinal_design": bool(
                revision["patch"]["longitudinal_design"]
            ),
            "task_potential": revision["task_potential"],
            "request_count": provider_request_count(provider),
            "provider_metrics": deepcopy(getattr(provider, "metrics", {})),
            "started_at_utc": started,
            "finished_at_utc": now(),
            "proposal_file": str(proposal_path),
            "scenario_file": str(target),
            "human_review": "pending",
        }
    except Exception as exc:
        failure = {
            "scenario_id": scenario["scenario_id"],
            "ordinal": ordinal,
            "run_attempt": run_attempt,
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "diagnostics": deepcopy(getattr(exc, "diagnostics", [])),
            "request_count": provider_request_count(provider),
            "provider_metrics": deepcopy(getattr(provider, "metrics", {})),
            "started_at_utc": started,
            "finished_at_utc": now(),
            "human_review": "pending",
        }
        atomic_json(
            Path(output) / "failures" / f"scenario_{ordinal:03d}.json",
            failure,
        )
        return failure


def write_matrix(source_matrix, output, results):
    matrix = json.loads(Path(source_matrix).read_text(encoding="utf-8"))
    by_ordinal = {item["ordinal"]: item for item in results}
    rows = []
    for row in matrix["scenarios"]:
        current = deepcopy(row)
        result = by_ordinal.get(int(row["ordinal"]))
        if result and result["status"] == "completed":
            scenario = json.loads(
                scenario_target(output, int(row["ordinal"])).read_text(
                    encoding="utf-8"
                )
            )
            current["title"] = scenario["title"]
            current["generation_status"] = "scenario_revised_rollout_pending"
            current["scenario_revision"] = {
                "model": "claude-fable-5",
                "human_review": "pending",
                "uses_longitudinal_design": result["uses_longitudinal_design"],
                "estimated_natural_turn_range": result[
                    "estimated_natural_turn_range"
                ],
            }
        rows.append(current)
    matrix.update({
        "format": "socialflux_scale300_design_matrix_v2",
        "parent": str(Path(source_matrix).parent),
        "revision_model": "claude-fable-5",
        "human_review": "pending",
        "scenarios": rows,
    })
    atomic_json(Path(output) / "design_matrix.json", matrix)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--source-matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--model-routes", type=Path, default=DEFAULT_ROUTES)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scenario-id", action="append")
    parser.add_argument("--max-scenarios", type=int)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retry-limit", type=int, default=3)
    parser.add_argument("--request-budget", type=int, default=1200)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    if not 1 <= args.workers <= 8:
        raise ValueError("workers must be between 1 and 8")
    if args.retry_limit < 1:
        raise ValueError("retry-limit must be positive")
    records = select_scenario_records(
        load_scenario_records(args.source), args.scenario_id
    )
    if args.max_scenarios is not None:
        records = records[:args.max_scenarios]
    if not records:
        raise ValueError("no scenarios selected")
    ceiling = len(records) * args.retry_limit
    if ceiling > args.request_budget:
        raise ValueError(
            f"retry ceiling {ceiling} exceeds request budget {args.request_budget}"
        )
    routes = ModelRoutes.load(args.model_routes).require([
        "scenario_normalization"
    ])
    route_config = routes.provider_config("scenario_normalization")
    if route_config.get("model") != "claude-fable-5":
        raise ValueError("active scenario revision requires claude-fable-5")
    args.output.mkdir(parents=True, exist_ok=True)
    run_manifest = {
        "format": "socialflux_scenario_revision_run_v1",
        "created_at_utc": now(),
        "status": "in_progress",
        "source": str(args.source),
        "source_matrix": str(args.source_matrix),
        "model_routes": str(args.model_routes),
        "model_routes_sha256": routes.sha256,
        "prompt": prompt_manifest()["prompts"]["scenario_revision_v1"],
        "provider": public_provider_config(route_config),
        "selected_count": len(records),
        "retry_limit": args.retry_limit,
        "request_budget": args.request_budget,
        "attempts": [],
        "results": [],
    }
    manifest_path = args.output / "run_manifest.json"
    if manifest_path.exists() and not args.resume:
        raise ValueError("output already contains a run; pass --resume")
    prior = {}
    attempt_history = []
    if args.resume:
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        if old.get("model_routes_sha256") != routes.sha256:
            raise ValueError("model routes changed; use a new output directory")
        prior = {item["scenario_id"]: item for item in old.get("results", [])}
        attempt_history = deepcopy(
            old.get("attempts", old.get("results", []))
        )
        run_manifest["created_at_utc"] = old.get(
            "created_at_utc", run_manifest["created_at_utc"]
        )
        run_manifest["resume_count"] = int(old.get("resume_count", 0)) + 1
    run_manifest["attempts"] = attempt_history
    atomic_json(manifest_path, run_manifest)

    pending = []
    results = []
    for path, scenario in records:
        old = prior.get(scenario["scenario_id"])
        target = scenario_target(args.output, scenario_ordinal(path))
        if old and old.get("status") == "completed" and target.exists():
            validate_scenario(json.loads(target.read_text(encoding="utf-8")))
            results.append(old)
        else:
            pending.append((path, scenario))

    def refresh_manifest_summary():
        run_manifest["attempts"] = attempt_history
        run_manifest["results"] = sorted(results, key=lambda item: item["ordinal"])
        run_manifest["completed_count"] = sum(
            item["status"] == "completed" for item in results
        )
        run_manifest["failed_count"] = sum(
            item["status"] == "failed" for item in results
        )
        run_manifest["actual_request_count"] = sum(
            int(item.get("request_count", 0)) for item in attempt_history
        )
        run_manifest["updated_at_utc"] = now()

    def record(result):
        attempt_history.append(result)
        results[:] = [
            item for item in results
            if item["scenario_id"] != result["scenario_id"]
        ]
        results.append(result)
        refresh_manifest_summary()
        atomic_json(manifest_path, run_manifest)
        print(
            f"[{len(results)}/{len(records)}] {result['status']} "
            f"{result['scenario_id']}",
            flush=True,
        )

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        prior_attempt_counts = {
            scenario_id: sum(
                item.get("scenario_id") == scenario_id
                for item in attempt_history
            )
            for _, scenario in pending
            for scenario_id in [scenario["scenario_id"]]
        }
        futures = {
            executor.submit(
                revise_one, path, scenario, args.output, route_config,
                args.retry_limit,
                prior_attempt_counts.get(scenario["scenario_id"], 0) + 1,
            ): scenario["scenario_id"]
            for path, scenario in pending
        }
        for future in as_completed(futures):
            record(future.result())

    refresh_manifest_summary()
    if (args.output / "scenarios").exists():
        write_catalog(args.output / "scenarios")
        write_matrix(args.source_matrix, args.output, results)
    run_manifest["status"] = (
        "completed" if len(results) == len(records)
        and all(item["status"] == "completed" for item in results)
        else "completed_with_failures"
    )
    run_manifest["finished_at_utc"] = now()
    atomic_json(manifest_path, run_manifest)
    print(json.dumps({
        "status": run_manifest["status"],
        "completed": run_manifest.get("completed_count", 0),
        "failed": run_manifest.get("failed_count", 0),
        "requests": run_manifest.get("actual_request_count", 0),
        "output": str(args.output),
    }, ensure_ascii=False))
    if run_manifest["status"] != "completed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
