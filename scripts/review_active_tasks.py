#!/usr/bin/env python3
"""Run the shared Gate 4 LLM pre-screen over active T1--T3 candidates."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.instance_quality import blind_instance_packet
from prompts.loader import render_prompt
from providers.factory import build_provider, public_provider_config
from providers.model_routes import ModelRoutes
from providers.structured import StructuredOutputError, complete_json
from schemas.validate import validate_instance_quality_judgment


TASK_NAMES = ("T1", "T2", "T3")


def now():
    return datetime.now(timezone.utc).isoformat()


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


def deterministic_seed(instance_id):
    digest = hashlib.sha256(instance_id.encode("utf-8")).hexdigest()
    return 35001 + int(digest[:8], 16) % 2_000_000_000


def source_rows(batch):
    rows = []
    for package_path in sorted((batch / "tasks").glob("scenario_*.json")):
        package = load(package_path)
        for task_name in TASK_NAMES:
            task = package.get("tasks", {}).get(task_name)
            if not task:
                continue
            instance = task["instance"]
            rows.append({
                "ordinal": int(package["ordinal"]),
                "scenario_id": package["scenario_id"],
                "task_name": task_name,
                "instance_id": instance["instance_id"],
                "task_type": instance["task_type"],
                "packet": blind_instance_packet(instance),
            })
    return rows


def update_human_packet(batch, records):
    path = batch / "human_review" / "gate4_tasks.json"
    if not path.exists():
        return
    payload = load(path)
    by_id = {item["instance_id"]: item for item in records}
    for item in payload.get("records", []):
        review = by_id.get(item["instance_id"])
        item["model_quality_review"] = (
            {
                "recommendation": review["recommendation"],
                "scores": review["scores"],
                "fatal_issues": review["fatal_issues"],
                "summary": review["summary"],
                "model": review["model"],
            }
            if review is not None
            else {"recommendation": "pending"}
        )
    payload["llm_screening"] = {
        "strategy": "shared_prompt_full_population_t1_t2_t3",
        "prompt_id": "instance_quality_judge_v2",
        "reviewed_count": len(records),
        "human_review_status": "pending",
    }
    atomic(path, payload)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument("--model-routes", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--request-budget", type=int, default=900)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 8:
        parser.error("workers must be in 1..8")
    if args.max_attempts < 1:
        parser.error("max-attempts must be positive")

    batch = args.batch_root.resolve()
    output = batch / "gate4" / "model_reviews.json"
    routes = ModelRoutes.load(args.model_routes).require(["quality_review"])
    provider_config = routes.provider_config("quality_review")
    rows = source_rows(batch)

    records = []
    if args.resume and output.exists():
        saved = load(output)
        if saved.get("model_routes_sha256") != routes.sha256:
            raise ValueError("Gate4 resume model route provenance mismatch")
        records = list(saved.get("records", []))
    expected_ids = {item["instance_id"] for item in rows}
    records = [item for item in records if item.get("instance_id") in expected_ids]
    completed = {item["instance_id"] for item in records}
    pending = [item for item in rows if item["instance_id"] not in completed]
    if len(pending) * args.max_attempts > args.request_budget:
        raise ValueError("Gate4 retry ceiling exceeds request budget")

    failures = []

    def judge_one(item):
        provider = build_provider(provider_config)
        try:
            judgment = complete_json(
                provider,
                [{
                    "role": "user",
                    "content": render_prompt(
                        "instance_quality_judge_v2",
                        item["packet"],
                    ),
                }],
                {
                    "temperature": 0.1,
                    "top_p": 0.9,
                    "seed": deterministic_seed(item["instance_id"]),
                },
                lambda value: validate_instance_quality_judgment(
                    value,
                    item["task_type"],
                ),
                context=f"Gate4 task quality {item['instance_id']}",
                max_attempts=args.max_attempts,
            )
            return {
                **judgment,
                "ordinal": item["ordinal"],
                "scenario_id": item["scenario_id"],
                "task_name": item["task_name"],
                "instance_id": item["instance_id"],
                "prompt_id": "instance_quality_judge_v2",
                "reviewer_type": "single_model_llm_screen_not_human",
                "model": provider_config["model"],
                "model_route": "quality_review",
                "provider": public_provider_config(provider_config),
                "model_review_request_count": int(
                    getattr(provider, "_call_index", 0) or 0
                ),
                "human_review": "pending",
                "reviewed_at_utc": now(),
            }, None
        except StructuredOutputError as exc:
            return None, {
                "instance_id": item["instance_id"],
                "error_type": type(exc).__name__,
                "message": str(exc),
                "last_error": str(exc.last_error),
                "last_raw": exc.last_raw,
                "diagnostics": deepcopy(exc.diagnostics),
            }
        except Exception as exc:
            return None, {
                "instance_id": item["instance_id"],
                "error_type": type(exc).__name__,
                "message": str(exc),
            }

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(judge_one, item): item for item in pending}
        for future in as_completed(futures):
            item = futures[future]
            record, failure = future.result()
            if record is not None:
                records = [
                    old for old in records
                    if old.get("instance_id") != record["instance_id"]
                ]
                records.append(record)
            else:
                failures.append(failure)
            print(json.dumps({
                "instance_id": item["instance_id"],
                "reviewed": len(records),
                "expected": len(rows),
                "failed": len(failures),
            }, ensure_ascii=False), flush=True)

    ordered = sorted(
        records,
        key=lambda value: (
            int(value["ordinal"]),
            TASK_NAMES.index(value["task_name"]),
        ),
    )
    payload = {
        "format": "socialflux_gate4_single_model_reviews_v1",
        "updated_at_utc": now(),
        "prompt_id": "instance_quality_judge_v2",
        "model_count": 1,
        "model": provider_config["model"],
        "model_routes_sha256": routes.sha256,
        "expected_count": len(rows),
        "reviewed_count": len(ordered),
        "complete": len(ordered) == len(rows) and not failures,
        "recommendation_counts": {
            name: sum(item["recommendation"] == name for item in ordered)
            for name in ("use", "revise", "reject")
        },
        "records": ordered,
        "failures": failures,
    }
    atomic(output, payload)
    update_human_packet(batch, ordered)
    print(json.dumps({
        "reviewed": len(ordered),
        "expected": len(rows),
        "model_count": 1,
        "complete": payload["complete"],
        "output": str(output),
    }, ensure_ascii=False, indent=2))
    if args.require_complete and not payload["complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
