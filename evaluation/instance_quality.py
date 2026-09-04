"""Structural quality audit for rollout-derived T1/T2/T3 instances."""

from collections import defaultdict
from copy import deepcopy

from environment.delta_mapper import flatten_state
from evaluation.leakage import find_leaks


def blind_instance_packet(instance):
    """Keep only participant-visible task content and remove all provenance."""
    return {
        "task_type": instance.get("task_type"),
        "language": instance.get("language"),
        "modality": instance.get("modality"),
        "input": deepcopy(instance.get("input", {})),
        "target_spec": deepcopy(instance.get("target_spec", {})),
    }


def _char_bigrams(text):
    normalized = "".join(str(text).split())
    if len(normalized) < 2:
        return {normalized} if normalized else set()
    return {normalized[index:index + 2] for index in range(len(normalized) - 1)}


def _similarity(left, right):
    left_grams = _char_bigrams(left)
    right_grams = _char_bigrams(right)
    union = left_grams | right_grams
    return len(left_grams & right_grams) / len(union) if union else 1.0


def _public_turn_signature(turn):
    return (
        str(turn.get("policy_action", {}).get("text", "")).strip(),
        str(turn.get("environment_response", "")).strip(),
    )


def _history_has_no_exact_repeated_turns(history):
    signatures = [_public_turn_signature(turn) for turn in history]
    return len(signatures) == len(set(signatures))


def _flatten_values(grouped):
    return [
        value
        for values in grouped.values()
        for value in (values.values() if isinstance(values, dict) else [values])
    ]


def audit_trajectory(trajectory):
    turns = trajectory.get("turns", [])
    actions = [str(turn.get("policy_action", {}).get("text", "")).strip() for turn in turns]
    responses = [str(turn.get("environment_response", "")).strip() for turn in turns]
    state_values = [
        value
        for turn in turns
        for value in _flatten_values(turn.get("state_after", {}))
    ]
    total = len(turns)
    action_unique_ratio = len(set(actions)) / total if total else 0.0
    response_unique_ratio = len(set(responses)) / total if total else 0.0
    boundary_fraction = (
        sum(value in (0, 10) for value in state_values) / len(state_values)
        if state_values else 0.0
    )
    checks = {
        "has_at_least_five_turns": total >= 5,
        "actions_nonempty": bool(actions) and all(actions),
        "responses_nonempty": bool(responses) and all(responses),
        "actions_no_exact_repetition": action_unique_ratio == 1.0,
        "responses_no_exact_repetition": response_unique_ratio == 1.0,
        "responses_concise": bool(responses) and max(map(len, responses)) <= 240,
    }
    return {
        "trajectory_id": trajectory.get("trajectory_id"),
        "source_model": trajectory.get("policy_provenance", {}).get("model", "unknown"),
        "turn_count": total,
        "passed": all(checks.values()),
        "checks": checks,
        "diagnostics": {
            "action_unique_ratio": round(action_unique_ratio, 4),
            "response_unique_ratio": round(response_unique_ratio, 4),
            "latent_value_boundary_fraction": round(boundary_fraction, 4),
        },
    }


def _source_ids(instance):
    metadata = instance.get("metadata", {})
    ids = metadata.get("source_trajectory_ids")
    if ids is not None:
        return list(ids)
    source_id = metadata.get("source_trajectory_id")
    return [source_id] if source_id else []


def _model_group(instance, trajectories):
    models = []
    for trajectory_id in _source_ids(instance):
        trajectory = trajectories.get(trajectory_id, {})
        model = trajectory.get("policy_provenance", {}).get("model", "unknown")
        models.append(model)
    return "|".join(sorted(set(models))) if models else "unknown"


def _state_distance(instance, trajectories):
    ids = _source_ids(instance)
    if len(ids) != 2 or any(trajectory_id not in trajectories for trajectory_id in ids):
        return None
    depth = len(instance.get("input", {}).get("history_a", []))
    left, right = (trajectories[trajectory_id] for trajectory_id in ids)
    if depth >= len(left.get("turns", [])) or depth >= len(right.get("turns", [])):
        return None
    left_state = flatten_state(left["turns"][depth]["state_before"])
    right_state = flatten_state(right["turns"][depth]["state_before"])
    shared = set(left_state) & set(right_state)
    return sum(abs(left_state[key] - right_state[key]) for key in shared)


def _branch_groups(interventions):
    groups = defaultdict(list)
    for branch in interventions:
        groups[(
            branch.get("source_trajectory_id"),
            branch.get("checkpoint_turn_id"),
        )].append(branch)
    return groups


