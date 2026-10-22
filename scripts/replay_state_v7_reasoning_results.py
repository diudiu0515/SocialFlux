#!/usr/bin/env python3
"""Replay saved Astra reasoning-comparison appraisals through current v7.

No provider calls are made.  Each observation starts with a fresh calibrator,
matching the pre-registered fixed-set comparison.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from environment.calibration import DeterministicStateCalibrator


PROFILE = "state_judgment_primary_hysteretic_v7"
DEFAULT_INPUT = (
    ROOT / "data/gpt50/experiment/state_v3_validation"
    / "v323_state_judgment_primary/reasoning_effort_comparison_results.json"
)
DEFAULT_OUTPUT = (
    ROOT / "data/gpt50/experiment/state_v3_validation"
    / "v323_state_judgment_primary/immediate_update_reasoning_replay.json"
)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def target_delta(result: dict, target: str) -> str:
    family, variable = target.split(".", 1)
    return result["state_delta"][family][variable]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    source = load(args.input)
    rows = []
    for observation in source["observations"]:
        case = observation["case"]
        saved_result = observation["result"]
        if saved_result.get("status") != "completed":
            rows.append({
                "observation_id": observation["observation_id"],
                "status": saved_result.get("status"),
            })
            continue
        scenario = load(ROOT / case["scenario"])
        trajectory = load(ROOT / case["source"])
        source_turn = next(
            turn for turn in trajectory["turns"]
            if turn["turn_id"] == case["turn_id"]
        )
        replay = DeterministicStateCalibrator(
            scenario, profile=PROFILE
        ).calibrate(
            saved_result["state_appraisal"]["appraisal"],
            case["pre_update_state"],
            source_turn["dynamics_before"],
            surface_duplicate_evidence_ids=(
                source_turn.get("memory_view") or {}
            ).get("deterministic_surface_duplicate_ids", []),
            current_event_id=case["turn_id"],
        )
        target = case["target"]
        diagnostic = next(
            (
                item for item in replay["calibration"]["state_impacts"]
                if item["variable"] == target
            ),
            None,
        )
        final_delta = target_delta(replay, target)
        recognized = saved_result["evaluation"]["variable_recognition_pass"]
        selected_count = sum(
            item.get("selected", False)
            for item in replay["calibration"]["state_impacts"]
        )
        rows.append({
            "observation_id": observation["observation_id"],
            "case_id": observation["case_id"],
            "reasoning_effort": observation["reasoning_effort"],
            "repeat": observation["repeat"],
            "status": "completed",
            "target": target,
            "human_judgment": saved_result["evaluation"]["human_judgment"],
            "observed_judgment": saved_result["evaluation"]["observed_judgment"],
            "target_recognized": recognized,
            "old_final_delta": saved_result["evaluation"]["final_delta"],
            "new_final_delta": final_delta,
            "recognized_and_updated": recognized and final_delta != "similar",
            "state_candidate_count": len(
                replay["calibration"]["state_impacts"]
            ),
            "selected_state_candidate_count": selected_count,
            "target_diagnostic": diagnostic,
        })

    summary = {}
    for effort in ("low", "medium"):
        subset = [
            row for row in rows
            if row.get("status") == "completed"
            and row.get("reasoning_effort") == effort
        ]
        recognized = [row for row in subset if row["target_recognized"]]
        target_suppressions = Counter(
            (row["target_diagnostic"] or {}).get("selection_reason", "not_emitted")
            for row in subset
            if row["new_final_delta"] == "similar"
        )
        summary[effort] = {
            "observations": len(subset),
            "target_recognized": len(recognized),
            "target_updated": sum(
                row["new_final_delta"] != "similar" for row in subset
            ),
            "recognized_target_updated": sum(
                row["recognized_and_updated"] for row in subset
            ),
            "mean_state_candidates_per_observation": (
                sum(row["state_candidate_count"] for row in subset) / len(subset)
            ),
            "mean_selected_state_candidates_per_observation": (
                sum(row["selected_state_candidate_count"] for row in subset)
                / len(subset)
            ),
            "target_no_update_reasons": dict(target_suppressions),
        }

    payload = {
        "format": "socialflux_state_v7_immediate_update_reasoning_replay_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(args.input.relative_to(ROOT)),
        "calibration_profile": PROFILE,
        "model_calls": 0,
        "summary": summary,
        "interpretation": [
            "This replay measures calibration behavior on frozen semantic outputs.",
            "It cannot repair a target variable that the appraiser did not recognize.",
            "All human-confirmed fixed-set targets are positive; precision still requires confirmed irrelevant and repeated-evidence controls.",
        ],
        "observations": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "model_calls": 0,
        "summary": summary,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
