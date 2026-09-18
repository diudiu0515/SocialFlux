#!/usr/bin/env python3
"""Merge resumable Scale300 semantic-review shards without changing judgments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    records = []
    seen = set()
    for path in args.input:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for record in payload.get("records", []):
            trajectory_id = record["trajectory_id"]
            if trajectory_id in seen:
                raise ValueError(f"duplicate trajectory_id: {trajectory_id}")
            seen.add(trajectory_id)
            records.append(record)
    records.sort(key=lambda item: (int(item["ordinal"]), item["trajectory_id"]))
    payload = {
        "format": "socialflux_scale300_model_semantic_reviews_v1",
        "reviewer_type": "qwen32_machine_semantic_review_not_human",
        "human_review": "pending",
        "record_count": len(records),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(args.output)
    print(json.dumps({"output": str(args.output), "records": len(records)}))


if __name__ == "__main__":
    main()
