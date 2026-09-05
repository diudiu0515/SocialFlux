#!/usr/bin/env python3
"""Select second-judge cases or merge completed independent judgments."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.judge_protocol import merge_judgments, required_secondary_ids
from scripts.audit_formal_rollout_pool import load_records


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--secondary", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fraction", type=float, default=0.20)
    args = parser.parse_args()
    if not 0 < args.fraction <= 1:
        raise ValueError("--fraction must be in (0, 1]")
    trajectories = load_records(args.raw_root)
    primary = read(args.primary)
    if args.secondary is None:
        reasons = required_secondary_ids(trajectories, primary.get("records", []), args.fraction)
        result = {
            "format": "socialflux_secondary_judge_selection_v1",
            "trajectory_ids": sorted(reasons),
            "selection_reasons": reasons,
        }
    else:
        result = merge_judgments(trajectories, primary, read(args.secondary), args.fraction)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "count": len(result.get("trajectory_ids", result.get("records", []))), "complete": result.get("complete")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
