#!/usr/bin/env python3
"""Run one-model Gate 3 semantic review over every active rollout."""

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

from evaluation.rollout_gate import public_judge_packet
from evaluation.rollout_semantic_review import validate_judgment
from prompts.loader import render_prompt
from providers.factory import build_provider, public_provider_config
from providers.model_routes import ModelRoutes
from providers.structured import StructuredOutputError, complete_json


ROOT = Path(__file__).resolve().parents[1]


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


def deterministic_seed(trajectory_id):
    digest = hashlib.sha256(trajectory_id.encode("utf-8")).hexdigest()
    return 33001 + int(digest[:8], 16) % 2_000_000_000


def decision(judgment):
    scores = judgment["scores"]
    passed = (
        not judgment["hard_reject_reasons"]
        and all(value >= 3 for value in scores.values())
        and scores["history_dependence"] >= 4
        and scores["character_consistency"] >= 4
        and scores["naturalness"] >= 4
    )
    return "approve" if passed else "reject"


def source_rows(batch, count):
    rows = []
    for ordinal in range(1, count + 1):
        package_path = (
            batch / "source_packages" / "shard1"
            / f"scenario_{ordinal:03d}.json"
        )
        package = load(package_path)
        trajectory_path = ROOT / package["source_artifact"]
        scenario_path = (
            batch / "scenarios" / f"scenario_{ordinal:03d}"
            / f"scenario_{ordinal:03d}.json"
        )
        rows.append({
            "ordinal": ordinal,
            "scenario_id": package["scenario_id"],
            "trajectory_id": package["source_trajectory_id"],
            "trajectory_path": trajectory_path,
            "scenario_path": scenario_path,
        })
    return rows


