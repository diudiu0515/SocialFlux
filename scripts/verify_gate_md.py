#!/usr/bin/env python3
"""Emit a clause-by-clause, evidence-backed gate.md completion report."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.rollout_gate import audit_pool_contract
from scripts.audit_formal_rollout_pool import load_records
from scripts.run_pipeline import load_rollout_config


def read_optional(path):
    return json.loads(path.read_text(encoding="utf-8")) if path and path.exists() else None


def check(clause, passed, evidence, pending=False):
    return {
        "clause": clause,
        "status": "passed" if passed else ("pending" if pending else "failed"),
        "passed": bool(passed),
        "evidence": evidence,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollout-config", type=Path, default=Path("configs/formal_rollout_pool.local.json"))
    parser.add_argument("--raw-root", type=Path, default=Path("data/formal/raw"))
    parser.add_argument("--gate-report", type=Path, default=Path("data/formal/gate_report.json"))
    parser.add_argument("--backbone-evidence", type=Path, default=Path("data/formal/environment/backbone_sensitivity.json"))
    parser.add_argument("--formal-gt", type=Path, default=Path("data/formal/annotations/formal_gt.json"))
    parser.add_argument("--four-gate-report", type=Path, default=Path("data/formal/four_gate_report.json"))
    parser.add_argument("--output", type=Path, default=Path("build/gate_md/report.json"))
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    config = load_rollout_config(args.rollout_config)
    policies = config["policies"]
    total_runs = sum(item.get("runs", 1) for item in policies)
    api_runs = sum(item.get("runs", 1) for item in policies if item.get("source_type") == "api")
    local_families = sorted({item.get("model_family") for item in policies if item.get("source_type") == "local"})
    formal_models = {item["provider"].get("model") for item in policies}
    trajectories = load_records(args.raw_root) if args.raw_root.exists() else []
    pool = audit_pool_contract(trajectories) if trajectories else None
    gate_report = read_optional(args.gate_report)
    backbone = read_optional(args.backbone_evidence)
    formal_gt = read_optional(args.formal_gt)
    four_gate = read_optional(args.four_gate_report)
    selection_reports = (gate_report or {}).get("selections", {})
    trajectory_audits = (gate_report or {}).get("trajectory_audits", [])
    passed_audits = [item for item in trajectory_audits if item.get("passed")]
    checks = [
        check("1_same_stateful_free_rollout_to_tasks", config.get("pool_stage") == "formal_raw" and not any(token in item["policy_id"].lower() for item in policies for token in ("repair", "neutral", "escalat")), {"pool_stage": config.get("pool_stage"), "policy_ids": [item["policy_id"] for item in policies]}),
        check("2_local_primary_heterogeneous_sources", len(local_families) >= 3 and api_runs / total_runs <= 0.30, {"local_families": local_families, "api_run_fraction": round(api_runs / total_runs, 4)}),
        check("3_prioritized_20_to_40b_local_model", any(item.get("source_type") == "local" and 20 <= item.get("model_parameters_billion", 0) <= 40 for item in policies), {"models": [{"model": item["provider"].get("model"), "parameters_billion": item.get("model_parameters_billion")} for item in policies]}),
        check("4_api_is_optional_and_at_most_30_percent", api_runs / total_runs <= 0.30, {"api_runs": api_runs, "total_runs": total_runs}),
        check("5_twelve_raw_rollouts_per_scenario", bool(pool) and pool["checks"]["each_scenario_has_at_least_12_raw"], pool or {"trajectory_count": 0}, pending=not trajectories),
        check("6_six_dimension_quality_and_hard_reject_gate", bool(gate_report) and (gate_report.get("passed_quality_count", 0) >= 80), {"gate_report_present": bool(gate_report), "passed_quality_count": (gate_report or {}).get("passed_quality_count", 0)}, pending=not gate_report),
        check("7_post_hoc_diverse_four_to_six_selection", bool(gate_report) and (gate_report.get("all_scenarios_selection_passed") is True) and len(selection_reports) == 20, {"scenario_selection_count": len(selection_reports)}, pending=not gate_report),
        check("8_history_dependence_full_recent_removed", bool(passed_audits) and all(not item.get("judge_errors") and "history_dependence" in item.get("scores", {}) for item in passed_audits), {"audited_trajectory_count": len(trajectory_audits), "passed_trajectory_count": len(passed_audits)}, pending=not trajectory_audits),
        check("9_development_and_final_are_separate", args.raw_root.resolve() != Path("configs/scenarios").resolve() and "/root/autodl-tmp/models/Qwen3.5-9B-modelscope" not in formal_models, {"formal_raw_root": str(args.raw_root), "formal_policy_models": sorted(formal_models)}),
        check("10_environment_policy_separation_and_backbone_sensitivity", bool(pool) and pool["checks"]["environment_policy_separated"] and bool(backbone) and backbone.get("record", {}).get("passed") is True and bool(four_gate) and four_gate.get("gates", {}).get("gate_2_environment_validity", {}).get("passed") is True, {"model_separation": pool["checks"]["environment_policy_separated"] if pool else None, "backbone_evidence_present": bool(backbone), "backbone_passed": (backbone or {}).get("record", {}).get("passed"), "full_environment_gate_passed": (four_gate or {}).get("gates", {}).get("gate_2_environment_validity", {}).get("passed")}, pending=not trajectories or not backbone or not four_gate),
        check("11_primary_plus_cross_family_secondary_judge", bool(gate_report) and gate_report.get("judge_protocol", {}).get("passed") is True, (gate_report or {}).get("judge_protocol", {"present": False}), pending=not gate_report),
        check("12_human_annotation_agreement_adjudication_gt", bool(four_gate) and four_gate.get("research_ready") is True and bool(formal_gt) and formal_gt.get("format") == "socialflux_formal_human_gt_v1" and formal_gt.get("instance_count", 0) > 0 and all(item.get("label_status") == "formal_human_gt" for item in formal_gt.get("records", [])), {"four_gate_research_ready": (four_gate or {}).get("research_ready"), "formal_gt_present": bool(formal_gt), "instance_count": (formal_gt or {}).get("instance_count", 0), "fleiss_kappa": (formal_gt or {}).get("fleiss_kappa_exact_label")}, pending=not formal_gt or not four_gate),
    ]
    result = {
        "format": "socialflux_gate_md_acceptance_v1",
        "all_complete": all(item["passed"] for item in checks),
        "checks": checks,
        "blocking_clauses": [item["clause"] for item in checks if not item["passed"]],
        "human_boundary": "Clause 12 and the scenario/S0-D0 signatures upstream of formal rollout require real human attestations; automation cannot create them.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# gate.md Acceptance", "", f"- All complete: `{str(result['all_complete']).lower()}`", "", "| Clause | Status |", "|---|---|"]
    lines.extend(f"| {item['clause']} | `{item['status']}` |" for item in checks)
    lines.extend(["", "## Human boundary", "", result["human_boundary"], ""])
    args.output.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "all_complete": result["all_complete"], "blocking_clauses": result["blocking_clauses"]}, ensure_ascii=False, indent=2))
    if args.strict and not result["all_complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
