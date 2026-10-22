"""Structural quality audit for rollout-derived T1/T2/T3 instances."""

from collections import defaultdict
from copy import deepcopy

from environment.appraisal import appraisal_preserves_action_owner
from environment.delta_mapper import flatten_state
from environment.interaction_ledger import record_evaluated_action
from evaluation.leakage import find_leaks
from providers.text import (
    asserts_ungrounded_institutional_procedure,
    asserts_ungrounded_performance_amount,
    asserts_ungrounded_remaining_amount,
    addresses_speaker_as_other,
    avoids_unsupported_offscreen_claim,
    bounces_latest_stance_request,
    claims_other_speaker_commitment,
    claims_pending_commitment_completed,
    collapses_multiple_facets_early,
    confirms_ungrounded_numeric_detail,
    confirms_unobserved_completion,
    contradicts_explicit_installment_total,
    contradicts_pending_own_commitment,
    copies_goal_thread_label,
    follows_dialogue_format,
    introduces_unprompted_coordination_actor,
    introduces_unprompted_legal_escalation,
    introduces_unrequested_artifact,
    evades_latest_obligation,
    lacks_natural_final_closure,
    overloads_consequential_terms,
    opens_followup_on_saturated_focus,
    mirrors_latest_speaker_move,
    prematurely_reports_future_commitment_completion,
    renews_pending_commitment_without_change,
    template_loop_signatures,
    violates_environment_counterparty_role,
    violates_role_specific_action,
    text_similarity,
    current_repayment_commitment_status,
    rewrites_absent_commitment_as_nonperformance,
    suspends_existing_obligation,
    upgrades_tentative_to_agreement,
)


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


def _append_public_transition_events(observed, turn):
    transition = turn.get("segment_transition_after") or {}
    event_texts = [
        str(event.get("text", ""))
        for event in transition.get("public_events", [])
        if event.get("public", True) and str(event.get("text", "")).strip()
    ]
    return observed + (" " + " ".join(event_texts) if event_texts else "")


def _performance_amounts_are_grounded(trajectory):
    context = trajectory.get("public_scenario_context", {})
    observed = " ".join((
        str(context.get("background", "")),
        str(context.get("public_situation", {})),
    ))
    for turn in trajectory.get("turns", []):
        action = str(turn.get("policy_action", {}).get("text", ""))
        if asserts_ungrounded_performance_amount(action, observed):
            return False
        observed += " " + action
        response = str(turn.get("environment_response", ""))
        if asserts_ungrounded_performance_amount(response, observed):
            return False
        observed = _append_public_transition_events(observed + " " + response, turn)
    return True


def _remaining_balances_are_grounded(trajectory):
    context = trajectory.get("public_scenario_context", {})
    observed = " ".join((
        str(context.get("background", "")),
        str(context.get("public_situation", {})),
    ))
    for turn in trajectory.get("turns", []):
        action = str(turn.get("policy_action", {}).get("text", ""))
        if asserts_ungrounded_remaining_amount(action, observed):
            return False
        observed += " " + action
        response = str(turn.get("environment_response", ""))
        if asserts_ungrounded_remaining_amount(response, observed):
            return False
        observed = _append_public_transition_events(observed + " " + response, turn)
    return True


def _numeric_confirmations_are_grounded(trajectory):
    context = trajectory.get("public_scenario_context", {})
    observed = " ".join((
        str(context.get("background", "")),
        str(context.get("public_situation", {})),
    ))
    for turn in trajectory.get("turns", []):
        action = str(turn.get("policy_action", {}).get("text", ""))
        if confirms_ungrounded_numeric_detail(action, observed):
            return False
        observed += " " + action
        response = str(turn.get("environment_response", ""))
        if confirms_ungrounded_numeric_detail(response, observed):
            return False
        observed = _append_public_transition_events(observed + " " + response, turn)
    return True


def _artifacts_are_observably_grounded(trajectory):
    context = trajectory.get("public_scenario_context", {})
    observed = " ".join((
        str(context.get("background", "")),
        str(context.get("public_situation", {})),
    ))
    for turn in trajectory.get("turns", []):
        action = str(turn.get("policy_action", {}).get("text", ""))
        if introduces_unrequested_artifact(action, observed):
            return False
        observed += " " + action
        response = str(turn.get("environment_response", ""))
        if introduces_unrequested_artifact(response, observed):
            return False
        observed = _append_public_transition_events(observed + " " + response, turn)
    return True


