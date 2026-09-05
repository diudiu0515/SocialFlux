#!/usr/bin/env python3
"""Prepare unsigned, hash-bound Gate 4 human review records."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.instance_quality import blind_instance_packet
from evaluation.rollout_gate import content_sha256
from evaluation.quality_gates import TASK_REVIEW_RATINGS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instances", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    instances = [
        json.loads(line) for line in args.instances.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    records = []
    for instance in instances:
        records.append({
            "instance_id": instance["instance_id"],
            "instance_sha256": content_sha256(instance),
            "reviewer": "",
            "reviewed_at_utc": "",
            "review_status": "pending",
            "human_attestation": False,
            "ratings": {
                key: None
                for key in sorted(TASK_REVIEW_RATINGS[instance["task_type"]])
            },
            "notes": "",
            "blind_packet": blind_instance_packet(instance),
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records),
        encoding="utf-8",
    )
    print(json.dumps({"review_packets": len(records), "output": str(args.output)}))


if __name__ == "__main__":
    main()
