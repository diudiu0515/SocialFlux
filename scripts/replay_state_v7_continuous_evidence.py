#!/usr/bin/env python3
"""Replay the v7 rule that every valid new state evidence updates immediately."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from environment.calibration import DeterministicStateCalibrator, FEATURE_NAMES


PROFILE = "state_judgment_primary_hysteretic_v7"
DEFAULT_OUTPUT = (
    ROOT / "data/gpt50/experiment/state_v3_validation"
    / "v323_state_judgment_primary/immediate_new_evidence_replay.json"
)


def scenario():
    return {
        "environment_agent": {"persona": {}},
        "selected_state_variables": {"relationship": ["trust"]},
        "initial_state": {"relationship": {"trust": 4}},
        "initialization_notes": {"rationale": {}, "state_transition_plan": {}},
    }


def appraisal(span):
    return {
        "event_features": {name: 0 for name in FEATURE_NAMES},
        "state_impacts": [{
            "variable": "relationship.trust",
            "direction": "increase",
            "evidence_feature": None,
            "evidence_span": span,
            "evidence_strength": 1,
            "directness": "direct",
            "new_evidence": True,
        }],
        "dynamics_impacts": [],
    }


def compact(label, event_id, result):
    diagnostic = result["calibration"]["state_impacts"][0]
    return {
        "label": label,
        "event_id": event_id,
        "final_delta": result["state_delta"]["relationship"]["trust"],
        "selection_reason": diagnostic["selection_reason"],
        "pending_after": diagnostic.get("slow_evidence_pending_after", 0),
        "consumed_ids": diagnostic.get("slow_evidence_consumed_ids", []),
        "replayed_consumed": diagnostic.get(
            "slow_evidence_replayed_consumed", False
        ),
        "pending_history": result["calibration"]["slow_evidence_history"],
        "consumed_history": result["calibration"][
            "slow_evidence_consumed_history"
        ],
        "full_calibration_diagnostic": diagnostic,
    }


def build_replay():
    continuous = DeterministicStateCalibrator(scenario(), profile=PROFILE)
    first = continuous.calibrate(
        appraisal("第一条普通且独立的可靠行为"),
        {"relationship": {"trust": 4}}, {}, current_event_id="e1",
    )
    second = continuous.calibrate(
        appraisal("第二条普通且独立的同向可靠行为"),
        {"relationship": {"trust": 5}}, {}, current_event_id="e2",
    )
    replay = continuous.calibrate(
        appraisal("第二条普通且独立的同向可靠行为"),
        {"relationship": {"trust": 6}}, {}, current_event_id="e2",
    )

    empty_accumulator = DeterministicStateCalibrator(scenario(), profile=PROFILE)
    isolated = empty_accumulator.calibrate(
        appraisal("第二条普通且独立的同向可靠行为"),
        {"relationship": {"trust": 4}}, {}, current_event_id="e2",
    )

    steps = [
        compact("full_history_first_ordinary_triggers", "e1", first),
        compact("full_history_second_independent_also_triggers", "e2", second),
        compact("full_history_consumed_event_replay_blocked", "e2", replay),
    ]
    isolated_step = compact(
        "empty_accumulator_single_new_evidence_triggers", "e2", isolated
    )
    checks = {
        "first_new_ordinary_event_triggers": (
            steps[0]["final_delta"] == "mild_increase"
            and steps[0]["consumed_ids"] == ["e1"]
            and steps[0]["pending_after"] == 0
        ),
        "second_new_ordinary_event_also_triggers": (
            steps[1]["final_delta"] == "mild_increase"
            and steps[1]["consumed_ids"] == ["e2"]
            and steps[1]["pending_after"] == 0
        ),
        "consumed_event_cannot_trigger_again": (
            steps[2]["final_delta"] == "similar"
            and steps[2]["replayed_consumed"] is True
            and not steps[2]["pending_history"]
        ),
        "empty_accumulator_does_not_block_new_evidence": (
            isolated_step["final_delta"] == "mild_increase"
            and isolated_step["consumed_ids"] == ["e2"]
            and isolated_step["pending_after"] == 0
        ),
    }
    return {
        "format": "socialflux_state_v7_immediate_new_evidence_replay_v2",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_calls": 0,
        "profile": PROFILE,
        "rule": (
            "valid ordinary and decisive new evidence both update immediately; "
            "strength changes magnitude only"
        ),
        "preserved_rules": [
            "numeric_bounds", "direction_mapping", "duplicate_event_blocking",
        ],
        "full_history_accumulation": steps,
        "empty_accumulator_single_turn": isolated_step,
        "checks": checks,
        "passed": all(checks.values()),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    result = build_replay()
    if not result["passed"]:
        raise AssertionError(json.dumps(result["checks"], ensure_ascii=False))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "checks": result["checks"],
        "passed": result["passed"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
