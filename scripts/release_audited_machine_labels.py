#!/usr/bin/env python3
"""Release complete machine task proposals after the human Gate 4 audit passes."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from annotation.audited_machine_gt import release_audited_machine_labels


def read_jsonl(path):
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instances", type=Path, required=True)
    parser.add_argument("--machine-proposals", type=Path, required=True)
    parser.add_argument("--four-gate-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = release_audited_machine_labels(
        read_jsonl(args.instances),
        json.loads(args.machine_proposals.read_text(encoding="utf-8")),
        json.loads(args.four_gate_report.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "instances": result["instance_count"],
        "gate4_sample_size": result["gate4_sample_size"],
        "output": str(args.output),
    }))


if __name__ == "__main__":
    main()
