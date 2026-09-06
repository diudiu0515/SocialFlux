#!/usr/bin/env python3
"""Merge targeted re-judgments into one exact-active-pool judge record."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_formal_rollout_pool import load_records


METADATA_KEYS = (
    "format", "judge_role", "model", "model_family", "provider", "sampling",
)


def merge_evidence(active_ids, payloads):
    if not payloads:
        raise ValueError("at least one judgment payload is required")
    metadata = {key: payloads[0].get(key) for key in METADATA_KEYS}
    if metadata["format"] != "socialflux_rollout_quality_judgments_v1":
        raise ValueError("unsupported rollout judgment format")
    merged = {}
    active_ids = set(active_ids)
    for payload in payloads:
        if any(payload.get(key) != metadata[key] for key in METADATA_KEYS):
            raise ValueError("judgment payload metadata does not match")
        records = payload.get("records")
        if not isinstance(records, list):
            raise ValueError("judgment payload must contain a records list")
        for record in records:
            trajectory_id = record.get("trajectory_id") if isinstance(record, dict) else None
            if not trajectory_id:
                raise ValueError("judgment record lacks trajectory_id")
            if trajectory_id in active_ids:
                merged[trajectory_id] = record
    missing = active_ids - set(merged)
    if missing:
        raise ValueError(
            "judgment evidence is missing active trajectories: "
            + ", ".join(sorted(missing))
        )
    return {
        **metadata,
        "records": [merged[trajectory_id] for trajectory_id in sorted(active_ids)],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--input", dest="inputs", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    active_ids = {item["trajectory_id"] for item in load_records(args.raw_root)}
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in args.inputs]
    result = merge_evidence(active_ids, payloads)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "judge_role": result["judge_role"],
        "trajectory_count": len(result["records"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
