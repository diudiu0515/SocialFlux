#!/usr/bin/env python3
"""Prepare an unsigned Gate 4 same-sample double-audit packet."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.instance_quality import blind_instance_packet
from evaluation.rollout_gate import content_sha256
from evaluation.quality_gates import TASK_REVIEW_RATINGS, deterministic_task_review_sample


def blank_review(task_type):
    return {
        "reviewer": "",
        "reviewed_at_utc": "",
        "review_status": "pending",
        "human_attestation": False,
        "ratings": {
            key: None for key in sorted(TASK_REVIEW_RATINGS[task_type])
        },
        "notes": "",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instances", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fraction", type=float, default=0.10)
    parser.add_argument("--minimum-per-task", type=int, default=2)
    args = parser.parse_args()
    instances = [
        json.loads(line) for line in args.instances.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    records = []
    sampled = deterministic_task_review_sample(
        instances, args.fraction, args.minimum_per_task
    )
    for instance in sampled:
        records.append({
            "instance_id": instance["instance_id"],
            "instance_sha256": content_sha256(instance),
            "reviews": {
                "reviewer_a": blank_review(instance["task_type"]),
                "reviewer_b": blank_review(instance["task_type"]),
            },
            "adjudication": blank_review(instance["task_type"]),
            "blind_packet": blind_instance_packet(instance),
        })
    payload = {
        "format": "socialflux_gate4_double_audit_v2",
        "sampling": {
            "strategy": "sha256_ranked_stratified_by_task_type_v1",
            "fraction_per_task_type": args.fraction,
            "minimum_per_task_type": args.minimum_per_task,
            "same_sample_for_both_reviewers": True,
            "population_count": len(instances),
            "sample_count": len(records),
        },
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"population": len(instances), "review_packets": len(records), "output": str(args.output)}))


if __name__ == "__main__":
    main()
