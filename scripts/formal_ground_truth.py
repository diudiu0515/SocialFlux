#!/usr/bin/env python3
"""Prepare blinded human packets or finalize 3-annotator formal GT."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from annotation.formal_gt import build_annotation_packets, finalize_ground_truth


def read_jsonl(path):
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records),
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--instances", type=Path, required=True)
    prepare.add_argument(
        "--quality-gate-report",
        type=Path,
        required=True,
        help="strict four-gate report proving every candidate passed Gate 4",
    )
    prepare.add_argument("--output", type=Path, required=True)
    finalize = sub.add_parser("finalize")
    finalize.add_argument("--packets", type=Path, required=True)
    finalize.add_argument("--annotations", type=Path, required=True)
    finalize.add_argument("--adjudications", type=Path, required=True)
    finalize.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        instances = read_jsonl(args.instances)
        gate_report = json.loads(args.quality_gate_report.read_text(encoding="utf-8"))
        gate4 = gate_report.get("gates", {}).get("gate_4_task_instance_quality", {})
        if gate4.get("passed") is not True:
            raise ValueError("formal annotation packets require a passed Gate 4 report")
        if gate4.get("instance_count") != len(instances):
            raise ValueError("Gate 4 report instance count does not match annotation input")
        records = build_annotation_packets(instances)
        write_jsonl(args.output, records)
        print(json.dumps({"packets": len(records), "output": str(args.output)}))
        return
    result = finalize_ground_truth(
        read_jsonl(args.packets),
        read_jsonl(args.annotations),
        read_jsonl(args.adjudications),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "instances": result["instance_count"],
        "fleiss_kappa": result["fleiss_kappa_exact_label"],
        "output": str(args.output),
    }))


if __name__ == "__main__":
    main()