def _common_checks(instance):
    return {
        "leakage_free": not find_leaks(instance),
        "ground_truth_not_fabricated": instance.get("ground_truth") is None,
        "human_label_pending": instance.get("label_status") == "pending_human_annotation",
    }


def _audit_t1(instance):
    data = instance.get("input", {})
    target = data.get("target_character_id", "")
    history = data.get("history", [])
    checkpoint = data.get("current_checkpoint", {})
    checks = {
        **_common_checks(instance),
        "environment_character_targeted": target.endswith("_ENVIRONMENT_AGENT"),
        "target_states_present": bool(instance.get("target_spec", {}).get("target_state_ids")),
        "observable_history_present": bool(history),
        "checkpoint_response_present": bool(str(checkpoint.get("current_response", "")).strip()),
        "history_is_flat": all("history" not in turn.get("observation", {}) for turn in history),
        "history_has_no_exact_repeated_turns": _history_has_no_exact_repeated_turns(history),
    }
    return checks, {}


def _response_addresses_target_itself(response, target_character):
    response = str(response).lstrip(" \t\r\n\"“")
    name = str(target_character.get("name", "")).strip()
    role = str(target_character.get("role", "")).strip()
    prefixes = {value for value in (name, role) if value}
    for title in ("总监", "经理", "主任", "老师", "医生", "教授", "老板", "院长", "队长", "校长"):
        if name and title in role:
            prefixes.add(name[0] + title)
    return any(response.startswith(prefix) for prefix in prefixes)


def _audit_t2(instance, trajectories):
    data = instance.get("input", {})
    target = instance.get("target_spec", {}).get("target_character_id", "")
    history_a = data.get("history_a", [])
    history_b = data.get("history_b", [])
    shared = data.get("shared_current_observation", {})
    shared_response = str(shared.get("current_response", "")).strip()
    target_character = data.get("target_character", {})
    distance = _state_distance(instance, trajectories)
    checks = {
        **_common_checks(instance),
        "environment_character_targeted": target.endswith("_ENVIRONMENT_AGENT"),
        "target_states_present": bool(instance.get("target_spec", {}).get("target_state_ids")),
        "histories_are_distinct": history_a != history_b,
        "history_depth_is_matched": bool(history_a) and len(history_a) == len(history_b),
        "histories_have_no_exact_repeated_turns": (
            _history_has_no_exact_repeated_turns(history_a)
            and _history_has_no_exact_repeated_turns(history_b)
        ),
        "shared_observation_response_present": bool(shared_response),
        "shared_response_does_not_address_target_itself": not _response_addresses_target_itself(
            shared_response,
            target_character,
        ),
        "shared_observation_marked_injected": instance.get("metadata", {}).get(
            "shared_observation_injected"
        ) is True,
        "compatibility_requires_human_review": instance.get("metadata", {}).get(
            "compatibility_status"
        ) == "pending_human_validation",
        "private_state_is_divergent": distance is not None and distance > 0,
    }
    return checks, {"private_state_distance": distance}


def _audit_t3(instance, branch_groups):
    data = instance.get("input", {})
    target = instance.get("target_spec", {}).get("target_character_id", "")
    actions = [item.get("text", "").strip() for item in data.get("candidate_actions", [])]
    similarities = [
        _similarity(actions[left], actions[right])
        for left in range(len(actions))
        for right in range(left + 1, len(actions))
    ]
    metadata = instance.get("metadata", {})
    branches = branch_groups.get((
        metadata.get("source_trajectory_id"),
        metadata.get("checkpoint_turn_id"),
    ), [])
    branch_actions = [item.get("candidate_action", {}).get("text", "").strip() for item in branches]
    states_before = [item.get("state_before") for item in branches]
    dynamics_before = [item.get("dynamics_before") for item in branches]
    immediate = [flatten_state(item.get("state_after_immediate", {})) for item in branches]
    delayed = [flatten_state(item.get("state_after_delayed", {})) for item in branches]
    expected_actions = set(actions)
    branch_complete = len(branches) == len(actions) and set(branch_actions) == expected_actions
    shared_start = bool(branches) and len({repr(item) for item in states_before}) == 1 and len(
        {repr(item) for item in dynamics_before}
    ) == 1
    immediate_divergent = len({repr(item) for item in immediate}) > 1
    delayed_divergent = len({repr(item) for item in delayed}) > 1
    checks = {
        **_common_checks(instance),
        "environment_character_targeted": target.endswith("_ENVIRONMENT_AGENT"),
        "target_states_present": bool(instance.get("target_spec", {}).get("target_state_ids")),
        "candidate_count_valid": 2 <= len(actions) <= 4,
        "candidate_actions_unique": len(actions) == len(set(actions)) and all(actions),
        "candidate_actions_lexically_distinct": not similarities or max(similarities) < 0.92,
        "branch_set_complete": branch_complete,
        "branches_share_private_start": shared_start,
        "branches_show_some_state_divergence": immediate_divergent or delayed_divergent,
    }
    return checks, {
        "branch_count": len(branches),
        "max_candidate_similarity": max(similarities) if similarities else 0.0,
        "immediate_divergent": immediate_divergent,
        "delayed_divergent": delayed_divergent,
    }


