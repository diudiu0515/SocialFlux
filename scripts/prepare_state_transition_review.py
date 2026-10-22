#!/usr/bin/env python3
"""Prepare a human-only review packet for state ontology and transitions."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from environment.state_ontology import build_state_semantics


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUTS = (
    ROOT / "data/gpt50/experiment/gate2/accepted_rollout_inputs"
)
DEFAULT_SCENARIOS = (
    ROOT / "data/gpt50/experiment/scenario/scenarios"
)
DEFAULT_OUTPUT = (
    ROOT
    / "data/gpt50/experiment/gate2/human_review"
    / "state_transition_ontology.json"
)


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _flatten(values):
    return {
        f"{family}.{variable}": value
        for family, variables in (values or {}).items()
        for variable, value in variables.items()
    }


def _scenario_paths(root):
    return {
        value["scenario_id"]: (path, value)
        for path in sorted(Path(root).glob("scenario_*/scenario_*.json"))
        for value in [_load(path)]
    }


def _trajectory_paths(root):
    return {
        value["scenario_id"]: (path, value)
        for path in sorted(Path(root).glob("scenario_*/trajectory.json"))
        for value in [_load(path)]
    }


def _blank_human_review():
    return {
        "review_status": "pending",
        "reviewer": "",
        "reviewed_at_utc": "",
        "human_attestation": False,
        "ratings": {
            "construct_relevance": None,
            "definition_unambiguity": None,
            "increase_anchor_validity": None,
            "decrease_anchor_validity": None,
            "non_evidence_boundary_validity": None,
            "timescale_validity": None,
            "initial_value_validity": None,
        },
        "decision": None,
        "required_revision": "",
        "notes": "",
    }


def _variable_observations(trajectory, path):
    counts = {
        "labels": 0,
        "appraised_candidates": 0,
        "calibrated_positive": 0,
        "selected": 0,
        "applied": 0,
        "selected_boundary_noop": 0,
    }
    examples = []
    for turn in trajectory.get("turns", []):
        before = _flatten(turn.get("state_before", {}))
        numeric = _flatten(turn.get("numeric_state_delta", {}))
        counts["labels"] += 1
        if numeric.get(path, 0):
            counts["applied"] += 1
        for item in (
            (turn.get("calibration") or {}).get("state_impacts") or []
        ):
            if item.get("variable") != path:
                continue
            counts["appraised_candidates"] += 1
            if item.get("calibrated_level", 0) > 0:
                counts["calibrated_positive"] += 1
            if item.get("selected"):
                counts["selected"] += 1
                current = before.get(path)
                if (
                    not numeric.get(path, 0)
                    and (
                        (
                            item.get("direction") == "increase"
                            and current == 10
                        )
                        or (
                            item.get("direction") == "decrease"
                            and current == 0
                        )
                    )
                ):
                    counts["selected_boundary_noop"] += 1
            if len(examples) < 3:
                examples.append(
                    {
                        "turn_id": turn.get("turn_id"),
                        "latest_action": (
                            turn.get("policy_action") or {}
                        ).get("text", ""),
                        "state_before": before.get(path),
                        "candidate_direction": item.get("direction"),
                        "evidence_strength": item.get(
                            "evidence_strength"
                        ),
                        "directness": item.get("directness"),
                        "evidence_feature": item.get(
                            "evidence_feature"
                        ),
                        "feature_inferred": item.get(
                            "feature_inferred"
                        ),
                        "calibrated_level": item.get(
                            "calibrated_level"
                        ),
                        "selected": item.get("selected"),
                        "applied_numeric_delta": numeric.get(path, 0),
                    }
                )
    return {"counts": counts, "candidate_examples": examples}


def build_packet(input_root, scenario_root):
    manifest = _load(Path(input_root) / "gate2_input_manifest.json")
    scenarios = _scenario_paths(scenario_root)
    trajectories = _trajectory_paths(input_root)
    records = []
    for source in manifest.get("records", []):
        scenario_id = source["scenario_id"]
        scenario_path, scenario = scenarios[scenario_id]
        trajectory_path, trajectory = trajectories[scenario_id]
        semantics = build_state_semantics(scenario)
        initial = _flatten(scenario.get("initial_state", {}))
        variables = []
        for path, specification in semantics["variables"].items():
            variables.append(
                {
                    "state_path": path,
                    "initial_value": initial[path],
                    "operational_semantics": specification,
                    "observed_old_v11_sparse_v1": (
                        _variable_observations(trajectory, path)
                    ),
                    "human_review": _blank_human_review(),
                }
            )
        records.append(
            {
                "scenario_id": scenario_id,
                "trajectory_id": trajectory["trajectory_id"],
                "source_status": source.get("source_status"),
                "scenario_path": str(scenario_path),
                "trajectory_path": str(trajectory_path),
                "title": scenario.get("title", ""),
                "background": scenario.get("background", ""),
                "turn_count": len(trajectory.get("turns", [])),
                "state_contract_version": scenario.get(
                    "state_contract_version"
                ),
                "variables": variables,
                "scenario_review": _blank_human_review(),
            }
        )
    return {
        "format": "socialflux_state_transition_human_review_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "review_status": "pending_human",
        "human_attestation": False,
        "reviewers": [],
        "model_calls": 0,
        "cohort": {
            "source_status_filter": manifest.get("source_status_filter"),
            "scenario_count": len(records),
            "variable_count": sum(
                len(record["variables"]) for record in records
            ),
            "exact_20_turn_count": manifest.get("exact_20_turn_count"),
        },
        "instructions": {
            "independence": (
                "A human reviewer must judge the ontology before looking at "
                "aggregate Gate outcomes. Model output cannot sign this packet."
            ),
            "decision_values": ["keep", "revise", "remove"],
            "rating_scale": "1-5; all fields required before attestation",
            "transition_rule": (
                "Do not reward frequent change. Check whether each recorded "
                "change or non-change follows variable-specific evidence and "
                "the declared timescale."
            ),
            "rollout_boundary": (
                "The attached observations are from old v11/sparse_v1 "
                "trajectories and are diagnostic only, not post-fix evidence."
            ),
        },
        "records": records,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument(
        "--scenarios", type=Path, default=DEFAULT_SCENARIOS
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    packet = build_packet(args.inputs, args.scenarios)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
