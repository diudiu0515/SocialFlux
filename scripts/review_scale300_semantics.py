#!/usr/bin/env python3
"""Run a resumable machine semantic review over current Scale300 trajectories."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.rollout_gate import public_judge_packet
from prompts.loader import render_prompt
from providers.factory import build_provider
from providers.model_routes import ModelRoutes
from providers.structured import StructuredOutputError, complete_json
from evaluation.rollout_semantic_review import validate_judgment


ROOT = Path(__file__).resolve().parents[1]
MODEL_ROUTES = ROOT / "configs" / "model_routes.frontier_api.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def deterministic_seed(trajectory_id):
    return 33001 + int(hashlib.sha256(trajectory_id.encode()).hexdigest()[:8], 16) % 2_000_000_000


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--scenarios", type=Path, required=True)
    parser.add_argument("--model-routes", type=Path, default=MODEL_ROUTES)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shard-count", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.shard_index <= args.shard_count:
        raise ValueError("invalid shard index")
    model_routes = ModelRoutes.load(args.model_routes).require(["quality_review"])
    provider = build_provider(model_routes.provider_config("quality_review"))
    review = read(args.review)
    records = []
    if args.resume and args.output.is_file():
        records = read(args.output).get("records", [])
    completed = {item["trajectory_id"] for item in records}
    for candidate in review["candidates"]:
        ordinal = int(candidate["ordinal"])
        if (ordinal - 1) % args.shard_count != args.shard_index - 1:
            continue
        latest = candidate.get("latest_attempt") or {}
        trajectory_id = latest.get("trajectory_id")
        artifact = latest.get("artifact_path")
        if not trajectory_id or trajectory_id in completed or not artifact:
            continue
        trajectory_path = ROOT / artifact
        if not trajectory_path.is_file():
            continue
        trajectory = read(trajectory_path)
        if not trajectory.get("turns"):
            continue
        scenario_path = (
            args.scenarios / f"scenario_{ordinal:03d}" / f"scenario_{ordinal:03d}.json"
        )
        scenario = read(scenario_path)
        prompt = render_prompt(
            "rollout_quality_judge_v2", public_judge_packet(trajectory, scenario)
        )
        provider.reset()
        try:
            judgment = complete_json(
                provider,
                [{"role": "user", "content": prompt}],
                {"temperature": 0.1, "seed": deterministic_seed(trajectory_id)},
                lambda value: validate_judgment(
                    value,
                    trajectory_id,
                    {turn["turn_id"] for turn in trajectory["turns"]},
                ),
                context=f"Scale300 semantic review {trajectory_id}",
                max_attempts=args.max_attempts,
            )
            record = {
                **judgment,
                "scenario_id": candidate["scenario_id"],
                "ordinal": ordinal,
                "decision": decision(judgment),
                "reviewer_type": "llm_machine_semantic_review_not_human",
                "model_route": "quality_review",
                **provider.provenance,
                "human_review": "pending",
                "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        except StructuredOutputError as exc:
            record = {
                "trajectory_id": trajectory_id,
                "scenario_id": candidate["scenario_id"],
                "ordinal": ordinal,
                "decision": "model_review_error",
                "error": str(exc),
                "reviewer_type": "llm_machine_semantic_review_not_human",
                "model_route": "quality_review",
                **provider.provenance,
                "human_review": "pending",
                "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        records.append(record)
        completed.add(trajectory_id)
        atomic_json(args.output, {
            "format": "socialflux_scale300_model_semantic_reviews_shard_v1",
            "shard_index": args.shard_index,
            "model_routes_path": str(model_routes.source_path),
            "model_routes_sha256": model_routes.sha256,
            "shard_count": args.shard_count,
            "records": records,
        })
        print(json.dumps({
            "ordinal": ordinal,
            "decision": record["decision"],
            "checkpointed": len(records),
        }), flush=True)


if __name__ == "__main__":
    main()
