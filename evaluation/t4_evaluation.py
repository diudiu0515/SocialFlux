"""Online T4 trajectory and terminal-judgment contract."""

from copy import deepcopy

from environment.policy_context import public_scenario_context
from evaluation.t4_rubric import T4_RUBRIC


T4_MAX_TURNS = 20
# Compatibility alias for callers that use the historical constant name.
T4_TARGET_TURNS = T4_MAX_TURNS
T4_DIMENSIONS = (
    "goal_achievement",
    "state_adaptation",
    "risk_management",
    "recovery",
    "relationship_outcome",
)


def assert_t4_trajectory(trajectory):
    """Accept a coherent natural ending at or before the 20-turn maximum."""
    turns = trajectory.get("turns", [])
    if not 1 <= len(turns) <= T4_MAX_TURNS:
        raise ValueError(
            f"T4 trajectory must contain 1 to {T4_MAX_TURNS} turns; "
            f"received {len(turns)}"
        )
    expected_ids = [f"t{index}" for index in range(1, len(turns) + 1)]
    if [turn.get("turn_id") for turn in turns] != expected_ids:
        raise ValueError("T4 trajectory turn IDs must be contiguous t1..t20")
    ending = trajectory.get("ending") or {}
    if ending.get("turn_id") != len(turns):
        raise ValueError("T4 ending turn must match the actual last turn")
    if ending.get("reason") not in {"natural_completion", "max_turns"}:
        raise ValueError("T4 trajectory must have a natural or maximum-horizon ending")
    if ending.get("reason") == "max_turns" and len(turns) != T4_MAX_TURNS:
        raise ValueError("max_turns ending is valid only at turn 20")
    return trajectory


def public_t4_judge_packet(trajectory, scenario):
    """Expose only evidence a T4 judge may use by default."""
    assert_t4_trajectory(trajectory)
    context = public_scenario_context(scenario)
    return {
        "task": "T4_online_long_horizon_evaluation",
        "horizon_turns": T4_MAX_TURNS,
        "horizon_max_turns": T4_MAX_TURNS,
        "observed_turns": len(trajectory["turns"]),
        "scenario_id": scenario["scenario_id"],
        "evaluated_agent_role": context["evaluated_agent_role"],
        "target_character": context["environment_role"],
        "public_background": context["background"],
        "public_situation": context["public_situation"],
        "opening_response": scenario.get("opening_response", ""),
        "ending": {key: trajectory["ending"][key] for key in ("reason", "turn_id")},
        "observable_trajectory": [
            {
                "turn_id": turn["turn_id"],
                "segment_id": turn.get("segment_id", "single_interaction"),
                "segment_turn_id": turn.get("segment_turn_id"),
                "elapsed_time_before": turn.get("elapsed_time_before", 0),
                "elapsed_time_after": turn.get("elapsed_time_after", 0),
                "evaluated_action": {"text": turn["policy_action"]["text"]},
                "environment_response": turn["environment_response"],
                "public_events_after": deepcopy(
                    (turn.get("segment_transition_after") or {}).get(
                        "public_events", []
                    )
                ),
            }
            for turn in trajectory["turns"]
        ],
        "public_timeline": deepcopy(trajectory.get("public_timeline", [])),
        "rubric": {
            **deepcopy(T4_RUBRIC),
            "dimensions": list(T4_DIMENSIONS),
            "scale": [0, 10],
            "principle": (
                "Score adaptation relative to the explicit goal and real trade-off; "
                "low conflict is not automatically better."
            ),
        },
        "private_fields_excluded": [
            "hidden_intention", "state", "dynamics", "appraisal", "state_delta",
            "trigger_conditions", "future_branches", "observable_expression",
            "media_metadata",
        ],
    }


def validate_t4_judgment(value, valid_turn_ids):
    """Validate one terminal T4 judgment without treating it as human GT."""
    if set(value) != {"dimensions", "overall_uncertainty", "human_validation_status"}:
        raise ValueError("T4 judgment fields mismatch")
    if value["human_validation_status"] != "not_human_validated":
        raise ValueError("automatic T4 judgment cannot claim human validation")
    dimensions = value["dimensions"]
    if set(dimensions) != set(T4_DIMENSIONS):
        raise ValueError("T4 judgment dimensions mismatch")
    allowed = set(valid_turn_ids)
    for name, record in dimensions.items():
        required = {
            "score", "evidence_turn_ids", "rationale", "uncertainty",
            "insufficient_evidence",
        }
        if set(record) != required:
            raise ValueError(f"T4 judgment fields mismatch: {name}")
        score = record["score"]
        if score is not None and (
            isinstance(score, bool)
            or not isinstance(score, int)
            or not 0 <= score <= 10
        ):
            raise ValueError(f"T4 score must be null or integer 0..10: {name}")
        evidence = record["evidence_turn_ids"]
        if (
            not isinstance(evidence, list)
            or not 1 <= len(evidence) <= 3
            or not all(isinstance(item, str) for item in evidence)
            or len(set(evidence)) != len(evidence)
            or not set(evidence) <= allowed
        ):
            raise ValueError(f"T4 evidence IDs invalid: {name}")
        if any(not isinstance(record[key], str) or not record[key].strip()
               for key in ("rationale", "uncertainty")):
            raise ValueError(f"T4 rationale/uncertainty missing: {name}")
        if not isinstance(record["insufficient_evidence"], bool):
            raise ValueError(f"T4 insufficient_evidence must be boolean: {name}")
        if score is None and not record["insufficient_evidence"]:
            raise ValueError(f"null T4 score requires insufficient_evidence: {name}")
        if score is None and name != "recovery":
            raise ValueError("only recovery can be not applicable")
    if not isinstance(value["overall_uncertainty"], str) or not value["overall_uncertainty"].strip():
        raise ValueError("T4 overall_uncertainty is empty")
    return value
