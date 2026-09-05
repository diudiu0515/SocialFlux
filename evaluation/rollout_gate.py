"""Executable quality, diversity, and provenance gates for rollout pools.

The module deliberately separates machine evidence from human or independent
judge evidence. A missing judgment never becomes an implicit pass.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import math
import re

from environment.delta_mapper import flatten_state
from evaluation.instance_quality import audit_trajectory
from providers.text import text_similarity


QUALITY_DIMENSIONS = (
    "dialogue_coherence",
    "history_dependence",
    "character_consistency",
    "state_response_consistency",
    "interaction_progression",
    "naturalness",
)

HARD_REJECT_REASONS = (
    "hidden_state_leakage",
    "malformed_output",
    "repetitive_loop",
    "severe_character_contradiction",
    "broken_dialogue_logic",
    "meaningless_premature_ending",
    "nonsensical_state_oscillation",
    "implementation_induced_state_saturation",
)

_PRIVATE_MARKERS = (
    "state_before",
    "state_after",
    "state_delta",
    "dynamics_before",
    "dynamics_after",
    "hidden_intention",
    "隐藏意图",
    "潜在状态",
    "<state>",
)


def _public_text(trajectory):
    return "\n".join(
        str(value)
        for turn in trajectory.get("turns", [])
        for value in (
            turn.get("policy_action", {}).get("text", ""),
            turn.get("environment_response", ""),
        )
    )


def _state_series(trajectory):
    turns = trajectory.get("turns", [])
    if not turns:
        return {}
    first = flatten_state(turns[0].get("state_before", {}))
    series = {key: [value] for key, value in first.items()}
    for turn in turns:
        after = flatten_state(turn.get("state_after", {}))
        for key in series:
            if key in after:
                series[key].append(after[key])
    return series


def _oscillation_fraction(trajectory):
    suspicious = 0
    eligible = 0
    for values in _state_series(trajectory).values():
        deltas = [right - left for left, right in zip(values, values[1:])]
        signs = [1 if value > 0 else -1 for value in deltas if value]
        if len(signs) < 4:
            continue
        eligible += 1
        reversals = sum(left != right for left, right in zip(signs, signs[1:]))
        if reversals >= len(signs) - 1 and sum(abs(value) for value in deltas) >= 6:
            suspicious += 1
    return suspicious / eligible if eligible else 0.0


def _saturation_fraction(trajectory):
    values = [
        value
        for series in _state_series(trajectory).values()
        for value in series[1:]
    ]
    return sum(value in (0, 10) for value in values) / len(values) if values else 0.0


def _progression_score(trajectory):
    turns = trajectory.get("turns", [])
    if len(turns) < 2:
        return 0.0
    signatures = []
    for turn in turns:
        state = flatten_state(turn.get("state_after", {}))
        dynamics = flatten_state(turn.get("dynamics_after", {}))
        signatures.append(tuple(sorted({**state, **{f"d:{k}": v for k, v in dynamics.items()}}.items())))
    state_change = (len(set(signatures)) - 1) / max(1, len(signatures) - 1)
    first = turns[0].get("policy_action", {}).get("text", "")
    last = turns[-1].get("policy_action", {}).get("text", "")
    lexical_change = 1.0 - text_similarity(first, last)
    return round(min(1.0, 0.65 * state_change + 0.35 * lexical_change), 4)


def _heuristic_scores(trajectory, structural):
    checks = structural["checks"]
    coherence_keys = (
        "actions_nonempty",
        "responses_nonempty",
        "actions_follow_dialogue_format",
        "responses_follow_dialogue_format",
    )
    natural_keys = (
        "actions_no_near_repetition",
        "responses_no_near_repetition",
        "responses_concise",
    )
    return {
        "dialogue_coherence": sum(bool(checks[key]) for key in coherence_keys) / len(coherence_keys),
        "interaction_progression": _progression_score(trajectory),
        "naturalness": sum(bool(checks[key]) for key in natural_keys) / len(natural_keys),
    }


def _validated_judge_scores(judgment):
    if not judgment:
        return {}, []
    scores = judgment.get("scores", {})
    valid = {}
    errors = []
    for key in QUALITY_DIMENSIONS:
        value = scores.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 1 <= value <= 5:
            errors.append(f"invalid_or_missing_score:{key}")
        else:
            valid[key] = float(value) / 5.0
    if judgment.get("hard_reject_reasons") is None:
        errors.append("missing_hard_reject_reasons")
    unknown = set(judgment.get("hard_reject_reasons", [])) - set(HARD_REJECT_REASONS)
    if unknown:
        errors.append("unknown_hard_reject_reason:" + ",".join(sorted(unknown)))
    return valid, errors


def audit_rollout(trajectory, judgment=None, history_evidence=None):
    """Return a conservative gate record for one trajectory."""
    structural = audit_trajectory(trajectory)
    turns = trajectory.get("turns", [])
    public_text = _public_text(trajectory).lower()
    saturation = _saturation_fraction(trajectory)
    oscillation = _oscillation_fraction(trajectory)
    hard_rejects = []
    if any(marker in public_text for marker in _PRIVATE_MARKERS):
        hard_rejects.append("hidden_state_leakage")
    if not structural["checks"]["actions_nonempty"] or not structural["checks"]["responses_nonempty"]:
        hard_rejects.append("malformed_output")
    if not (
        structural["checks"]["actions_no_exact_repetition"]
        and structural["checks"]["responses_no_exact_repetition"]
        and structural["checks"]["actions_no_near_repetition"]
        and structural["checks"]["responses_no_near_repetition"]
    ):
        hard_rejects.append("repetitive_loop")
    if len(turns) < 5:
        hard_rejects.append("meaningless_premature_ending")
    if oscillation > 0.5:
        hard_rejects.append("nonsensical_state_oscillation")
    if saturation > 0.75:
        hard_rejects.append("implementation_induced_state_saturation")

    judge_scores, judge_errors = _validated_judge_scores(judgment)
    if judgment:
        hard_rejects.extend(judgment.get("hard_reject_reasons", []))
    history_evidence_failed = False
    if history_evidence is None:
        judge_errors.append("missing_history_dependence_evidence")
    elif history_evidence.get("passed") is not True:
        history_evidence_failed = True
        judge_errors.append("history_dependence_evidence_failed")
    else:
        score = history_evidence.get("score", 1.0)
        if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= 1:
            judge_errors.append("invalid_history_dependence_score")
        # The intervention score measures how strongly behavior/interpretation
        # changes when history is removed.  It is independent evidence and must
        # not overwrite the judge's 1–5 History Dependence quality score.
    hard_rejects = sorted(set(hard_rejects))
    heuristic_scores = _heuristic_scores(trajectory, structural)
    # Heuristics remain diagnostics only. They cannot stand in for independent
    # judgment on a formal quality gate dimension.
    scores = {
        key: value for key, value in judge_scores.items()
        if key in QUALITY_DIMENSIONS
    }
    missing = [key for key in QUALITY_DIMENSIONS if key not in scores]
    overall = (
        round(sum(scores.values()) / len(QUALITY_DIMENSIONS), 4)
        if not missing else None
    )
    threshold_failures = []
    if not missing:
        threshold_failures.extend(
            key for key, value in scores.items() if value < 0.6
        )
        threshold_failures.extend(
            key for key in ("history_dependence", "character_consistency", "naturalness")
            if scores[key] < 0.8
        )
        if overall < 0.7:
            threshold_failures.append("overall_score")
    passed = (
        not hard_rejects
        and not judge_errors
        and not missing
        and not threshold_failures
    )
    pending = bool(missing or judge_errors) and not history_evidence_failed
    return {
        "trajectory_id": trajectory.get("trajectory_id"),
        "scenario_id": trajectory.get("scenario_id"),
        "passed": passed,
        "status": "passed" if passed else ("pending_evidence" if pending else "rejected"),
        "scores": scores,
        "overall_score": overall,
        "missing_evidence": missing,
        "judge_errors": judge_errors,
        "hard_reject_reasons": hard_rejects,
        "diagnostics": {
            "turn_count": len(turns),
            "heuristic_scores": heuristic_scores,
            "threshold_failures": sorted(set(threshold_failures)),
            "state_oscillation_fraction": round(oscillation, 4),
            "state_saturation_fraction": round(saturation, 4),
            "structural_gate": structural,
        },
    }


def infer_observed_outcome(trajectory):
    """Assign a descriptive post-hoc outcome; this is not a rollout policy."""
    turns = trajectory.get("turns", [])
    if not turns:
        return "premature_ending"
    start_state = flatten_state(turns[0].get("state_before", {}))
    end_state = flatten_state(turns[-1].get("state_after", {}))
    start_dyn = flatten_state(turns[0].get("dynamics_before", {}))
    end_dyn = flatten_state(turns[-1].get("dynamics_after", {}))
    def composite_change(positive_tokens, negative_tokens, start, end):
        changes = []
        for key, final in end.items():
            change = final - start.get(key, final)
            lowered = key.lower()
            if any(token in lowered for token in positive_tokens):
                changes.append(change)
            elif any(token in lowered for token in negative_tokens):
                changes.append(-change)
        return sum(changes) / len(changes) if changes else 0.0

    relationship_health = composite_change(
        ("trust", "respect", "recognition", "safety"),
        ("hostility", "antagonism", "distrust", "judgment"),
        start_state,
        end_state,
    )
    engagement = composite_change(
        ("repair", "openness", "compromise", "shared_ownership", "honesty", "patience", "resolve"),
        ("resistance", "denial", "control_urge"),
        start_state,
        end_state,
    )
    risk_keys = [key for key in end_dyn if "risk" in key or "pressure" in key]
    risk = sum(end_dyn[key] - start_dyn.get(key, end_dyn[key]) for key in risk_keys)
    open_change = sum(
        end_dyn[key] - start_dyn.get(key, end_dyn[key])
        for key in end_dyn if "open" in key
    )
    last_text = _public_text({"turns": turns[-2:]}).lower()
    if re.search(r"不再|结束|离开|退出|withdraw|leave", last_text):
        return "withdrawal"
    if relationship_health >= 1.5 and engagement >= 1:
        return "successful_repair"
    if risk <= -3 and relationship_health >= 0:
        return "successful_negotiation"
    if risk <= -2 and relationship_health <= -1.5:
        return "goal_success_with_relationship_damage"
    if relationship_health >= 1 and (risk >= 1 or open_change <= 0):
        return "relationship_preservation_with_partial_goal_failure"
    if relationship_health <= -1.5 or risk >= 4 or open_change <= -2:
        return "gradual_deterioration"
    if abs(relationship_health) <= 0.75 and abs(engagement) <= 0.75 and abs(risk) <= 2 and abs(open_change) <= 1:
        return "stalemate"
    return "strategy_change_during_interaction"


def trajectory_similarity(left, right):
    left_turns = left.get("turns", [])
    right_turns = right.get("turns", [])
    left_text = _public_text(left)
    right_text = _public_text(right)
    text_score = text_similarity(left_text, right_text)
    left_final = flatten_state(left_turns[-1].get("state_after", {})) if left_turns else {}
    right_final = flatten_state(right_turns[-1].get("state_after", {})) if right_turns else {}
    keys = set(left_final) & set(right_final)
    if not keys:
        state_score = 0.0
    else:
        distance = sum(abs(left_final[key] - right_final[key]) for key in keys) / (10 * len(keys))
        state_score = 1.0 - distance
    return round(0.7 * text_score + 0.3 * state_score, 4)


def select_diverse_trajectories(trajectories, audits, minimum=4, maximum=6, threshold=0.88):
    """Greedy quality-first selection with outcome and model-family coverage."""
    by_id = {item["trajectory_id"]: item for item in trajectories}
    eligible = [item for item in audits if item.get("passed") and item["trajectory_id"] in by_id]
    eligible.sort(key=lambda item: item.get("overall_score") or 0.0, reverse=True)
    selected = []
    covered_outcomes = set()
    covered_families = set()
    eligible_rows = []
    for audit in eligible:
        trajectory = by_id[audit["trajectory_id"]]
        eligible_rows.append((audit, trajectory, infer_observed_outcome(trajectory), trajectory.get("policy_provenance", {}).get("model_family", "unknown")))

    def add(row, coverage=False):
        _, trajectory, outcome, family = row
        duplicate = any(trajectory_similarity(trajectory, prior) >= threshold for prior in selected)
        if duplicate and not coverage:
            return False
        selected.append(trajectory)
        covered_outcomes.add(outcome)
        covered_families.add(family)
        return True

    for family in sorted({row[3] for row in eligible_rows}):
        row = next(item for item in eligible_rows if item[3] == family)
        if len(selected) < maximum and row[1] not in selected:
            add(row, coverage=True)
    for outcome in sorted({row[2] for row in eligible_rows}):
        row = next(item for item in eligible_rows if item[2] == outcome)
        if len(selected) < maximum and row[1] not in selected:
            add(row, coverage=True)
    for row in eligible_rows:
        if len(selected) >= maximum:
            break
        if row[1] not in selected:
            add(row)
    if len(selected) < minimum:
        for row in eligible_rows:
            _, trajectory, _, _ = row
            if trajectory not in selected:
                add(row, coverage=True)
            if len(selected) >= minimum:
                break
    eligible_families = {row[3] for row in eligible_rows if row[3] != "unknown"}
    eligible_outcomes = {row[2] for row in eligible_rows}
    diversity_passed = (
        len(covered_families - {"unknown"}) >= min(3, len(eligible_families))
        and len(eligible_families) >= 3
        and len(covered_outcomes) >= 2
        and len(eligible_outcomes) >= 2
    )
    return {
        "passed": minimum <= len(selected) <= maximum and diversity_passed,
        "selected": selected[:maximum],
        "selected_ids": [item["trajectory_id"] for item in selected[:maximum]],
        "observed_outcomes": [infer_observed_outcome(item) for item in selected[:maximum]],
        "model_families": sorted({
            item.get("policy_provenance", {}).get("model_family", "unknown")
            for item in selected[:maximum]
        }),
        "eligible_count": len(eligible),
        "diversity_passed": diversity_passed,
        "eligible_outcome_count": len(eligible_outcomes),
        "eligible_model_family_count": len(eligible_families),
    }


def audit_pool_contract(
    trajectories,
    selected_by_scenario=None,
    api_max_fraction=0.30,
    require_raw_minimum=True,
):
    """Audit the model/source composition and per-scenario sampling contract."""
    selection_supplied = selected_by_scenario is not None
    selected_by_scenario = selected_by_scenario or {}
    total = len(trajectories)
    sources = Counter(
        item.get("policy_provenance", {}).get("source_type", "unknown")
        for item in trajectories
    )
    families = {
        item.get("policy_provenance", {}).get("model_family", "unknown")
        for item in trajectories
        if item.get("policy_provenance", {}).get("source_type") == "local"
    }
    prioritized_capacity_present = any(
        item.get("policy_provenance", {}).get("source_type") == "local"
        and isinstance(item.get("policy_provenance", {}).get("model_parameters_billion"), (int, float))
        and not isinstance(item.get("policy_provenance", {}).get("model_parameters_billion"), bool)
        and 20 <= item["policy_provenance"]["model_parameters_billion"] <= 40
        for item in trajectories
    )
    scenarios = defaultdict(list)
    for item in trajectories:
        scenarios[item.get("scenario_id")].append(item)
    api_fraction = sources["api"] / total if total else 0.0
    checks = {
        "nonempty": total > 0,
        "at_least_three_local_model_families": len(families - {"unknown"}) >= 3,
        "prioritized_20_to_40b_local_model_present": prioritized_capacity_present,
        "api_fraction_at_most_30_percent": api_fraction <= api_max_fraction,
        "each_scenario_has_at_least_12_raw": (
            not require_raw_minimum
            or (bool(scenarios) and all(len(items) >= 12 for items in scenarios.values()))
        ),
        "each_scenario_selects_4_to_6": (
            not selection_supplied
            or (bool(selected_by_scenario) and all(
                4 <= len(items) <= 6 for items in selected_by_scenario.values()
            ))
        ),
        "environment_policy_separated": all(
            item.get("policy_provenance", {}).get("model")
            != item.get("environment_provenance", {}).get("environment", {}).get("model")
            for item in trajectories
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "trajectory_count": total,
        "scenario_count": len(scenarios),
        "source_counts": dict(sources),
        "api_fraction": round(api_fraction, 4),
        "local_model_families": sorted(families),
    }


def content_sha256(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def public_judge_packet(trajectory, scenario=None):
    """Return a state-free reference packet sent to a quality judge."""
    packet = {
        "trajectory_id": trajectory.get("trajectory_id"),
        "scenario_id": trajectory.get("scenario_id"),
        "turns": [
            {
                "turn_id": turn.get("turn_id"),
                "action": turn.get("policy_action", {}).get("text", ""),
                "response": turn.get("environment_response", ""),
                "observable_expression": deepcopy(turn.get("observable_expression", {})),
            }
            for turn in trajectory.get("turns", [])
        ],
    }
    if scenario is not None:
        environment_agent = scenario.get("environment_agent", {})
        packet["scenario_context"] = {
            "mechanism": scenario.get("mechanism", ""),
            "background": scenario.get("background", ""),
            "environment_agent": {
                "persona": deepcopy(environment_agent.get("persona", {})),
                "explicit_goal": environment_agent.get("explicit_goal", ""),
            },
            "evaluated_agent_role": deepcopy(scenario.get("evaluated_agent_role", {})),
        }
    return packet