def _institutional_procedures_are_grounded(trajectory):
    public_context = trajectory.get("public_scenario_context", {})
    observed = " ".join((
        str(public_context.get("background", "")),
        str(public_context.get("public_situation", {})),
    ))
    for turn in trajectory.get("turns", []):
        action = str(turn.get("policy_action", {}).get("text", ""))
        if asserts_ungrounded_institutional_procedure(action, observed):
            return False
        observed += " " + action
        response = str(turn.get("environment_response", ""))
        if asserts_ungrounded_institutional_procedure(response, observed):
            return False
        observed = _append_public_transition_events(observed + " " + response, turn)
    return True

def _coordination_actors_are_grounded(trajectory):
    context = trajectory.get("public_scenario_context", {})
    observed = " ".join((
        str(context.get("background", "")),
        str(context.get("public_situation", {})),
    ))
    for turn in trajectory.get("turns", []):
        action = str(turn.get("policy_action", {}).get("text", ""))
        if introduces_unprompted_coordination_actor(action, observed):
            return False
        observed += " " + action
        response = str(turn.get("environment_response", ""))
        if introduces_unprompted_coordination_actor(response, observed):
            return False
        observed = _append_public_transition_events(observed + " " + response, turn)
    return True


def _legal_escalations_are_grounded(trajectory):
    context = trajectory.get("public_scenario_context", {})
    observed = " ".join((
        str(context.get("background", "")),
        str(context.get("public_situation", {})),
    ))
    for turn in trajectory.get("turns", []):
        action = str(turn.get("policy_action", {}).get("text", ""))
        if introduces_unprompted_legal_escalation(action, observed):
            return False
        observed += " " + action
        response = str(turn.get("environment_response", ""))
        if introduces_unprompted_legal_escalation(response, observed):
            return False
        observed = _append_public_transition_events(observed + " " + response, turn)
    return True


def _installment_arithmetic_is_consistent(trajectory):
    latest_response = ""
    for turn in trajectory.get("turns", []):
        action = str(turn.get("policy_action", {}).get("text", ""))
        response = str(turn.get("environment_response", ""))
        if contradicts_explicit_installment_total(action, latest_response):
            return False
        if contradicts_explicit_installment_total(response, action):
            return False
        latest_response = response
    return True


def _pending_commitments_are_consistent(trajectory):
    latest_response = ""
    for turn in trajectory.get("turns", []):
        ledger = deepcopy(turn.get("interaction_ledger_before", {}))
        for key in (
            "established_facts", "goal_threads", "active_proposals",
            "commitments", "unresolved_threads", "recent_moves",
        ):
            ledger.setdefault(key, [])
        ledger.setdefault("latest_obligation", None)
        ledger.setdefault("progress", {})
        action_obj = turn.get("policy_action", {})
        action = str(action_obj.get("text", ""))
        response = str(turn.get("environment_response", ""))
        if claims_pending_commitment_completed(action, ledger):
            return False
        if claims_other_speaker_commitment(
            action, ledger, "evaluated_agent"
        ):
            return False
        if prematurely_reports_future_commitment_completion(
            action, ledger, "evaluated_agent"
        ):
            return False
        if contradicts_pending_own_commitment(
            action, ledger, "evaluated_agent"
        ):
            return False
        response_ledger = record_evaluated_action(
            ledger,
            turn_id=int(str(turn.get("turn_id", "0")).lstrip("t") or 0),
            action=action_obj,
            appraisal=turn.get("appraisal", {}),
        )
        if claims_pending_commitment_completed(response, response_ledger):
            return False
        if claims_other_speaker_commitment(
            response, response_ledger, "environment_agent"
        ):
            return False
        if prematurely_reports_future_commitment_completion(
            response, response_ledger, "environment_agent"
        ):
            return False
        if contradicts_pending_own_commitment(
            response, response_ledger, "environment_agent"
        ):
            return False
        latest_response = response
    return True

def _saturated_followups_are_absent(trajectory):
    for turn in trajectory.get("turns", []):
        ledger = deepcopy(turn.get("interaction_ledger_before", {}))
        for key in (
            "established_facts", "goal_threads", "active_proposals",
            "commitments", "unresolved_threads", "recent_moves",
        ):
            ledger.setdefault(key, [])
        ledger.setdefault("latest_obligation", None)
        ledger.setdefault("progress", {})
        action_obj = turn.get("policy_action", {})
        action = str(action_obj.get("text", ""))
        if opens_followup_on_saturated_focus(action, ledger):
            return False
        response_ledger = record_evaluated_action(
            ledger,
            turn_id=int(str(turn.get("turn_id", "0")).lstrip("t") or 0),
            action=action_obj,
            appraisal=turn.get("appraisal", {}),
        )
        if opens_followup_on_saturated_focus(
            turn.get("environment_response", ""), response_ledger
        ):
            return False
    return True


