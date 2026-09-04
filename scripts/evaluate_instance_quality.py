#!/usr/bin/env python3
"""Evaluate structural quality of rollout-derived SocialFlux instances."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.instance_quality import (
    blind_instance_packet,
    build_instance_quality_report,
)
from evaluation.pipeline_acceptance import load_trajectory_pool
from prompts.loader import render_prompt
from providers.factory import build_provider, public_provider_config
from schemas.validate import validate_instance_quality_judgment


def _jsonl(path):
    if not Path(path).exists():
        return []
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _interventions(pipeline_output):
    records = []
    for path in sorted(Path(pipeline_output).glob("*/validation/local_action_interventions.json")):
        records.extend(json.loads(path.read_text(encoding="utf-8")))
    return records


def _blind_judge(instances, audited, config, limit=None):
    provider = build_provider(config["provider"])
    sampling = config.get("sampling", {})
    grouped = {}
    selected = list(zip(instances, audited))
    if limit is not None:
        selected = selected[:limit]
    for instance, audit in selected:
        raw = provider.complete(
            [{"role": "user", "content": render_prompt(
                "instance_quality_judge_v2",
                blind_instance_packet(instance),
            )}],
            **sampling,
        )
        judgment = json.loads(raw)
        validate_instance_quality_judgment(judgment, instance["task_type"])
        judgment["mean_score"] = round(
            sum(judgment["scores"].values()) / len(judgment["scores"]),
            4,
        )
        audit["blind_semantic_review"] = judgment
        group = audit["source_model_group"]
        task = audit["task_type"]
        grouped.setdefault(group, {}).setdefault(task, []).append(judgment)
    summary = {}
    for model, tasks in grouped.items():
        summary[model] = {}
        for task, judgments in tasks.items():
            summary[model][task] = {
                "count": len(judgments),
                "mean_score": round(
                    sum(item["mean_score"] for item in judgments) / len(judgments),
                    4,
                ),
                "recommendations": {
                    label: sum(item["recommendation"] == label for item in judgments)
                    for label in ("use", "revise", "reject")
                },
            }
    return {
        "prompt_id": "instance_quality_judge_v2",
        "judge_provider": public_provider_config(config["provider"]),
        "sampling": sampling,
        "reviewed_count": len(selected),
        "by_source_model": summary,
        "status": "diagnostic_only_not_human_ground_truth",
    }


def _markdown(report):
    lines = [
        "# SocialFlux Instance Quality Report",
        "",
        f"- Instances: `{report['instance_count']}`",
        f"- Structurally passed: `{report['structurally_passed']}`",
        f"- Mean structural score: `{report['mean_structural_score']}`",
        f"- Trajectories passing repetition/shape checks: `{report['trajectory_quality']['passed']}/{report['trajectory_quality']['trajectory_count']}`",
        "- Semantic quality: `pending blind human or independent-model review`",
        "",
        "## By source model",
        "",
        "| Model group | Task | Count | Passed | Mean structural score |",
        "|---|---:|---:|---:|---:|",
    ]
    for model, tasks in report["by_source_model"].items():
        for task, values in tasks.items():
            lines.append(
                f"| {model} | {task} | {values['count']} | "
                f"{values['passed']} | {values['mean_structural_score']} |"
            )
    lines.extend([
        "",
        "## By scenario",
        "",
        "| Scenario | Task | Count | Passed | Mean structural score |",
        "|---|---:|---:|---:|---:|",
    ])
    for scenario_id, tasks in report["by_scenario"].items():
        for task, values in tasks.items():
            lines.append(
                f"| {scenario_id} | {task} | {values['count']} | "
                f"{values['passed']} | {values['mean_structural_score']} |"
            )
    lines.extend([
        "",
        "## Interpretation boundary",
        "",
        "该分数只覆盖合同、泄漏、证据形状和分支完整性，不把社会合理性、O* 自然度、候选行动的策略意义、人类可回答性或标签有效性伪装成自动结论。模型优劣必须使用匹配配置的 rollout，并做盲化语义评审。",
        "",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline-output", type=Path, default=Path("build/pipeline_v2"))
    parser.add_argument("--scenario-root", type=Path, default=Path("configs/scenarios"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--judge-provider-config", type=Path)
    parser.add_argument("--judge-limit", type=int)
    args = parser.parse_args()
    instances = _jsonl(args.pipeline_output / "instances.jsonl")
    report = build_instance_quality_report(
        instances,
        load_trajectory_pool(args.scenario_root),
        _interventions(args.pipeline_output),
    )
    if args.judge_provider_config:
        judge_config = json.loads(
            args.judge_provider_config.read_text(encoding="utf-8")
        )
        report["blind_semantic_review"] = _blind_judge(
            instances,
            report["instances"],
            judge_config,
            args.judge_limit,
        )
    output = args.output or args.pipeline_output / "instance_quality_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output.with_suffix(".md").write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "instance_count": report["instance_count"],
        "structurally_passed": report["structurally_passed"],
        "mean_structural_score": report["mean_structural_score"],
        "by_source_model": report["by_source_model"],
        "by_scenario": report["by_scenario"],
        "trajectory_quality": report["trajectory_quality"],
        "blind_semantic_review": report.get("blind_semantic_review"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
