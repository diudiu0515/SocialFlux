#!/usr/bin/env python3
"""Run an independent schema-constrained judge over observable trajectories."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.rollout_gate import public_judge_packet
from evaluation.review_configuration import (
    load_review_config,
    public_review_profile,
)
from evaluation.rollout_semantic_review import (
    deterministic_review_sampling,
    validate_judgment,
)
from prompts.loader import render_prompt
from providers.factory import build_provider
from providers.structured import StructuredOutputError, complete_json
from scripts.audit_formal_rollout_pool import load_records
from scripts.run_pipeline import load_scenarios


def write_checkpoint(
    path, args, review_config, profile_name, records, failures=None,
):
    profile = public_review_profile(review_config, profile_name)
    ordered_records = sorted(records, key=lambda item: item["trajectory_id"])
    ordered_failures = sorted(
        failures or [], key=lambda item: item["trajectory_id"]
    )
    payload = {
        "format": "socialflux_rollout_quality_judgments_v3",
        "judge_role": args.judge_role,
        "review_profile": profile,
        "model": profile["provider"].get("model"),
        "model_family": "claude",
        "records": ordered_records,
        "failures": ordered_failures,
        "actual_requests_including_retries": sum(
            int(record.get("model_review_request_count", 0))
            for record in ordered_records
        ) + sum(
            int(record.get("request_count", 0))
            for record in ordered_failures
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument(
        "--scenarios", type=Path, default=Path("configs/scenarios"),
        help="scenario bundle used to build observable judge packets",
    )
    parser.add_argument(
        "--review-config",
        type=Path,
        default=Path("configs/review_models.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--judge-role", choices=("primary", "secondary"), required=True)
    parser.add_argument(
        "--trajectory-id-file",
        type=Path,
        help="optional JSON selection emitted by merge_rollout_judgments.py",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="reuse validated records already checkpointed in --output",
    )
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--request-budget", type=int, default=5000)
    args = parser.parse_args()
    review_config = load_review_config(args.review_config)
    profile_name = f"rollout_{args.judge_role}"
    profile = review_config["profiles"][profile_name]
    sampling = profile.get("sampling", {})
    selected_ids = None
    if args.trajectory_id_file:
        selection = json.loads(args.trajectory_id_file.read_text(encoding="utf-8"))
        selected_ids = set(selection.get("trajectory_ids", []))
        if not selected_ids:
            raise ValueError("trajectory selection is empty")
    records = []
    failures = []
    if args.resume and args.output.exists():
        checkpoint = json.loads(args.output.read_text(encoding="utf-8"))
        if (
            checkpoint.get("judge_role") != args.judge_role
            or checkpoint.get("review_profile", {}).get("model_routes", {}).get("sha256")
            != review_config["model_routes_provenance"]["sha256"]
            or checkpoint.get("model") != profile["provider"].get("model")
        ):
            raise ValueError("resume checkpoint judge provenance mismatch")
        records = list(checkpoint.get("records", []))
        failures = list(checkpoint.get("failures", []))
    completed_ids = {item["trajectory_id"] for item in records}
    scenarios = {
        item["scenario_id"]: item for item in load_scenarios(args.scenarios)
    }
    pending = []
    for trajectory in load_records(args.raw_root):
        trajectory_id = trajectory["trajectory_id"]
        if selected_ids is not None and trajectory_id not in selected_ids:
            continue
        if trajectory_id in completed_ids:
            continue
        pending.append(trajectory)
    retry_ceiling = len(pending) * args.max_attempts
    if retry_ceiling > args.request_budget:
        raise ValueError(
            f"retry ceiling {retry_ceiling} exceeds request budget "
            f"{args.request_budget}"
        )

    def judge_one(trajectory):
        trajectory_id = trajectory["trajectory_id"]
        prompt = render_prompt(
            "rollout_quality_judge_v2",
            public_judge_packet(trajectory, scenarios[trajectory["scenario_id"]]),
        )
        provider = build_provider(profile["provider"])
        try:
            judgment = complete_json(
                provider,
                [{"role": "user", "content": prompt}],
                deterministic_review_sampling(sampling, trajectory_id),
                lambda value, trajectory_id=trajectory_id, trajectory=trajectory: validate_judgment(
                    value, trajectory_id, {item["turn_id"] for item in trajectory["turns"]}
                ),
                context=f"quality judgment {trajectory_id}",
                max_attempts=args.max_attempts,
            )
            judgment["model_review_request_count"] = int(
                getattr(provider, "_call_index", 0) or 0
            )
            return judgment, None
        except StructuredOutputError as exc:
            return None, {
                "trajectory_id": trajectory_id,
                "last_error": str(exc.last_error),
                "last_raw": exc.last_raw,
                "attempt_diagnostics": deepcopy(exc.diagnostics),
                "request_count": int(getattr(provider, "_call_index", 0) or 0),
            }
        except Exception as exc:
            return None, {
                "trajectory_id": trajectory_id,
                "error_type": type(exc).__name__,
                "message": str(exc),
                "request_count": int(getattr(provider, "_call_index", 0) or 0),
            }

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(judge_one, trajectory): trajectory["trajectory_id"]
            for trajectory in pending
        }
        for future in as_completed(futures):
            trajectory_id = futures[future]
            judgment, failure = future.result()
            failures = [
                item for item in failures
                if item.get("trajectory_id") != trajectory_id
            ]
            if judgment is not None:
                records.append(judgment)
                completed_ids.add(trajectory_id)
            else:
                failures.append(failure)
            write_checkpoint(
                args.output, args, review_config, profile_name, records, failures
            )
            print(json.dumps({
                "processed": len(records) + len(failures),
                "checkpointed": len(records),
                "failed": len(failures),
                "trajectory_id": trajectory_id,
            }), flush=True)
    if selected_ids is not None:
        judged_ids = {item["trajectory_id"] for item in records}
        missing = sorted(selected_ids - judged_ids)
        if missing:
            raise ValueError("selected trajectories were not found: " + ", ".join(missing))
    write_checkpoint(
        args.output, args, review_config, profile_name, records, failures
    )
    print(json.dumps({
        "judged": len(records),
        "failed": len(failures),
        "output": str(args.output),
    }, ensure_ascii=False))
    if failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
