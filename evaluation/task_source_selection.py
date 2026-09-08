"""Task-specific source ranking for SocialFlux offline instances.

Model identity is deliberately excluded from every score.  It remains provenance
for audit only; a model may win zero, one, or all tasks in a scenario.
"""

from collections import defaultdict

from environment.delta_mapper import flatten_state


TASK_WEIGHTS = {
    "t1": {
        "state_response_consistency": 0.40,
        "history_dependence": 0.25,
        "dialogue_coherence": 0.20,
        "character_consistency": 0.15,
    },
    "t2": {
        "history_dependence": 0.35,
        "state_response_consistency": 0.25,
        "dialogue_coherence": 0.15,
        "naturalness": 0.15,
        "character_consistency": 0.10,
    },
    "t3": {
        "interaction_progression": 0.30,
        "state_response_consistency": 0.25,
        "dialogue_coherence": 0.20,
        "naturalness": 0.15,
        "character_consistency": 0.10,
    },
}


def _weighted_score(audit, weights):
    scores = audit.get("scores", {})
    return round(sum(float(scores.get(key, 0.0)) * weight for key, weight in weights.items()), 4)


def select_task_sources(trajectories, audits, t1_source_count=3):
    """Return independent T1/T2/T3 rankings after the common quality gate."""
    by_id = {item["trajectory_id"]: item for item in trajectories}
    audit_by_id = {
        item["trajectory_id"]: item
        for item in audits or []
        if item.get("passed") is True and item.get("trajectory_id") in by_id
    }
    if audits:
        eligible_ids = set(audit_by_id)
        basis = "passed_quality_audits"
    else:
        # Development compatibility only. Formal-selected pools always carry audits.
        eligible_ids = set(by_id)
        audit_by_id = {
            identifier: {"scores": {name: 0.5 for name in set().union(*[set(w) for w in TASK_WEIGHTS.values()])}}
            for identifier in eligible_ids
        }
        basis = "unjudged_development_fallback"

    scores = defaultdict(dict)
    rankings = {}
    for task, weights in TASK_WEIGHTS.items():
        for identifier in sorted(eligible_ids):
            scores[task][identifier] = _weighted_score(audit_by_id[identifier], weights)
        rankings[task] = sorted(
            eligible_ids,
            key=lambda identifier: (-scores[task][identifier], identifier),
        )

    return {
        "format": "socialflux_task_source_selection_v1",
        "strategy": "quality_gate_then_task_specific_weighted_ranking",
        "model_quota": False,
        "model_identity_used_in_score": False,
        "basis": basis,
        "eligible_trajectory_ids": sorted(eligible_ids),
        "t1_source_ids": rankings["t1"][: max(1, t1_source_count)],
        "t2_source_ids_ranked": rankings["t2"],
        "t3_source_ids_ranked": rankings["t3"],
        "scores": {task: dict(values) for task, values in scores.items()},
        "weights": TASK_WEIGHTS,
    }


def rank_t3_checkpoints(trajectories, source_scores):
    """Prefer strong T3 sources and later, history-bearing checkpoints."""
    ranked = []
    for trajectory in trajectories:
        turns = trajectory.get("turns", [])
        if len(turns) < 2:
            continue
        source_score = float(source_scores.get(trajectory["trajectory_id"], 0.0))
        for index, turn in enumerate(turns[1:], start=1):
            depth = index / max(1, len(turns) - 1)
            checkpoint_utility = max(0.0, 1.0 - abs(depth - (2 / 3)))
            ranked.append({
                "trajectory": trajectory,
                "turn": turn,
                "source_score": round(source_score, 4),
                "checkpoint_depth": round(depth, 4),
                "checkpoint_utility": round(checkpoint_utility, 4),
                "selection_score": round(
                    0.90 * source_score + 0.10 * checkpoint_utility,
                    4,
                ),
            })
    return sorted(
        ranked,
        key=lambda item: (
            -item["selection_score"],
            item["trajectory"]["trajectory_id"],
            item["turn"]["turn_id"],
        ),
    )


def rank_t1_checkpoints(trajectories, source_scores):
    """Rank informative, history-bearing T1 checkpoints without exposing state."""
    rows = []
    for trajectory in trajectories:
        turns = trajectory.get("turns", [])
        for index, turn in enumerate(turns):
            before = flatten_state(turn.get("state_before", {}))
            after = flatten_state(turn.get("state_after", {}))
            movement = sum(
                abs(after.get(key, value) - value)
                for key, value in before.items()
            )
            rows.append({
                "trajectory": trajectory,
                "turn_index": index,
                "source_score": float(
                    source_scores.get(trajectory["trajectory_id"], 0.0)
                ),
                "depth": (index + 1) / max(1, len(turns)),
                "movement": movement,
            })
    max_movement = max((item["movement"] for item in rows), default=1.0) or 1.0
    for item in rows:
        item["selection_score"] = round(
            0.75 * item["source_score"]
            + 0.15 * item["depth"]
            + 0.10 * item["movement"] / max_movement,
            4,
        )
    return sorted(
        rows,
        key=lambda item: (
            -item["selection_score"],
            item["trajectory"]["trajectory_id"],
            -item["turn_index"],
        ),
    )
