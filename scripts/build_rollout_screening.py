#!/usr/bin/env python3
"""Build the protocol-v1 screening audit queue and one-winner pool."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.rollout_gate import HARD_REJECT_REASONS, infer_observed_outcome
from evaluation.screening_protocol import (
    PROTOCOL_VERSION,
    automatic_decision,
    choose_one,
    deterministic_sample,
)


ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = ROOT / "configs" / "scenarios"
EXPERIMENT_ROOT = ROOT / "data" / "formal" / "experiments"
FINAL_GATE_REPORT = ROOT / "reports" / "experiments" / "2026-09-06_four_gate_final_development.json"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def experiment_rank(path):
    match = re.search(r"round(\d+)", path.as_posix())
    stage = int(match.group(1)) if match else (1 if "final" in path.as_posix() else 0)
    kind = 2 if path.name == "judgments.merged.json" else 1
    return stage, kind, path.as_posix()


def load_judgments():
    index = {}
    provenance = {}
    paths = sorted(EXPERIMENT_ROOT.glob("**/judgments.merged.json"))
    paths += sorted(EXPERIMENT_ROOT.glob("**/judgments.primary.json"))
    for path in sorted(paths, key=experiment_rank):
        for record in read_json(path).get("records", []):
            trajectory_id = record.get("trajectory_id")
            if trajectory_id:
                index[trajectory_id] = record
                provenance[trajectory_id] = path.relative_to(ROOT).as_posix()
    return index, provenance


def load_final_audits():
    if not FINAL_GATE_REPORT.exists():
        return {}
    value = read_json(FINAL_GATE_REPORT)
    audits = value.get("gates", {}).get("gate_3_rollout_quality", {}).get("audits", [])
    return {item["trajectory_id"]: item for item in audits}


def load_history_evidence():
    index = {}
    source = {}
    paths = sorted(EXPERIMENT_ROOT.glob("**/history_dependence.json"))
    for path in sorted(paths, key=experiment_rank):
        for record in read_json(path).get("records", []):
            trajectory_id = record.get("trajectory_id")
            if trajectory_id:
                index[trajectory_id] = record
                source[trajectory_id] = path.relative_to(ROOT).as_posix()
    return index, source


def active_ids(rollout_dir):
    manifest = read_json(rollout_dir / "manifest.json")
    return set(manifest.get("trajectory_ids", []))


def trajectory_inventory():
    records = []
    for scenario_dir in sorted(SCENARIO_ROOT.glob("scenario_*")):
        rollout_dir = scenario_dir / "rollouts"
        if not rollout_dir.is_dir() or not (rollout_dir / "manifest.json").exists():
            continue
        active = active_ids(rollout_dir)
        for path in sorted(rollout_dir.glob("*.json")):
            if path.name == "manifest.json":
                continue
            trajectory = read_json(path)
            if not trajectory.get("trajectory_id") or not trajectory.get("turns"):
                continue
            stage = "active_candidate" if trajectory["trajectory_id"] in active else "orphan_archive"
            records.append((path, trajectory, stage))
        rejected_dir = rollout_dir / "rejected"
        for path in sorted(rejected_dir.glob("*.json")):
            if path.name == "manifest.json":
                continue
            trajectory = read_json(path)
            if trajectory.get("trajectory_id") and trajectory.get("turns"):
                records.append((path, trajectory, "rejected_archive"))
    return records


def turn_evidence(judgment, history):
    explicit = judgment.get("evidence", {}) if judgment else {}
    history_turns = (history or {}).get("critical_event_turn_ids", [])
    checkpoint = (history or {}).get("checkpoint_turn_id")
    result = {
        "judge": {key: list(explicit.get(key, [])) for key in (
            "dialogue_coherence", "history_dependence", "character_consistency",
            "state_response_consistency", "interaction_progression", "naturalness",
        )},
        "history_dependence": list(explicit.get("history_dependence", [])),
        "interaction_progression": list(explicit.get("interaction_progression", [])),
        "history_probe_critical_events": list(history_turns),
        "history_probe_checkpoint": checkpoint,
    }
    result["judge_turn_evidence_complete"] = all(result["judge"].values())
    return result


def build_report():
    judgments, judgment_sources = load_judgments()
    final_audits = load_final_audits()
    history, history_sources = load_history_evidence()
    rows = []
    by_scenario = defaultdict(list)
    for path, trajectory, source_stage in trajectory_inventory():
        trajectory_id = trajectory["trajectory_id"]
        judgment = judgments.get(trajectory_id, {})
        audit = final_audits.get(trajectory_id, {})
        scores = audit.get("scores") or judgment.get("scores", {})
        hard = sorted(set(
            audit.get("hard_reject_reasons", [])
            + judgment.get("hard_reject_reasons", [])
        ))
        decision = automatic_decision(scores, hard)
        evidence = turn_evidence(judgment, history.get(trajectory_id))
        provenance = trajectory.get("policy_provenance", {})
        row = {
            "trajectory_id": trajectory_id,
            "scenario_id": trajectory.get("scenario_id"),
            "source_stage": source_stage,
            "trajectory_path": path.relative_to(ROOT).as_posix(),
            "policy_id": trajectory.get("policy_id"),
            "model": provenance.get("model") or (
                provenance.get("provider", {}).get("model")
                if isinstance(provenance.get("provider"), dict) else None
            ),
            "model_family": provenance.get("model_family", "unknown"),
            "seed": (provenance.get("sampling") or {}).get("seed"),
            "turn_count": len(trajectory.get("turns", [])),
            "observed_outcome": infer_observed_outcome(trajectory),
            "automatic_decision": decision["decision"],
            "scores": decision["scores"],
            "mean_quality_score": decision["mean_quality_score"],
            "hard_failures": decision["hard_failures"],
            "missing_evidence": decision["missing_evidence"],
            "rule_reasons": decision["rule_reasons"],
            "judge_rationale": judgment.get("rationale", ""),
            "judge_source": judgment_sources.get(trajectory_id),
            "turn_evidence": evidence,
            "history_evidence": history.get(trajectory_id),
            "history_evidence_source": history_sources.get(trajectory_id),
            "protocol_contract_warnings": (
                [] if evidence["judge_turn_evidence_complete"]
                else ["judge_missing_explicit_turn_id_evidence"]
            ),
        }
        rows.append(row)
        if source_stage == "active_candidate":
            by_scenario[row["scenario_id"]].append(row)

    pass_sample = deterministic_sample(
        [item for item in rows if item["automatic_decision"] == "PASS"], 0.20, "pass"
    )
    reject_sample = deterministic_sample(
        [item for item in rows if item["automatic_decision"] == "REJECT"], 0.20, "reject"
    )
    selected_ids = set()
    scenario_reports = {}
    for scenario_id, candidates in sorted(by_scenario.items()):
        winner, ordered = choose_one(candidates)
        if winner:
            selected_ids.add(winner["trajectory_id"])
        scenario_reports[scenario_id] = {
            "candidate_count": len(candidates),
            "provisional_selected_id": winner["trajectory_id"] if winner else None,
            "selection_status": "provisional_pending_human_comparative_review",
            "ranked_ids": [item["trajectory_id"] for item in ordered],
            "ranking_basis": [
                "automatic decision tier",
                "mean quality",
                "critical-dimension floor",
                "state-response consistency",
                "interaction progression",
            ],
            "model_quota": False,
        }

    for row in rows:
        reasons = []
        if row["source_stage"] == "active_candidate":
            reasons.append("one-winner comparative review: inspect all active candidates")
        if row["automatic_decision"] == "REVIEW":
            reasons.append("protocol REVIEW: 100% human audit")
        if row["trajectory_id"] in pass_sample:
            reasons.append("protocol PASS deterministic audit sample: >=20%")
        if row["trajectory_id"] in reject_sample:
            reasons.append("protocol REJECT deterministic audit sample: 20%")
        if row["protocol_contract_warnings"]:
            reasons.append("judge output contract needs turn-ID verification")
        row["provisional_selected"] = row["trajectory_id"] in selected_ids
        row["human_review_required"] = bool(reasons)
        row["human_review_reasons"] = reasons

    decision_counts = Counter(item["automatic_decision"] for item in rows)
    stage_counts = Counter(item["source_stage"] for item in rows)
    report = {
        "format": "socialflux_rollout_screening_report_v1",
        "protocol_version": PROTOCOL_VERSION,
        "protocol_path": "docs/protocols/SocialFlux_Rollout_Screening_Protocol_v1.md",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "selection_policy": {
            "final_per_scenario": 1,
            "status": "provisional_until_human_comparative_review",
            "user_override": "one canonical trajectory per scenario",
            "raw_candidates_preserved_for_audit": True,
            "model_identity_used_in_ranking": False,
        },
        "summary": {
            "scenario_count": len(by_scenario),
            "inventory_count": len(rows),
            "active_candidate_count": stage_counts["active_candidate"],
            "archive_count": stage_counts["rejected_archive"] + stage_counts["orphan_archive"],
            "human_review_queue_count": sum(item["human_review_required"] for item in rows),
            "provisional_selected_count": len(selected_ids),
            "decision_counts": dict(decision_counts),
            "source_stage_counts": dict(stage_counts),
            "judge_turn_evidence_warning_count": sum(
                bool(item["protocol_contract_warnings"]) for item in rows
            ),
        },
        "audit_policy": {
            "pass_fraction": 0.20,
            "review_fraction": 1.0,
            "reject_fraction": 0.20,
            "comparative_review": "all active candidates",
            "questions": [
                "Is the automatic decision correct?",
                "Which quality dimension is wrong?",
                "What caused the error?",
                "Is it an isolated or systematic issue?",
                "How should the rule or prompt change?",
            ],
        },
        "scenarios": scenario_reports,
        "records": sorted(rows, key=lambda item: (item["scenario_id"], item["source_stage"], item["trajectory_id"])),
    }
    return report


def materialize(report, output_dir):
    selected_root = output_dir / "selected"
    if selected_root.exists():
        shutil.rmtree(selected_root)
    selected_root.mkdir(parents=True, exist_ok=True)
    by_id = {item["trajectory_id"]: item for item in report["records"]}
    selected_manifest = {
        "format": "socialflux_one_trajectory_pool_v1",
        "protocol_version": report["protocol_version"],
        "selection_status": "provisional_pending_human_comparative_review",
        "scenario_count": len(report["scenarios"]),
        "trajectory_count": 0,
        "scenarios": {},
    }
    for scenario_id, scenario in sorted(report["scenarios"].items()):
        trajectory_id = scenario["provisional_selected_id"]
        if not trajectory_id:
            continue
        source = ROOT / by_id[trajectory_id]["trajectory_path"]
        destination = selected_root / scenario_id / f"{trajectory_id}.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        selected_manifest["scenarios"][scenario_id] = {
            "trajectory_id": trajectory_id,
            "source_path": source.relative_to(ROOT).as_posix(),
            "materialized_path": destination.relative_to(ROOT).as_posix(),
            "human_confirmation": "pending",
        }
    selected_manifest["trajectory_count"] = len(selected_manifest["scenarios"])
    (selected_root / "manifest.json").write_text(
        json.dumps(selected_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "build" / "rollout_screening_v1"
    )
    args = parser.parse_args()
    report = build_report()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "screening_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    materialize(report, args.output_dir)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
