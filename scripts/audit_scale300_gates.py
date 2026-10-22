#!/usr/bin/env python3
"""Produce machine-only Gate 1-4 dossiers for Scale300.

This report never writes human attestations.  Gate 4 is a pre-construction
readiness audit until a human-confirmed Gate 3 trajectory exists.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas.validate import validate_scenario


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "configs" / "scale300_v1" / "design_matrix.json"
REVIEW = ROOT / "build" / "scale300_v1" / "review.json"
OUTPUT = ROOT / "build" / "scale300_v1" / "automatic_gate_audit.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def nonzero(value):
    if isinstance(value, dict):
        return any(nonzero(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(nonzero(item) for item in value)
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value != 0


def gate1(scenario, row):
    schema_valid = True
    schema_error = None
    try:
        validate_scenario(scenario)
    except Exception as exc:
        schema_valid = False
        schema_error = f"{type(exc).__name__}: {exc}"
    source = scenario.get("source", {})
    narrative = scenario.get("narrative_design", {})
    checks = {
        "schema_valid": schema_valid,
        "social_mechanism_present": bool(scenario.get("mechanism")),
        "both_roles_and_goals_present": bool(
            scenario.get("evaluated_agent_role", {}).get("explicit_goal")
            and scenario.get("environment_agent", {}).get("explicit_goal")
        ),
        "history_present": len(narrative.get("relevant_history", [])) >= 3,
        "meaningful_choice_space_present": len(narrative.get("meaningful_choice_space", [])) >= 3,
        "initial_state_and_dynamics_present": bool(
            scenario.get("initial_state") and scenario.get("initial_dynamics")
        ),
        "source_provenance_present": bool(
            source.get("type") and source.get("provenance_id")
            and source.get("provenance_note")
        ),
        "narrative_source_fields_present": (
            source.get("type") != "narrative-derived"
            or bool(source.get("work_title") and source.get("year") and source.get("medium"))
        ),
        "task_potential_declared": set(row.get("task_potential", {})) == {"T1", "T2", "T3", "T4"},
        "natural_max_20_contract": scenario.get("max_turns") == 20,
    }
    return {
        "automatic_status": "machine_pass" if all(checks.values()) else "machine_review",
        "checks": checks,
        "schema_error": schema_error,
        "human_status": "pending",
        "human_required": [
            "hard-constraint semantic review",
            "six 1-5 quality ratings",
            "source/provenance verification where applicable",
            "initial-state freeze and runtime dynamics seed validation",
        ],
    }


def gate2(candidate, trajectory):
    framework = (candidate.get("latest_attempt") or {}).get("framework") or {}
    turns = (trajectory or {}).get("turns", [])
    checks = {
        "trajectory_evidence_present": bool(turns),
        "two_separate_environment_llm_stages": framework.get("environment_llm_stages_per_turn") == 2,
        "appraisal_update_response_and_ledger_each_turn": framework.get(
            "every_turn_has_appraisal_update_response_and_ledger"
        ) is True,
        "cross_turn_state_and_dynamics_chain": framework.get(
            "cross_turn_state_and_dynamics_chain"
        ) is True,
        "separate_stage_request_counts_present": framework.get(
            "separate_stage_request_counts_present"
        ) is True,
        "state_update_flow_ran_each_turn": bool(turns) and all(
            "state_before" in turn and "state_after" in turn
            and "dynamics_before" in turn and "dynamics_after" in turn
            for turn in turns
        ),
    }
    return {
        "automatic_status": "machine_pass_framework" if all(checks.values()) else "machine_review",
        "checks": checks,
        "shared_experiment_evidence": {
            "scope": "existing 20-scenario matched pilot; does not replace Scale300 human validation",
            "E3": "32 checkpoints / 18 machine-pass",
            "E4": "20/20 strict pairs; direction overall/state/dynamics 0.9400/0.9429/0.9333",
            "E5": "20/20 checkpoints machine-pass",
            "E6": "exact direction 0.7078; change/no-change 0.7128; sign reversal 0.005; replay failure 0",
        },
        "human_status": "pending",
        "human_required": [
            "E1 sampled state-transition agreement",
            "E2 full-trajectory plausibility",
            "E3-E5 control and semantic spot-check",
        ],
    }


def gate3(candidate, trajectory):
    status = candidate.get("generation_status")
    precheck = candidate.get("machine_precheck") or {}
    semantic = candidate.get("model_semantic_review") or {"decision": "pending"}
    model_decision = semantic.get("decision", "pending")
    checks = {
        "current_scenario_version": (
            (candidate.get("latest_attempt") or {}).get("scenario_version_matches_current") is True
        ),
        "nonempty_trajectory": bool((trajectory or {}).get("turns")),
        "main_window_and_machine_precheck": status == "accepted" and precheck.get("passed") is True,
        "model_semantic_not_rejected": model_decision not in {"reject"},
    }
    if status == "accepted" and model_decision == "approve":
        automatic_status = "machine_and_model_pass_human_pending"
    elif status == "accepted":
        automatic_status = "machine_pass_model_or_human_pending"
    else:
        automatic_status = "machine_review_or_reject"
    return {
        "automatic_status": automatic_status,
        "checks": checks,
        "generation_status": status,
        "machine_precheck": precheck,
        "model_semantic_review": semantic,
        "human_status": "pending",
        "human_required": [
            "full-text six-dimension review",
            "hard-reject semantic confirmation with turn evidence",
            "history-dependence evidence",
            "canonical trajectory selection",
        ],
    }


def gate4(candidate, trajectory):
    turns = (trajectory or {}).get("turns", [])
    changed = [
        turn.get("turn_id") for turn in turns
        if nonzero(turn.get("numeric_state_delta", {}))
        or nonzero(turn.get("numeric_dynamics_delta", {}))
    ]
    future5 = [
        turn.get("turn_id") for index, turn in enumerate(turns)
        if len(turns) - index - 1 >= 5
    ]
    ending = (trajectory or {}).get("ending") or {}
    gate3_machine_candidate = candidate.get("generation_status") == "accepted"
    readiness = {
        "T1": {
            "automatic_ready": gate3_machine_candidate and bool(changed),
            "candidate_checkpoint_count": len(changed),
            "note": "labels not formal before Gate 3 human confirmation",
        },
        "T2": {
            "automatic_ready": False,
            "candidate_pair_count": 0,
            "note": "requires controlled A/B histories with identical ending; one rollout is insufficient",
        },
        "T3": {
            "automatic_ready": gate3_machine_candidate and bool(future5),
            "candidate_checkpoint_count_with_5_turn_window": len(future5),
            "note": "counterfactual branches and 2-4 actions remain to be generated after Gate 3 selection",
        },
        "T4": {
            "automatic_ready": bool(turns) and ending.get("reason") in {"natural_completion", "max_turns"},
            "ending": ending,
        },
    }
    return {
        "automatic_status": (
            "preconstruction_partial_ready_human_gate3_required"
            if any(item["automatic_ready"] for item in readiness.values())
            else "blocked_or_not_ready"
        ),
        "task_readiness": readiness,
        "formal_instance_constructed": False,
        "human_status": "pending_after_task_construction",
        "human_required": [
            "two independent reviewers inspect the same deterministic 10% sample per task type",
            "third reviewer adjudicates disagreements only",
        ],
    }


def main():
    matrix = read(MATRIX)
    review = read(REVIEW)
    rows = {item["scenario_id"]: item for item in matrix["scenarios"]}
    records = []
    counts = {name: Counter() for name in ("gate1", "gate2", "gate3", "gate4")}
    for candidate in review["candidates"]:
        scenario_id = candidate["scenario_id"]
        ordinal = int(rows[scenario_id]["ordinal"])
        scenario_path = (
            MATRIX.parent / "scenarios" / f"scenario_{ordinal:03d}"
            / f"scenario_{ordinal:03d}.json"
        )
        scenario = read(scenario_path)
        latest = candidate.get("latest_attempt") or {}
        artifact = latest.get("artifact_path")
        trajectory = read(ROOT / artifact) if artifact and (ROOT / artifact).is_file() else None
        gates = {
            "gate1": gate1(scenario, rows[scenario_id]),
            "gate2": gate2(candidate, trajectory),
            "gate3": gate3(candidate, trajectory),
            "gate4": gate4(candidate, trajectory),
        }
        for name, result in gates.items():
            counts[name][result["automatic_status"]] += 1
        records.append({
            "scenario_id": scenario_id,
            "ordinal": ordinal,
            "title": rows[scenario_id]["title"],
            "trajectory_id": latest.get("trajectory_id"),
            "artifact_path": artifact,
            "gates": gates,
        })
    payload = {
        "format": "socialflux_scale300_automatic_gate_audit_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scenario_count": len(records),
        "scope": "automatic and model-proposed evidence only",
        "human_attestation_written": False,
        "formal_release_ready": False,
        "summary": {name: dict(counter) for name, counter in counts.items()},
        "records": records,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
