#!/usr/bin/env python3
"""Plot state trajectories and separate semantic-entry from calibration effects.

This script intentionally uses a small, version-controlled comparison set.  It
does not pool every historical rollout because those artifacts mix incompatible
prompt and runtime revisions.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
V19_ROOT = ROOT / "data/gpt50/experiment/state_v3_validation/state_closed_loop_pilot_v19/gpt"
V32_ROOT = ROOT / "data/gpt50/experiment/state_v3_validation/state_closed_loop_pilot_v32_natural/gpt"
V7_COMPARISON = ROOT / (
    "data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/"
    "reasoning_effort_comparison_results.json"
)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_state(state: dict) -> dict[str, float]:
    return {
        f"{family}.{variable}": float(value)
        for family, values in state.items()
        if isinstance(values, dict)
        for variable, value in values.items()
        if isinstance(value, (int, float))
    }


def canonical_rollouts() -> list[tuple[str, Path]]:
    paths: list[tuple[str, Path]] = []
    for scenario in ("003", "010", "017", "018", "026", "028"):
        candidates = [
            path
            for path in (V19_ROOT / f"scenario_{scenario}").glob("*.json")
            if isinstance(load(path).get("turns"), list)
            and load(path).get("turns")
        ]
        if len(candidates) != 1:
            raise RuntimeError(f"expected one canonical v19 rollout for {scenario}: {candidates}")
        paths.append((f"v19/{scenario}", candidates[0]))
    candidates = [
        path
        for path in (V32_ROOT / "scenario_003").glob("*.json")
        if isinstance(load(path).get("turns"), list)
        and load(path).get("turns")
    ]
    if len(candidates) != 1:
        raise RuntimeError(f"expected one canonical v32 rollout for 003: {candidates}")
    paths.append(("v32/003", candidates[0]))
    return paths


def analyze_rollout(label: str, path: Path) -> dict:
    trajectory = load(path)
    states = [trajectory["initial_state"]] + [turn["state_after"] for turn in trajectory["turns"]]
    initial = flatten_state(states[0])
    flattened = [flatten_state(state) for state in states]
    displacement = [
        sum(abs(values[key] - initial[key]) for key in initial) / len(initial)
        for values in flattened
    ]
    changed_per_turn = []
    candidate_count = 0
    selected_count = 0
    decisive_count = 0
    suppression_reasons: Counter[str] = Counter()
    family_changed: Counter[str] = Counter()
    for turn in trajectory["turns"]:
        numeric = turn.get("numeric_state_delta") or {}
        changed = 0
        for family, values in numeric.items():
            if not isinstance(values, dict):
                continue
            family_count = sum(float(value or 0) != 0 for value in values.values())
            family_changed[family] += family_count
            changed += family_count
        changed_per_turn.append(changed)
        impacts = (turn.get("calibration") or {}).get("state_impacts") or []
        candidate_count += len(impacts)
        for impact in impacts:
            decisive_count += bool(impact.get("decisive_evidence"))
            if impact.get("selected"):
                selected_count += 1
            else:
                suppression_reasons[impact.get("suppressed_by") or "unspecified"] += 1
    ranges = {
        key: max(state[key] for state in flattened) - min(state[key] for state in flattened)
        for key in initial
    }
    return {
        "label": label,
        "path": str(path.relative_to(ROOT)),
        "scenario_id": trajectory.get("scenario_id"),
        "turn_count": len(trajectory["turns"]),
        "state_changed_turn_count": sum(value > 0 for value in changed_per_turn),
        "changed_variable_count": sum(changed_per_turn),
        "changed_variables_per_turn": sum(changed_per_turn) / len(changed_per_turn),
        "candidate_count": candidate_count,
        "selected_count": selected_count,
        "decisive_candidate_count": decisive_count,
        "candidate_to_update_rate": selected_count / candidate_count if candidate_count else None,
        "variables_with_nonzero_range": sum(value > 0 for value in ranges.values()),
        "mean_variable_range": sum(ranges.values()) / len(ranges),
        "state_ranges": ranges,
        "mean_absolute_displacement_from_initial": displacement,
        "changed_variables_by_turn": changed_per_turn,
        "changed_variables_by_family": dict(family_changed),
        "suppression_reasons": dict(suppression_reasons),
    }


def make_plot(records: list[dict], v7_summary: dict, output: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(15, 10), constrained_layout=True)

    ax = axes[0, 0]
    for record in records:
        values = record["mean_absolute_displacement_from_initial"]
        ax.plot(range(len(values)), values, marker="o", markersize=3, linewidth=1.6, label=record["label"])
    ax.set_title("Full rollouts: mean |state - initial state|")
    ax.set_xlabel("Turn (0 = initial)")
    ax.set_ylabel("Mean absolute displacement")
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.25)
    ax.legend(ncol=2, fontsize=8)

    ax = axes[0, 1]
    width = max(record["turn_count"] for record in records)
    heat = np.full((len(records), width), np.nan)
    for row, record in enumerate(records):
        values = record["changed_variables_by_turn"]
        heat[row, : len(values)] = values
    image = ax.imshow(heat, aspect="auto", cmap="Blues", vmin=0, vmax=max(3, np.nanmax(heat)))
    ax.set_title("Changed state variables per turn")
    ax.set_xlabel("Turn")
    ax.set_yticks(range(len(records)), [record["label"] for record in records])
    ax.set_xticks(range(0, width, 2), range(1, width + 1, 2))
    fig.colorbar(image, ax=ax, label="Changed variables")

    ax = axes[1, 0]
    efforts = ["low", "medium"]
    metrics = [
        ("Recognition", "variable_recognition"),
        ("Exact judgment", "exact_four_way"),
        ("Strength", "strength"),
        ("Costly honesty", "costly_honesty_decisive"),
        ("Same-topic new", "same_topic_new_recognized"),
    ]
    x = np.arange(len(metrics))
    bar_width = 0.36
    for offset, effort in enumerate(efforts):
        summary = v7_summary[effort]
        values = []
        for _, key in metrics:
            denominator = (
                summary["costly_honesty_total"]
                if key == "costly_honesty_decisive"
                else summary["same_topic_new_total"]
                if key == "same_topic_new_recognized"
                else summary["complete_calls"]
            )
            values.append(100 * summary[key] / denominator)
        ax.bar(x + (offset - 0.5) * bar_width, values, bar_width, label=effort)
    ax.set_title("v7 semantic entry: Astra reasoning comparison")
    ax.set_ylabel("Correct (%)")
    ax.set_ylim(0, 105)
    ax.set_xticks(x, [label for label, _ in metrics], rotation=18, ha="right")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)

    suppression = Counter()
    for record in records:
        suppression.update(record["suppression_reasons"])
    top = suppression.most_common(7)
    ax = axes[1, 1]
    labels = [key for key, _ in reversed(top)]
    values = [value for _, value in reversed(top)]
    ax.barh(labels, values, color="#d7895b")
    ax.set_title("Full-rollout candidates not selected")
    ax.set_xlabel("Count across 7 rollouts")
    ax.grid(axis="x", alpha=0.25)

    fig.suptitle(
        "State diagnostics: full-rollout movement vs. v7 semantic recognition",
        fontsize=15,
    )
    fig.savefig(output, dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "reports/experiments/state_diagnostics_2026-10-05",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    records = [analyze_rollout(label, path) for label, path in canonical_rollouts()]
    comparison = load(V7_COMPARISON)
    v7_summary = comparison["summary"]["by_effort"]
    aggregate_suppression = Counter()
    for record in records:
        aggregate_suppression.update(record["suppression_reasons"])
    aggregate = {
        "trajectory_count": len(records),
        "turn_count": sum(record["turn_count"] for record in records),
        "state_changed_turn_count": sum(record["state_changed_turn_count"] for record in records),
        "changed_variable_count": sum(record["changed_variable_count"] for record in records),
        "candidate_count": sum(record["candidate_count"] for record in records),
        "selected_count": sum(record["selected_count"] for record in records),
        "decisive_candidate_count": sum(record["decisive_candidate_count"] for record in records),
        "suppression_reasons": dict(aggregate_suppression),
    }
    aggregate["state_changed_turn_rate"] = aggregate["state_changed_turn_count"] / aggregate["turn_count"]
    aggregate["changed_variables_per_turn"] = aggregate["changed_variable_count"] / aggregate["turn_count"]
    aggregate["candidate_to_update_rate"] = aggregate["selected_count"] / aggregate["candidate_count"]
    report = {
        "format": "socialflux_state_curve_diagnostics_v1",
        "scope": {
            "full_rollouts": "canonical completed v19 set plus completed v32 natural pilot; shared evidence_independent_hysteretic_v3 profile",
            "v7_fixed_set": str(V7_COMPARISON.relative_to(ROOT)),
            "warning": "No v7 full rollout exists; semantic-entry and full-trajectory evidence are shown separately and must not be treated as one runtime version.",
        },
        "aggregate": aggregate,
        "v7_semantic_summary": v7_summary,
        "rollouts": records,
        "diagnosis": [
            "Historical comparable full rollouts are not globally frozen: state changes occur on more than half of turns.",
            "The v7 fixed-set blocker is upstream semantic recognition, especially costly honesty and same-topic new behavior, not feature or dialogue veto in the calibrator.",
            "Astra medium reasoning did not improve the v7 semantic gate over low reasoning.",
            "A v7 full-trajectory curve cannot be claimed until an alternative appraiser passes the fixed semantic gate and a bounded small rollout is run.",
        ],
    }
    json_path = args.output_dir / "state_diagnostics.json"
    png_path = args.output_dir / "state_diagnostics.png"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    make_plot(records, v7_summary, png_path)
    print(json.dumps({"json": str(json_path), "png": str(png_path), "aggregate": aggregate}, indent=2))


if __name__ == "__main__":
    main()
