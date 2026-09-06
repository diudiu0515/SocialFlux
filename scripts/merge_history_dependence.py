#!/usr/bin/env python3
"""Merge targeted history rechecks into evidence for the exact active pool."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_formal_rollout_pool import load_records


def merge_records(active_ids, payloads):
    active_ids = set(active_ids)
    merged = {}
    for payload in payloads:
        records = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(records, list):
            raise ValueError("history evidence input must contain a records list")
        for record in records:
            trajectory_id = record.get("trajectory_id") if isinstance(record, dict) else None
            if not trajectory_id:
                raise ValueError("history evidence record lacks trajectory_id")
            if trajectory_id in active_ids:
                merged[trajectory_id] = record
    missing = active_ids - set(merged)
    if missing:
        raise ValueError(
            "history evidence is missing active trajectories: "
            + ", ".join(sorted(missing))
        )
    return [merged[trajectory_id] for trajectory_id in sorted(active_ids)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--input", dest="inputs", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    active_ids = {
        item["trajectory_id"] for item in load_records(args.raw_root)
    }
    payloads = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in args.inputs
    ]
    records = merge_records(active_ids, payloads)
    result = {
        "format": "socialflux_history_dependence_evidence_v1",
        "source_files": [str(path) for path in args.inputs],
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "trajectory_count": len(records),
        "passed": sum(record.get("passed") is True for record in records),
        "rejected": sum(record.get("passed") is not True for record in records),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
