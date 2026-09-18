#!/usr/bin/env python3
"""Create unsigned, hash-bound Gate 1 records for all Scale300 scenarios."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "configs" / "scale300_v1" / "scenarios"
OUTPUT = ROOT / "reviews" / "scale300_scenario_review_template.json"


def main():
    records = []
    for ordinal in range(1, 301):
        path = SCENARIOS / f"scenario_{ordinal:03d}" / f"scenario_{ordinal:03d}.json"
        scenario = json.loads(path.read_text(encoding="utf-8"))
        notes = scenario.get("initialization_notes", {}).get("rationale", {})
        records.append({
            "scenario_id": scenario["scenario_id"],
            "reviewer": "",
            "reviewed_at_utc": "",
            "scenario_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "decision": "pending",
            "human_attestation": False,
            "attestations": {
                "variables_relevant": False,
                "values_justified": False,
                "no_policy_effect_baked_in": False,
                "initial_triggers_inactive": False,
                "multiple_future_paths_possible": False,
                "shared_across_models_and_seeds": False,
            },
            "quality_scores": {
                "social_plausibility": None,
                "character_coherence": None,
                "tradeoff_quality": None,
                "history_necessity": None,
                "interaction_richness": None,
                "t1_t4_suitability": None,
            },
            "s0_notes": notes,
            "d0_notes": scenario.get("initial_dynamics", {}),
            "trigger_notes": scenario.get("initialization_notes", {}).get(
                "trigger_reachability", []
            ),
        })
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({
        "format": "socialflux_scenario_review_registry_v1",
        "instructions": (
            "Unsigned Scale300 Gate 1 template. Machine checks cannot set "
            "human_attestation or approve a scenario."
        ),
        "records": records,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"records": len(records), "output": str(OUTPUT)}))


if __name__ == "__main__":
    main()
