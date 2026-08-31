#!/usr/bin/env python3
"""Run the five-criterion pipeline acceptance report."""

import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.pipeline_acceptance import build_acceptance_report, load_scenarios


def markdown(report):
    lines = [
        "# SocialFlux Pipeline Acceptance",
        "",
        "本报告由 scripts/run_acceptance.py 生成。自动通过不等于替代人工语义验收。",
        "",
        "| 验收项 | 状态 | 结果 |",
        "|---|---|---|",
    ]
    for item in report["criteria"]:
        if "passed_checks" in item:
            result = "{}/{} checks".format(item["passed_checks"], item["check_count"])
        elif "passed_scenarios" in item:
            result = "{}/{} scenarios".format(item["passed_scenarios"], item["scenario_count"])
        elif "structurally_valid_scenarios" in item:
            result = "{}/{} scenarios structurally valid".format(
                item["structurally_valid_scenarios"], item["scenario_count"]
            )
        else:
            result = "see JSON details"
        lines.append("| {} | {} | {} |".format(item["criterion"], item["status"], result))
        lines.append("")
        lines.append(item.get("interpretation", ""))
        if item.get("reason"):
            lines.append("")
            lines.append("原因：" + item["reason"])
        if item.get("required_fix"):
            lines.append("")
            lines.append("后续：" + item["required_fix"])
        lines.append("")
    human_pending = report["gate"].get("formal_human_pending", [])
    lines.extend([
        "## Gate",
        "",
        "- Automated engineering checks: " + ("passed" if report["gate"]["automated_passed"] else "failed"),
        "- Research acceptance: " + ("passed" if report["gate"]["research_acceptance"] else "pending formal human review"),
        "- Formal human review pending: " + (", ".join(human_pending) if human_pending else "none"),
        "",
        "完整逐项 evidence 保存在同目录的 acceptance_report.json。",
    ])
    return chr(10).join(lines) + chr(10)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", type=Path, default=Path("configs/scenarios"))
    parser.add_argument("--output", type=Path, default=Path("build/pipeline_v1"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = build_acceptance_report(load_scenarios(args.scenarios))
    (args.output / "acceptance_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + chr(10),
        encoding="utf-8",
    )
    (args.output / "acceptance_report.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output / "acceptance_report.json"),
        "scenario_count": report["scenario_count"],
        "criteria": [
            {"criterion": item["criterion"], "status": item["status"]}
            for item in report["criteria"]
        ],
        "gate": report["gate"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
