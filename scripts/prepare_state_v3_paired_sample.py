#!/usr/bin/env python3
"""Pre-register a risk-stratified State v3 paired-rollout sample."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FAMILIES = (
    "emotion",
    "behavioral_disposition",
    "relationship",
    "consequence_risk",
)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stable_key(seed, scenario_id):
    return hashlib.sha256(f"{seed}:{scenario_id}".encode()).hexdigest()


def flatten_directions(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for child in value.values() for item in flatten_directions(child)]
    if isinstance(value, list):
        return [item for child in value for item in flatten_directions(child)]
    return []


def select_sample(accepted, e1_items, e9_items, *, seed):
    accepted_ids = set(accepted)
    e9 = {}
    for item in e9_items:
        scenario_id = item.get("scenario_id")
        if scenario_id not in accepted_ids or item.get("changed_turn_count") != 0:
            continue
        record = e9.setdefault(scenario_id, {"families": set(), "zero_count": 0})
        record["families"].add(item.get("state_family"))
        record["zero_count"] += 1

    e9_selected = []
    uncovered = set(FAMILIES)
    while len(e9_selected) < 4:
        candidates = [
            scenario_id for scenario_id in e9
            if scenario_id not in e9_selected
        ]
        if not candidates:
            break
        candidates.sort(key=lambda scenario_id: (
            -len(e9[scenario_id]["families"] & uncovered),
            -e9[scenario_id]["zero_count"],
            stable_key(seed + ":e9", scenario_id),
        ))
        chosen = candidates[0]
        e9_selected.append(chosen)
        uncovered -= e9[chosen]["families"]

    e1_scores = {}
    for item in e1_items:
        scenario_id = item.get("scenario_id")
        if scenario_id not in accepted_ids or scenario_id in e9_selected:
            continue
        directions = flatten_directions(
            item.get("machine_directions_after_vote") or {}
        )
        similar = sum(value == "similar" for value in directions)
        e1_scores[scenario_id] = max(e1_scores.get(scenario_id, 0), similar)
    e1_selected = sorted(
        e1_scores,
        key=lambda scenario_id: (
            -e1_scores[scenario_id],
            stable_key(seed + ":e1", scenario_id),
        ),
    )[:4]

    risk = e9_selected + e1_selected
    remaining = sorted(
        accepted_ids - set(risk),
        key=lambda scenario_id: stable_key(seed + ":control", scenario_id),
    )
    controls = remaining[:8]
    selected = risk + controls
    if len(e9_selected) != 4 or len(e1_selected) != 4 or len(controls) != 8:
        raise ValueError("could not construct the fixed 4+4+8 paired sample")
    if len(selected) != len(set(selected)):
        raise ValueError("paired sample contains duplicate scenarios")
    return {
        "e9_zero_change_risk": e9_selected,
        "e1_unchanged_direction_risk": e1_selected,
        "stable_hash_controls": controls,
        "selected": selected,
        "e9_risk_details": {
            scenario_id: {
                "zero_change_review_item_count": e9[scenario_id]["zero_count"],
                "state_families": sorted(e9[scenario_id]["families"]),
            }
            for scenario_id in e9_selected
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--accepted-root", type=Path,
        default=ROOT / "data/gpt50/experiment/gate2/accepted_rollout_inputs",
    )
    parser.add_argument(
        "--e1", type=Path,
        default=ROOT / "data/gpt50/experiment/gate2/state_transition_agreement.json",
    )
    parser.add_argument(
        "--e9", type=Path,
        default=ROOT / "data/gpt50/experiment/gate2/timescale_validity.json",
    )
    parser.add_argument(
        "--output", type=Path,
        default=(
            ROOT / "data/gpt50/experiment/state_v3_validation/"
            "paired_sample_manifest.json"
        ),
    )
    parser.add_argument("--seed", default="state-v3-paired-sample-v1")
    args = parser.parse_args(argv)

    trajectories = {}
    for path in sorted(args.accepted_root.glob("scenario_*/trajectory.json")):
        trajectory = load(path)
        trajectories[trajectory["scenario_id"]] = {
            "trajectory_id": trajectory["trajectory_id"],
            "source_turn_count": len(trajectory.get("turns", [])),
            "source_path": str(path.resolve()),
            "source_sha256": sha256_file(path),
        }
    if len(trajectories) != 31:
        raise ValueError(f"expected 31 accepted trajectories, found {len(trajectories)}")
    selection = select_sample(
        trajectories,
        load(args.e1).get("review_items", []),
        load(args.e9).get("review_items", []),
        seed=args.seed,
    )
    payload = {
        "format": "socialflux_state_v3_paired_sample_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "pre_registered_before_state_v3_paired_outcomes",
        "seed": args.seed,
        "source_population": {
            "status_filter": "accepted",
            "count": len(trajectories),
            "e1_file": str(args.e1.resolve()),
            "e1_sha256": sha256_file(args.e1),
            "e9_file": str(args.e9.resolve()),
            "e9_sha256": sha256_file(args.e9),
        },
        "selection_policy": {
            "risk_count": 8,
            "control_count": 8,
            "e9": (
                "four stable-hash-tiebroken scenarios with zero-change review "
                "items, greedily covering the four state families"
            ),
            "e1": (
                "four non-overlapping stable-hash-tiebroken scenarios with the "
                "largest sampled all-similar direction count"
            ),
            "control": "eight stable-hash controls from the remaining accepted pool",
            "independent_of_state_v3_paired_outcomes": True,
        },
        **selection,
        "source_trajectories": {
            scenario_id: trajectories[scenario_id]
            for scenario_id in selection["selected"]
        },
        "required_real_rollout_turns": 20,
        "human_review": "pending",
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
        "risk": selection["selected"][:8],
        "controls": selection["stable_hash_controls"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
