#!/usr/bin/env python3
"""Replay frozen independent appraisals through state-judgment-primary v7."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from environment.calibration import DeterministicStateCalibrator


DEFAULT_INPUT = (
    ROOT / "data/gpt50/experiment/state_v3_validation"
    / "v3227_independent_per_variable/fixed_set_correction_results.json"
)
DEFAULT_OUTPUT = (
    ROOT / "data/gpt50/experiment/state_v3_validation"
    / "v323_state_judgment_primary/deterministic_replay.json"
)
PROFILE = "state_judgment_primary_hysteretic_v7"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def delta_for(result, target):
    family, variable = target.split(".", 1)
    return result["state_delta"][family][variable]


def target_diagnostic(result, target):
    return next(
        (item for item in result["calibration"]["state_impacts"]
        if item["variable"] == target
        ), None,
    )

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    frozen = load(args.input)
    rows = []
    for row in frozen["fixed_set"]:
        case = row["case"]
        saved = row["independent"]
        transition = saved["transition"]
        scenario = load(ROOT / case["scenario"])
        source = load(ROOT / case["source"])
        turn = next(
            item for item in source["turns"]
            if item["turn_id"] == case["turn_id"]
        )
        result = DeterministicStateCalibrator(
            scenario, profile=PROFILE
        ).calibrate(
            transition["appraisal"],
            turn["state_before"],
            turn["dynamics_before"],
            surface_duplicate_evidence_ids=(
                turn.get("memory_view") or {}
            ).get("deterministic_surface_duplicate_ids", []),
            current_event_id=case["turn_id"],
        )
        judgment = next(
            item for item in transition.get("state_judgments", [])
            if item["variable"] == case["target"]
        )
        final_delta = delta_for(result, case["target"])
        update_expected = case["requires_nonzero_final_update"]
        update_correct = (
            final_delta != "similar" if update_expected
            else final_delta == "similar"
        )
        rows.append({
            "case_id": case["case_id"],
            "target": case["target"],
            "human_confirmation": case.get("human_confirmation", "pending"),
            "expected_judgment": case["expected_judgment"],
            "observed_judgment": judgment["judgment"],
            "judgment_match": (
                judgment["judgment"] == case["expected_judgment"]
            ),
            "feature_interface_validation": judgment.get(
                "feature_interface_validation"
            ),
            "v6_final_delta": (
                saved["evaluation"]["final_delta"]
            ),
            "v7_final_delta": final_delta,
            "final_update_correct": update_correct,
            "v7_target_diagnostic": target_diagnostic(result, case["target"]),
        })
    matched = [item for item in rows if item["judgment_match"]]
    payload = {
        "format": "socialflux_state_judgment_primary_replay_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(args.input.resolve().relative_to(ROOT)),
        "calibration_profile": PROFILE,
        "model_calls": 0,
        "label_status": (
            "pre_registered_expected_labels; human_confirmation_pending"
        ),
        "summary": {
            "case_count": len(rows),
            "state_judgment_match": sum(
                item["judgment_match"] for item in rows
            ),
            "final_update_correct": sum(
                item["final_update_correct"] for item in rows
            ),
            "matched_judgment_case_count": len(matched),
            "matched_judgment_final_update_correct": sum(
                item["final_update_correct"] for item in matched
            ),
        },
        "scale_decision": {
            "approved": False,
            "reason": (
                "Frozen Astra state judgments match only "
                f"{sum(item['judgment_match'] for item in rows)}/{len(rows)} "
                "pre-registered labels; calibration cannot repair missing or "
                "mis-strengthened variable evidence. Human labels remain pending."
            ),
        },
        "cases": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(json.dumps({
        "output": str(args.output),
        **payload["summary"],
        "scale_approved": payload["scale_decision"]["approved"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
