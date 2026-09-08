#!/usr/bin/env python3
"""Audit and summarize task-specific rollout source selection."""

import argparse
from collections import Counter
import json
from pathlib import Path


TASKS = {
    "T1_state_tracking": "t1",
    "T2_history_sensitive_merge": "t2",
    "T3_counterfactual_choice_effect": "t3",
}


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def audit(root):
    root = Path(root)
    scenarios = []
    distributions = {task: Counter() for task in TASKS.values()}
    for scenario_root in sorted(root.glob("IA_PIPE_*")):
        manifest = json.loads((scenario_root / "pipeline_manifest.json").read_text(encoding="utf-8"))
        selection = manifest.get("task_source_selection", {})
        instances = read_jsonl(scenario_root / "offline" / "instances.jsonl")
        attempts_path = scenario_root / "validation" / "t3_selection_attempts.json"
        attempts = (
            json.loads(attempts_path.read_text(encoding="utf-8"))
            if attempts_path.exists() else []
        )
        rollout_root = Path(manifest["rollout_bundle"])
        rollout_manifest = json.loads((rollout_root / "manifest.json").read_text(encoding="utf-8"))
        models = {}
        for identifier in rollout_manifest.get("trajectory_ids", []):
            trajectory = json.loads((rollout_root / f"{identifier}.json").read_text(encoding="utf-8"))
            models[identifier] = trajectory.get("policy_provenance", {}).get("model", trajectory.get("policy_id", "unknown"))

        sources = {task: [] for task in TASKS.values()}
        for instance in instances:
            task = TASKS[instance["task_type"]]
            metadata = instance["metadata"]
            identifiers = metadata.get("source_trajectory_ids") or [metadata.get("source_trajectory_id")]
            for identifier in identifiers:
                if identifier and identifier not in sources[task]:
                    sources[task].append(identifier)
                    distributions[task][models.get(identifier, "unknown")] += 1

        eligible = set(selection.get("eligible_trajectory_ids", []))
        selected_trace = selection.get("selected", {})
        actual_instance_ids = {
            task: {
                instance["instance_id"]
                for instance in instances
                if TASKS[instance["task_type"]] == task
            }
            for task in TASKS.values()
        }
        recorded_instance_ids = {
            task: {item.get("instance_id") for item in selected_trace.get(task, [])}
            for task in TASKS.values()
        }
        ranked_t3_sources = selection.get("t3_source_ids_ranked", [])
        selected_t3_source = sources["t3"][0] if sources["t3"] else None
        selected_attempt_indexes = [
            index for index, item in enumerate(attempts)
            if item.get("status") in {
                "selected", "selected_existing_build", "reused_after_full_audit"
            }
        ]
        selected_attempt_index = selected_attempt_indexes[0] if len(selected_attempt_indexes) == 1 else None
        prior_attempts = attempts[:selected_attempt_index] if selected_attempt_index is not None else []
        prior_rejected_sources = {
            item.get("source_trajectory_id")
            for item in prior_attempts
            if item.get("status") == "rejected_branch_generation"
        }
        scored_attempts = [
            float(item["selection_score"])
            for item in attempts
            if item.get("selection_score") is not None
        ]
        scores_nonincreasing = all(
            left >= right for left, right in zip(scored_attempts, scored_attempts[1:])
        )
        if selected_t3_source in ranked_t3_sources:
            higher_t3_sources = set(
                ranked_t3_sources[:ranked_t3_sources.index(selected_t3_source)]
            )
        else:
            higher_t3_sources = set(ranked_t3_sources)
        best_viable_attempt_order = (
            selected_attempt_index is not None
            and selected_attempt_index == len(attempts) - 1
            and all(
                item.get("status") == "rejected_branch_generation"
                for item in prior_attempts
            )
            and higher_t3_sources.issubset(prior_rejected_sources)
            and scores_nonincreasing
        )
        checks = {
            "quality_report_used": selection.get("basis") == "passed_quality_audits",
            "model_quota_disabled": selection.get("model_quota") is False,
            "model_identity_not_scored": selection.get("model_identity_used_in_score") is False,
            "all_task_sources_quality_eligible": all(
                identifier in eligible for values in sources.values() for identifier in values
            ),
            "actual_task_selection_recorded": all(
                actual_instance_ids[task] == recorded_instance_ids[task]
                for task in TASKS.values()
            ),
            "t3_uses_best_viable_ranked_source": (
                bool(selected_t3_source)
                and selected_t3_source in ranked_t3_sources
                and best_viable_attempt_order
            ),
            "t3_checkpoint_has_history": all(
                float(instance.get("metadata", {}).get("checkpoint_depth", 0)) > 0
                for instance in instances
                if instance["task_type"] == "T3_counterfactual_choice_effect"
            ),
            "t3_attempts_recorded": bool(attempts) and any(
                item.get("status") in {
                    "selected", "selected_existing_build", "reused_after_full_audit"
                }
                for item in attempts
            ),
        }
        scenarios.append({
            "scenario_id": manifest["scenario_id"],
            "passed": all(checks.values()),
            "checks": checks,
            "sources": sources,
            "source_models": {
                task: [models.get(identifier, "unknown") for identifier in values]
                for task, values in sources.items()
            },
            "t3_selection_attempts": attempts,
        })
    return {
        "format": "socialflux_task_source_selection_audit_v1",
        "scenario_count": len(scenarios),
        "passed": len(scenarios) == 20 and all(item["passed"] for item in scenarios),
        "selection_policy": "quality-first, task-specific, no model quota",
        "model_distributions": {
            task: dict(values) for task, values in distributions.items()
        },
        "scenarios": scenarios,
    }


def markdown(report):
    lines = [
        "# Task-specific source selection audit",
        "",
        f"- 结果：`{'PASS' if report['passed'] else 'FAIL'}`",
        f"- Scenario：`{report['scenario_count']}` / `20`",
        "- 规则：先过质量门，T1/T2/T3 分别择优；模型不计分、不设配额。",
        "",
        "## 模型分布（结果，不是目标配额）",
        "",
    ]
    for task, counts in report["model_distributions"].items():
        lines.append(f"- {task.upper()}：" + "；".join(f"{model} = {count}" for model, count in sorted(counts.items())))
    lines.extend(["", "## Scenario 明细", ""])
    for item in report["scenarios"]:
        lines.append(
            f"- `{item['scenario_id']}`：`{'PASS' if item['passed'] else 'FAIL'}`；"
            f"T1={item['sources']['t1']}；T2={item['sources']['t2']}；T3={item['sources']['t3']}"
        )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.pipeline_output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