def update_review_files(batch, records):
    by_ordinal = {int(item["ordinal"]): item for item in records}
    source_path = batch / "source_review.json"
    source_review = load(source_path)
    for candidate in source_review.get("candidates", []):
        review = by_ordinal.get(int(candidate["ordinal"]))
        if review is None:
            candidate["model_semantic_review"] = {
                "decision": "pending",
                "reviewer_type": "not_run",
            }
            continue
        candidate["model_semantic_review"] = {
            "decision": review["decision"],
            "scores": review["scores"],
            "hard_reject_reasons": review["hard_reject_reasons"],
            "reviewer_type": review["reviewer_type"],
            "model": review["model"],
            "reviewed_at_utc": review["reviewed_at_utc"],
        }
    atomic(source_path, source_review)

    human_path = batch / "human_review" / "gate3_rollouts.json"
    human = load(human_path)
    for item in human.get("records", []):
        review = by_ordinal.get(int(item["ordinal"]))
        item["model_semantic_review"] = (
            {
                "decision": review["decision"],
                "scores": review["scores"],
                "hard_reject_reasons": review["hard_reject_reasons"],
                "model": review["model"],
            }
            if review is not None else {"decision": "pending"}
        )
    human["llm_screening"] = {
        "strategy": "single_model_full_population",
        "model_count": 1,
        "reviewed_count": len(records),
        "human_sampling_status": "pending",
    }
    atomic(human_path, human)

    audit_path = batch / "automatic_gate_audit.json"
    audit = load(audit_path)
    for item in audit.get("records", []):
        review = by_ordinal.get(int(item["ordinal"]))
        if review is not None:
            item["gates"]["gate3"]["model_semantic_review"] = {
                "decision": review["decision"],
                "scores": review["scores"],
                "hard_reject_reasons": review["hard_reject_reasons"],
            }
    atomic(audit_path, audit)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument("--model-routes", type=Path, required=True)
    parser.add_argument("--count", type=int, default=150)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--request-budget", type=int, default=450)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 8:
        parser.error("workers must be in 1..8")
    batch = args.batch_root.resolve()
    output = batch / "gate3" / "model_reviews.json"
    routes = ModelRoutes.load(args.model_routes).require(["quality_review"])
    provider_config = routes.provider_config("quality_review")
    rows = source_rows(batch, args.count)

    records = []
    if args.resume and output.exists():
        saved = load(output)
        if saved.get("model_routes_sha256") != routes.sha256:
            raise ValueError("Gate3 resume model route provenance mismatch")
        records = list(saved.get("records", []))
    completed = {
        item["trajectory_id"] for item in records
        if item.get("decision") in {"approve", "reject"}
    }
    pending = [item for item in rows if item["trajectory_id"] not in completed]
    if len(pending) * args.max_attempts > args.request_budget:
        raise ValueError("Gate3 retry ceiling exceeds request budget")

    failures = []

    def judge_one(item):
        trajectory = load(item["trajectory_path"])
        scenario = load(item["scenario_path"])
        trajectory_id = item["trajectory_id"]
        provider = build_provider(provider_config)
        try:
            judgment = complete_json(
                provider,
                [{
                    "role": "user",
                    "content": render_prompt(
                        "rollout_quality_judge_v2",
                        public_judge_packet(trajectory, scenario),
                    ),
                }],
                {
                    "temperature": 0.1,
                    "top_p": 0.9,
                    "seed": deterministic_seed(trajectory_id),
                },
                lambda value: validate_judgment(
                    value,
                    trajectory_id,
                    {turn["turn_id"] for turn in trajectory["turns"]},
                ),
                context=f"Gate3 semantic review {trajectory_id}",
                max_attempts=args.max_attempts,
            )
            return {
                **judgment,
                "ordinal": item["ordinal"],
                "scenario_id": item["scenario_id"],
                "decision": decision(judgment),
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
                "ordinal": item["ordinal"],
                "scenario_id": item["scenario_id"],
                "trajectory_id": trajectory_id,
                "error_type": type(exc).__name__,
                "message": str(exc),
                "last_error": str(exc.last_error),
                "last_raw": exc.last_raw,
                "diagnostics": deepcopy(exc.diagnostics),
            }
        except Exception as exc:
            return None, {
                "ordinal": item["ordinal"],
                "scenario_id": item["scenario_id"],
                "trajectory_id": trajectory_id,
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
                    if old.get("trajectory_id") != record["trajectory_id"]
                ]
                records.append(record)
            else:
                failures.append(failure)
            ordered = sorted(records, key=lambda value: int(value["ordinal"]))
            payload = {
                "format": "socialflux_gate3_single_model_reviews_v1",
                "updated_at_utc": now(),
                "model_count": 1,
                "model": provider_config["model"],
                "model_routes_sha256": routes.sha256,
                "expected_count": args.count,
                "reviewed_count": len(ordered),
                "complete": len(ordered) == args.count and not failures,
                "records": ordered,
                "failures": failures,
            }
            atomic(output, payload)
            print(json.dumps({
                "ordinal": item["ordinal"],
                "reviewed": len(ordered),
                "failed": len(failures),
            }), flush=True)

    ordered = sorted(records, key=lambda value: int(value["ordinal"]))
    payload = {
        "format": "socialflux_gate3_single_model_reviews_v1",
        "updated_at_utc": now(),
        "model_count": 1,
        "model": provider_config["model"],
        "model_routes_sha256": routes.sha256,
        "expected_count": args.count,
        "reviewed_count": len(ordered),
        "complete": len(ordered) == args.count and not failures,
        "decision_counts": {
            name: sum(item["decision"] == name for item in ordered)
            for name in ("approve", "reject")
        },
        "records": ordered,
        "failures": failures,
    }
    atomic(output, payload)
    update_review_files(batch, ordered)
    print(json.dumps({
        "reviewed": len(ordered),
        "expected": args.count,
        "model_count": 1,
        "complete": payload["complete"],
        "output": str(output),
    }, ensure_ascii=False, indent=2))
    if args.require_complete and not payload["complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
