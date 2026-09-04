#!/usr/bin/env python3
"""Audit every canonical scenario for rollout plus T1/T2/T3 review completeness."""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.scenario_docs import discover_scenario_paths

REQUIRED_TASKS = (
    "T1_state_tracking",
    "T2_history_sensitive_merge",
    "T3_counterfactual_choice_effect",
)


def _json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def audit_scenario_bundle(scenario_path, pipeline_root):
    scenario_path = Path(scenario_path)
    scenario = _json(scenario_path, {})
    scenario_id = scenario.get("scenario_id", scenario_path.stem)
    rollout_dir = scenario_path.parent / "rollouts"
    manifest = _json(rollout_dir / "manifest.json", {}) or {}
    trajectory_ids = manifest.get("trajectory_ids", [])
    trajectory_files = [rollout_dir / f"{item}.json" for item in trajectory_ids]
    dialogues = (rollout_dir / "dialogues.md").read_text(encoding="utf-8") if (rollout_dir / "dialogues.md").exists() else ""
    tasks_document = (rollout_dir / "tasks.md").read_text(encoding="utf-8") if (rollout_dir / "tasks.md").exists() else ""
    pipeline_dir = Path(pipeline_root) / scenario_id
    instances = _jsonl(pipeline_dir / "offline" / "instances.jsonl")
    counts = Counter(item.get("task_type") for item in instances)
    branches = _json(pipeline_dir / "validation" / "local_action_interventions.json", []) or []
    expected_branches = sum(
        len(item.get("input", {}).get("candidate_actions", []))
        for item in instances
        if item.get("task_type") == "T3_counterfactual_choice_effect"
    )
    checks = {
        "natural_rollout_manifest": manifest.get("config", {}).get("origin") == "free_form_model_interaction",
        "at_least_two_trajectories": len(trajectory_ids) >= 2,
        "manifest_count_matches": manifest.get("trajectory_count") == len(trajectory_ids),
        "all_trajectory_files_present": bool(trajectory_ids) and all(path.exists() for path in trajectory_files),
        "rollout_natural_language_present": "Free-form Rollout Dialogues" in dialogues and "**Evaluated model:**" in dialogues and "**Environment character:**" in dialogues,
        "t1_present": counts["T1_state_tracking"] >= 1,
        "t2_present": counts["T2_history_sensitive_merge"] >= 1,
        "t3_present": counts["T3_counterfactual_choice_effect"] >= 1,
        "t3_branches_complete": expected_branches > 0 and len(branches) == expected_branches,
        "task_natural_language_present": all(heading in tasks_document for heading in (
            "## T1：当前状态跟踪",
            "## T2：历史敏感合流",
            "## T3：局部反事实 action 效果",
        )),
        "every_instance_described": bool(instances) and all(item.get("instance_id", "") in tasks_document for item in instances),
        "private_review_boundary_stated": "不得作为模型输入或正式 GT" in tasks_document,
    }
    return {
        "scenario_id": scenario_id,
        "trajectory_count": len(trajectory_ids),
        "task_counts": {task: counts[task] for task in REQUIRED_TASKS},
        "intervention_branch_count": len(branches),
        "checks": checks,
        "ready_for_human_spot_check": all(checks.values()),
    }


def build_bundle_audit(scenario_root, pipeline_root):
    results = [
        audit_scenario_bundle(path, pipeline_root)
        for path in discover_scenario_paths(scenario_root)
    ]
    return {
        "format": "socialflux_scenario_bundle_audit_v1",
        "scenario_count": len(results),
        "ready_count": sum(item["ready_for_human_spot_check"] for item in results),
        "all_ready_for_human_spot_check": bool(results) and all(item["ready_for_human_spot_check"] for item in results),
        "scenarios": results,
        "boundary": "Artifact completeness is automated; social plausibility and labels remain pending human review.",
    }


def _markdown(report):
    lines = [
        "# SocialFlux Scenario Bundle Audit", "",
        f"- Ready for human spot check: `{report['ready_count']}/{report['scenario_count']}`",
        f"- All bundles ready: `{str(report['all_ready_for_human_spot_check']).lower()}`",
        "- Boundary: artifact completeness is automated; social plausibility and labels remain pending human review.",
        "",
        "| Scenario | Rollouts | T1 | T2 | T3 | Branches | Review bundle |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in report["scenarios"]:
        counts = item["task_counts"]
        lines.append(
            f"| {item['scenario_id']} | {item['trajectory_count']} | "
            f"{counts['T1_state_tracking']} | {counts['T2_history_sensitive_merge']} | "
            f"{counts['T3_counterfactual_choice_effect']} | {item['intervention_branch_count']} | "
            f"{'ready' if item['ready_for_human_spot_check'] else 'incomplete'} |"
        )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", type=Path, default=Path("configs/scenarios"))
    parser.add_argument("--pipeline-output", type=Path, default=Path("build/pipeline_v2"))
    parser.add_argument("--output", type=Path, default=Path("build/pipeline_v2/scenario_bundle_audit.json"))
    args = parser.parse_args()
    report = build_bundle_audit(args.scenarios, args.pipeline_output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({
        "scenario_count": report["scenario_count"],
        "ready_count": report["ready_count"],
        "all_ready_for_human_spot_check": report["all_ready_for_human_spot_check"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    if not report["all_ready_for_human_spot_check"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
