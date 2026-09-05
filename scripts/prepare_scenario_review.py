#!/usr/bin/env python3
"""Create a complete 20-scenario human review worksheet without signing it."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.review_registry import (
    REQUIRED_ATTESTATIONS,
    REQUIRED_QUALITY_SCORES,
    file_sha256,
)
from scripts.scenario_docs import discover_scenario_paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", type=Path, default=Path("configs/scenarios"))
    parser.add_argument("--output", type=Path, default=Path("reviews/scenario_review_template.json"))
    args = parser.parse_args()
    records = []
    for path in discover_scenario_paths(args.scenarios):
        scenario = json.loads(path.read_text(encoding="utf-8"))
        records.append({
            "scenario_id": scenario["scenario_id"],
            "reviewer": "",
            "reviewed_at_utc": "",
            "scenario_sha256": file_sha256(path),
            "decision": "pending",
            "human_attestation": False,
            "attestations": {key: False for key in REQUIRED_ATTESTATIONS},
            "quality_scores": {key: None for key in REQUIRED_QUALITY_SCORES},
            "s0_notes": scenario.get("initialization_notes", {}).get("rationale", {}),
            "d0_notes": scenario.get("initial_dynamics", {}),
            "trigger_notes": scenario.get("initialization_notes", {}).get(
                "trigger_reachability", []
            ),
        })
    payload = {
        "format": "socialflux_scenario_review_registry_v1",
        "instructions": (
            "A real reviewer must inspect every scenario, update JSON quality/status, "
            "regenerate scenario docs, then refresh hashes and sign each record."
        ),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"review_packets": len(records), "output": str(args.output)}))


if __name__ == "__main__":
    main()
