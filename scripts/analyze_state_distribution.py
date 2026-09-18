#!/usr/bin/env python3
"""Report R4 state-distribution diagnostics, optionally against a baseline."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.state_distribution import (
    compare_state_distributions,
    summarize_state_distribution,
)
from scripts.audit_formal_rollout_pool import load_records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--baseline-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    after = summarize_state_distribution(load_records(args.raw_root))
    payload = after
    if args.baseline_root:
        before = summarize_state_distribution(load_records(args.baseline_root))
        payload = compare_state_distributions(before, after)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
