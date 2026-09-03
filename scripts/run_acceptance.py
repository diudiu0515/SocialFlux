#!/usr/bin/env python3
"""Build the nine-criterion SocialFlux environment acceptance report."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.pipeline_acceptance import (
    build_acceptance_report,
    load_local_interventions,
    load_scenarios,
    load_trajectory_pool,
)


def markdown(report):
    lines = [
        "# SocialFlux Environment Acceptance v2",
        "",
        "本报告只接受自由模型交互轨迹与真实 checkpoint 局部干预。pending 不等于失败，也不得伪装成已完成人工验收。",
        "",
        "| 验收项 | 状态 | 所需证据 |",
        "|---|---|---|",
    ]
    for item in report["criteria"]:
        lines.append(
            f"| {item['criterion']} | {item['status']} | {item.get('requirement', '')} |"
        )
    lines.extend([
        "",
        "## Gate",
        "",
        f"- Natural trajectories: `{report['trajectory_count']}`",
        f"- Automated artifacts ready: `{str(report['gate']['automated_artifacts_ready']).lower()}`",
        f"- Research acceptance: `{str(report['gate']['research_acceptance']).lower()}`",
        "",
        "已废弃：多轮 repair/neutral/escalation 固定策略敏感性；scenario-authored expected delta matching。",
        "",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", type=Path, default=Path("configs/scenarios"))
    parser.add_argument("--pipeline-output", type=Path, default=Path("build/pipeline_v2"))
    parser.add_argument("--output", type=Path, default=Path("build/acceptance_v2"))
    args = parser.parse_args()
    scenarios = load_scenarios(args.scenarios)
    trajectories = load_trajectory_pool(args.scenarios)
    interventions = load_local_interventions(args.pipeline_output)
    report = build_acceptance_report(scenarios, trajectories, interventions)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "acceptance_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output / "acceptance_report.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output / "acceptance_report.json"),
        "scenario_count": report["scenario_count"],
        "trajectory_count": report["trajectory_count"],
        "criteria": [
            {"criterion": item["criterion"], "status": item["status"]}
            for item in report["criteria"]
        ],
        "gate": report["gate"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