def _actions_address_latest_obligation(trajectory):
    latest_response = ""
    for turn in trajectory.get("turns", []):
        action = str(turn.get("policy_action", {}).get("text", ""))
        if evades_latest_obligation(action, latest_response, "other"):
            return False
        latest_response = str(turn.get("environment_response", ""))
    return True


def _commitment_history_is_consistent(trajectory):
    """Reject only explicit rewrites of the observable commitment record."""
    absent = "没有形成可核验的还款承诺"
    for turn in trajectory.get("turns", []):
        observation = turn.get("observation", {})
        status = current_repayment_commitment_status(
            turn.get("interaction_ledger_before", {}),
            observation.get("longitudinal_context", {}).get("public_timeline", []),
            observation.get("current_response", ""),
        )
        if status != "no_verifiable_commitment":
            continue
        action = str(turn.get("policy_action", {}).get("text", ""))
        response = str(turn.get("environment_response", ""))
        if rewrites_absent_commitment_as_nonperformance(action, absent):
            return False
        if rewrites_absent_commitment_as_nonperformance(response, absent):
            return False
    return True


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
    action_similarities = [
        text_similarity(actions[left], actions[right])
        for left in range(total)
        for right in range(left + 1, total)
    ]
    response_similarities = [
        text_similarity(responses[left], responses[right])
        for left in range(total)
        for right in range(left + 1, total)
    ]
    environment_speaker = (
        turns[0].get("observation", {}).get("target_character", {})
        if turns else {}
    )
    boundary_fraction = (
        sum(value in (0, 10) for value in state_values) / len(state_values)
        if state_values else 0.0
    )
    public_context = trajectory.get("public_scenario_context", {})
    evaluated_role = public_context.get("evaluated_agent_role", {})
    checks = {
        "has_at_least_five_turns": total >= 5,
        "actions_nonempty": bool(actions) and all(actions),
        "responses_nonempty": bool(responses) and all(responses),
        "actions_no_exact_repetition": action_unique_ratio == 1.0,
        "responses_no_exact_repetition": response_unique_ratio == 1.0,
        "actions_no_near_repetition": not action_similarities or max(action_similarities) < 0.85,
        "responses_no_near_repetition": not response_similarities or max(response_similarities) < 0.85,
        "actions_no_template_loop": not template_loop_signatures(actions),
        "responses_no_template_loop": not template_loop_signatures(responses),
        "responses_do_not_address_environment_speaker": all(
            not addresses_speaker_as_other(value, environment_speaker)
            for value in responses
        ),
        "actions_avoid_unsupported_offscreen_claims": all(
            avoids_unsupported_offscreen_claim(value) for value in actions
        ),
        "responses_avoid_unsupported_offscreen_claims": all(
            avoids_unsupported_offscreen_claim(value, environment=True)
            for value in responses
        ),
        "responses_do_not_confirm_unobserved_completion": all(
            not confirms_unobserved_completion(response, action)
            for action, response in zip(actions, responses)
        ),
        "turns_preserve_speaker_action_ownership": all(
            not mirrors_latest_speaker_move(response, action)
            for action, response in zip(actions, responses)
        ),
        "turns_preserve_existing_obligations": all(
            not suspends_existing_obligation(value)
            for value in actions + responses
        ),
        "turns_preserve_commitment_record": _commitment_history_is_consistent(
            trajectory
        ),
        "turns_preserve_proposal_strength": all(
            not upgrades_tentative_to_agreement(
                action, turn.get("observation", {}).get("current_response", "")
            )
            and not upgrades_tentative_to_agreement(response, action)
            for action, response, turn in zip(actions, responses, turns)
        ),
        "turns_do_not_bounce_stance_requests": all(
            not bounces_latest_stance_request(response, action)
            and (
                index == 0
                or not bounces_latest_stance_request(action, responses[index - 1])
            )
            for index, (action, response) in enumerate(zip(actions, responses))
        ),
        "actions_respect_public_role": all(
            not violates_role_specific_action(action, evaluated_role)
            for action in actions
        ),
        "responses_respect_counterparty_role": all(
            not violates_environment_counterparty_role(response, evaluated_role)
            for response in responses
        ),
        "numeric_confirmations_are_grounded": _numeric_confirmations_are_grounded(
            trajectory
        ),
        "performance_amounts_are_grounded": _performance_amounts_are_grounded(
            trajectory
        ),
        "remaining_balances_are_grounded": _remaining_balances_are_grounded(
            trajectory
        ),
        "installment_arithmetic_is_consistent": _installment_arithmetic_is_consistent(
            trajectory
        ),
        "pending_commitments_are_consistent": _pending_commitments_are_consistent(
            trajectory
        ),
        "artifact_workflows_are_grounded": _artifacts_are_observably_grounded(
            trajectory
        ),
        "institutional_procedures_are_grounded": _institutional_procedures_are_grounded(
            trajectory
        ),
        "coordination_actors_are_grounded": _coordination_actors_are_grounded(
            trajectory
        ),
        "legal_escalations_are_grounded": _legal_escalations_are_grounded(
            trajectory
        ),
        "turns_do_not_copy_goal_thread_labels": all(
            not copies_goal_thread_label(action, turn.get("interaction_ledger_before", {}))
            and not copies_goal_thread_label(response, turn.get("interaction_ledger_before", {}))
            for action, response, turn in zip(actions, responses, turns)
        ),
        "turns_do_not_overload_consequential_terms": all(
            not overloads_consequential_terms(action, index)
            and not overloads_consequential_terms(response, index)
            for index, (action, response) in enumerate(
                zip(actions, responses), start=1
            )
        ),
        "responses_address_latest_obligation": all(
            not evades_latest_obligation(
                response,
                action,
                turn.get("appraisal", {}).get("social_act", "other"),
            )
            for action, response, turn in zip(actions, responses, turns)
        ),
        "actions_address_latest_obligation": _actions_address_latest_obligation(
            trajectory
        ),
        "turns_do_not_open_saturated_followups": _saturated_followups_are_absent(
            trajectory
        ),
        "early_turns_do_not_collapse_multiple_facets": all(
            not collapses_multiple_facets_early(action, index)
            and not collapses_multiple_facets_early(response, index)
            for index, (action, response) in enumerate(
                zip(actions, responses), start=1
            )
        ),
        "appraisals_preserve_action_owner": all(
            appraisal_preserves_action_owner(
                turn.get("appraisal", {}), public_context.get("environment_role", {})
            )
            for turn in turns
        ),
        "fixed_horizon_closes_naturally": (
            total != 20
            or (
                not lacks_natural_final_closure(actions[-1], 20)
                and not lacks_natural_final_closure(responses[-1], 20)
            )
        ),
        "actions_follow_dialogue_format": all(map(follows_dialogue_format, actions)),
        "responses_follow_dialogue_format": all(map(follows_dialogue_format, responses)),
        "responses_concise": bool(responses) and max(map(len, responses)) <= 240,
    }
    hard_check_names = (
        "has_at_least_five_turns",
        "actions_nonempty",
        "responses_nonempty",
        "responses_do_not_address_environment_speaker",
        "responses_do_not_confirm_unobserved_completion",
        "turns_preserve_speaker_action_ownership",
        "turns_preserve_existing_obligations",
        "turns_preserve_commitment_record",
        "turns_preserve_proposal_strength",
        "actions_respect_public_role",
        "responses_respect_counterparty_role",
        "performance_amounts_are_grounded",
        "remaining_balances_are_grounded",
        "installment_arithmetic_is_consistent",
        "pending_commitments_are_consistent",
        "appraisals_preserve_action_owner",
        "actions_follow_dialogue_format",
        "responses_follow_dialogue_format",
        "responses_concise",
    )
    diagnostic_check_names = tuple(
        key for key in checks if key not in hard_check_names
    )
    return {
        "trajectory_id": trajectory.get("trajectory_id"),
        "source_model": trajectory.get("policy_provenance", {}).get("model", "unknown"),
        "turn_count": total,
        "passed": all(checks[key] for key in hard_check_names),
        "checks": checks,
        "check_groups": {
            "hard": list(hard_check_names),
            "diagnostic": list(diagnostic_check_names),
        },
        "diagnostics": {
            "action_unique_ratio": round(action_unique_ratio, 4),
            "response_unique_ratio": round(response_unique_ratio, 4),
            "max_action_similarity": round(max(action_similarities), 4) if action_similarities else 0.0,
            "max_response_similarity": round(max(response_similarities), 4) if response_similarities else 0.0,
            "action_template_loops": template_loop_signatures(actions),
            "response_template_loops": template_loop_signatures(responses),
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