def audit_instance(instance, trajectories=None, branch_groups=None):
    trajectories = trajectories or {}
    branch_groups = branch_groups or {}
    task_type = instance.get("task_type", "unknown")
    if task_type == "T1_state_tracking":
        checks, diagnostics = _audit_t1(instance)
    elif task_type == "T2_history_sensitive_merge":
        checks, diagnostics = _audit_t2(instance, trajectories)
    elif task_type == "T3_counterfactual_choice_effect":
        checks, diagnostics = _audit_t3(instance, branch_groups)
    else:
        checks, diagnostics = {**_common_checks(instance), "known_task_type": False}, {}
    score = sum(checks.values()) / len(checks) if checks else 0.0
    return {
        "instance_id": instance.get("instance_id"),
        "scenario_id": instance.get("story_id"),
        "task_type": task_type,
        "source_model_group": _model_group(instance, trajectories),
        "structural_score": round(score, 4),
        "passed": all(checks.values()),
        "checks": checks,
        "diagnostics": diagnostics,
        "semantic_review_status": "pending_blind_human_or_independent_model_review",
    }


def build_instance_quality_report(instances, trajectories=None, interventions=None):
    trajectories = trajectories or []
    trajectory_index = {
        item["trajectory_id"]: item for item in trajectories
    }
    trajectory_audits = [audit_trajectory(item) for item in trajectories]
    branch_groups = _branch_groups(interventions or [])
    audited = [
        audit_instance(instance, trajectory_index, branch_groups)
        for instance in instances
    ]
    grouped = defaultdict(list)
    for item in audited:
        grouped[(item["source_model_group"], item["task_type"])].append(item)
    by_model = {}
    for (model, task), items in sorted(grouped.items()):
        by_model.setdefault(model, {})[task] = {
            "count": len(items),
            "passed": sum(item["passed"] for item in items),
            "mean_structural_score": round(
                sum(item["structural_score"] for item in items) / len(items),
                4,
            ),
        }
    scenario_groups = defaultdict(list)
    for item in audited:
        scenario_groups[(item["scenario_id"], item["task_type"])].append(item)
    by_scenario = {}
    for (scenario_id, task), items in sorted(scenario_groups.items()):
        by_scenario.setdefault(scenario_id, {})[task] = {
            "count": len(items),
            "passed": sum(item["passed"] for item in items),
            "mean_structural_score": round(
                sum(item["structural_score"] for item in items) / len(items),
                4,
            ),
        }
    trajectory_by_scenario = {}
    for item, audit in zip(trajectories, trajectory_audits):
        scenario_id = item.get("scenario_id", "unknown")
        entry = trajectory_by_scenario.setdefault(scenario_id, {"count": 0, "passed": 0})
        entry["count"] += 1
        entry["passed"] += int(audit["passed"])
    return {
        "format": "socialflux_instance_quality_v1",
        "instance_count": len(audited),
        "structurally_passed": sum(item["passed"] for item in audited),
        "mean_structural_score": round(
            sum(item["structural_score"] for item in audited) / len(audited),
            4,
        ) if audited else 0.0,
        "by_source_model": by_model,
        "by_scenario": by_scenario,
        "trajectory_quality": {
            "trajectory_count": len(trajectory_audits),
            "passed": sum(item["passed"] for item in trajectory_audits),
            "by_scenario": trajectory_by_scenario,
            "trajectories": trajectory_audits,
        },
        "instances": audited,
        "interpretation": {
            "structural_score_scope": "contract, leakage, evidence shape, and branch completeness only",
            "not_measured_automatically": [
                "social plausibility",
                "shared-observation naturalness",
                "candidate-action strategic meaningfulness",
                "human answerability",
                "label validity",
            ],
            "comparison_status": "requires matched-model rollouts and blind semantic review",
        },
    }
