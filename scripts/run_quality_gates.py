#!/usr/bin/env python3
"""Run the strict Gate 1 -> Gate 4 audit and emit a blocking report."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.review_registry import load_review_registry
from evaluation.quality_gates import (
    _read_interventions,
    _read_jsonl,
    audit_all_gates,
    load_rollouts,
)
from scripts.run_pipeline import load_scenarios
from scripts.scenario_docs import discover_scenario_paths


def markdown(report):
    lines = [
        "# SocialFlux Four-Gate Quality Report",
        "",
        f"- Research ready: `{str(report['research_ready']).lower()}`",
        f"- Scenarios: `{report['scenario_count']}`",
        f"- Trajectories: `{report['trajectory_count']}`; Gate 3 eligible: `{report['eligible_trajectory_count']}`",
        f"- Task instances: `{report['instance_count']}`",
        "",
        "| Gate | Status |",
        "|---|---|",
    ]
    for gate_name, gate in report["gates"].items():
        lines.append(f"| {gate_name} | `{gate['status']}` |")
    lines.extend(["", "## Deficiencies", ""])
    if report["deficiencies"]:
        for item in report["deficiencies"]:
            lines.append("- " + "; ".join(f"{key}={value}" for key, value in item.items()))
    else:
        lines.append("- none")
    lines.extend(["", "## Boundary", "", report["human_boundary"], ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario-root", type=Path, default=Path("configs/scenarios"))
    parser.add_argument("--raw-root", type=Path)
    parser.add_argument(
        "--rollout-stage",
        choices=("raw", "selected"),
        default="raw",
        help="selected skips raw >=12 and requires 4–6 trajectories per scenario",
    )
    parser.add_argument("--pipeline-output", type=Path, default=Path("build/pipeline_v2"))
    parser.add_argument("--environment-evidence", type=Path)
    parser.add_argument("--judgments", type=Path)
    parser.add_argument("--history-evidence", type=Path)
    parser.add_argument("--human-task-review", type=Path)
    parser.add_argument("--review-registry", type=Path, help="human-signed Gate 1 registry")
    parser.add_argument("--output", type=Path, default=Path("build/quality_gates/report.json"))
    parser.add_argument("--strict", action="store_true", help="exit 1 unless all four gates pass")
    args = parser.parse_args()

    scenarios = load_scenarios(args.scenario_root)
    scenario_paths = {
        json.loads(path.read_text(encoding="utf-8"))["scenario_id"]: path
        for path in discover_scenario_paths(args.scenario_root)
    }
    review_registry = load_review_registry(args.review_registry) if args.review_registry else None
    trajectories = load_rollouts(
        args.raw_root or args.scenario_root,
        require_selected_manifest=args.rollout_stage == "selected",
    )
    instances = _read_jsonl(args.pipeline_output / "instances.jsonl")
    interventions = _read_interventions(args.pipeline_output)
    report = audit_all_gates(
        scenarios,
        trajectories,
        instances,
        interventions,
        args.environment_evidence,
        args.judgments,
        args.history_evidence,
        args.human_task_review,
        scenario_paths,
        review_registry,
        args.rollout_stage,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "research_ready": report["research_ready"],
        "scenario_count": report["scenario_count"],
        "trajectory_count": report["trajectory_count"],
        "eligible_trajectory_count": report["eligible_trajectory_count"],
        "instance_count": report["instance_count"],
        "gate_status": {key: value["status"] for key, value in report["gates"].items()},
    }, ensure_ascii=False, indent=2))
    if args.strict and not report["research_ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
