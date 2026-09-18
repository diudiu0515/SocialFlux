#!/usr/bin/env python3
"""CLI for the run-scoped, source-adapted T2 v2 pipeline."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tasks.T2.runtime import ROOT, load
from tasks.T2.configuration import load_t2_config
from tasks.T2.answering import validate_answer
from tasks.T2.pair_builder import T2PairBuilder, cross_speaker_echo_violations
from tasks.T2.run_artifacts import (
    initialize_run,
    count_requests,
    result_name,
    summarize_run,
    write_result,
)
from tasks.T2.source_selection import source_index


SPEC_PATH = ROOT / "configs" / "t2_source_adaptation_v2.json"
AUDIT_PATH = ROOT / "build" / "scale300_v1" / "automatic_gate_audit.json"
OUT = ROOT / "build" / "t2_source_adapted"


def _default_run_id():
    return datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")


def _safe_run_id(value):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        raise argparse.ArgumentTypeError(
            "run id may contain only letters, digits, dot, dash, underscore"
        )
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=SPEC_PATH)
    parser.add_argument("--audit", type=Path, default=AUDIT_PATH)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--run-id", type=_safe_run_id, default=None)
    parser.add_argument("--spec-index", type=int)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--resume-failed", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--request-budget", type=int, default=6000)
    parser.add_argument("--summarize", action="store_true")
    args = parser.parse_args()

    config_path = args.config.resolve()
    config, specs, pair_source, model_routes = load_t2_config(ROOT, config_path)
    run_id = args.run_id or _default_run_id()
    run_dir = args.output.resolve() / run_id
    initialize_run(
        run_dir,
        run_id=run_id,
        config_path=config_path,
        pair_source=pair_source,
        specs=specs,
        model_routes=model_routes,
    )
    if args.summarize:
        print(json.dumps(summarize_run(run_dir), ensure_ascii=False, indent=2))
        return
    if args.all == (args.spec_index is not None):
        parser.error("choose exactly one of --all or --spec-index")
    indexes = list(range(len(specs))) if args.all else [args.spec_index]
    if any(index < 0 or index >= len(specs) for index in indexes):
        parser.error("spec index out of range")
    if args.resume_failed and args.skip_existing:
        parser.error("resume-failed and skip-existing are mutually exclusive")
    retry_ceiling = len(indexes) * 40
    if retry_ceiling > args.request_budget:
        parser.error(
            f"retry ceiling {retry_ceiling} exceeds request budget "
            f"{args.request_budget}"
        )

    builder = T2PairBuilder(
        model_routes,
        load(args.audit),
        run_id=run_id,
        selection_settings=config.get("source_selection"),
    )
    def build_index(index):
        prior_path = run_dir / "results" / result_name(index, specs[index])
        if args.resume_failed:
            if not prior_path.exists():
                raise ValueError(f"no saved result to resume: {prior_path}")
            return builder.resume(specs[index], load(prior_path))
        return builder.build(specs[index])

    submitted = []
    request_count = 0
    futures = {}
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for index in indexes:
            prior_path = run_dir / "results" / result_name(index, specs[index])
            if args.skip_existing and prior_path.exists():
                continue
            futures[executor.submit(build_index, index)] = index
        for future in as_completed(futures):
            index = futures[future]
            result = future.result()
            artifact = write_result(run_dir, index, specs[index], result)
            submitted.append(index)
            pair_counts = (result.get("pair") or {}).get("request_counts")
            request_count += count_requests(
                pair_counts or result.get("request_counts", {})
            )
            print(json.dumps({
                "completed_this_invocation": len(submitted),
                "submitted_this_invocation": len(futures),
                "spec_index": index,
                "ordinal": specs[index]["ordinal"],
                "scenario_id": result.get("scenario_id"),
                "status": result["status"],
                "stage": result["stage"],
                "artifact": str(artifact.relative_to(ROOT)),
            }, ensure_ascii=False), flush=True)
    if request_count > args.request_budget:
        raise ValueError(
            f"actual requests {request_count} exceeded budget {args.request_budget}"
        )
    print(json.dumps(summarize_run(run_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
