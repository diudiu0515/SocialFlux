"""Select source rollouts for controlled T2 history adaptation.

Selection is deliberately conservative and evidence based.  It decides whether
an existing rollout is worth adapting; it does not try to repair dialogue text.
"""

from __future__ import annotations

from copy import deepcopy


def source_index(source):
    return {turn["turn_id"]: index for index, turn in enumerate(source.get("turns", []))}


def find_audit_record(audit, *, ordinal, trajectory_id):
    for record in audit.get("records", []):
        if record.get("ordinal") != ordinal:
            continue
        if trajectory_id and record.get("trajectory_id") != trajectory_id:
            continue
        return record
    return None


def assess_source(spec, scenario, source, audit_record, settings=None):
    """Return a transparent eligible/skipped decision for one source rollout."""
    settings = settings or {}
    minimum_history_turns = int(settings.get("minimum_history_turns", 4))
    minimum_branch_turns = int(settings.get("minimum_branch_turns", 2))
    allowed_generation_statuses = set(settings.get(
        "allowed_generation_statuses",
        ["accepted", "short_natural_trajectory", "budget_truncated"],
    ))
    reasons = []
    indexes = source_index(source)
    fork_id = spec.get("fork_turn_id")
    ending_id = spec.get("ending_turn_id")

    if source.get("scenario_id") != scenario.get("scenario_id"):
        reasons.append("source_scenario_mismatch")
    if fork_id not in indexes:
        reasons.append("fork_turn_missing")
    if ending_id not in indexes:
        reasons.append("ending_turn_missing")

    fork_index = indexes.get(fork_id)
    ending_index = indexes.get(ending_id)
    if fork_index is not None and ending_index is not None:
        if not 0 < fork_index < ending_index:
            reasons.append("invalid_fork_ending_order")
        if ending_index < minimum_history_turns:
            reasons.append("insufficient_history_before_ending")
        if ending_index - fork_index < minimum_branch_turns:
            reasons.append("insufficient_adapted_history")
        branch = source.get("turns", [])[fork_index:ending_index]
        if any(turn.get("segment_transition_after") for turn in branch):
            reasons.append("branch_crosses_public_event_boundary")

    gate3 = (audit_record or {}).get("gates", {}).get("gate3", {})
    generation_status = gate3.get("generation_status")
    model_review = gate3.get("model_semantic_review") or {}
    machine = gate3.get("machine_precheck") or {}
    hard_rejects = list(
        (machine.get("structural") or {}).get("hard_reject_reasons") or []
    )
    if audit_record is None:
        reasons.append("source_audit_missing")
    else:
        if generation_status not in allowed_generation_statuses:
            reasons.append("source_generation_status_not_allowed")
        if model_review.get("decision") == "reject":
            reasons.append("source_model_semantic_reject")
        if hard_rejects:
            reasons.append("source_machine_hard_reject")

    return {
        "status": "eligible" if not reasons else "skipped_source_quality",
        "eligible": not reasons,
        "reasons": reasons,
        "metrics": {
            "source_turn_count": len(source.get("turns", [])),
            "history_turns_before_ending": ending_index,
            "adapted_turns_before_ending": (
                ending_index - fork_index
                if fork_index is not None and ending_index is not None else None
            ),
            "generation_status": generation_status,
            "machine_precheck_passed": machine.get("passed"),
            "model_semantic_decision": model_review.get("decision"),
            "machine_hard_reject_reasons": hard_rejects,
        },
        "audit": {
            "trajectory_id": (audit_record or {}).get("trajectory_id"),
            "gate3": deepcopy(gate3),
            "human_review": gate3.get("human_status", "pending"),
            "human_acceptance_claimed": gate3.get("human_status") == "accepted",
        },
    }
