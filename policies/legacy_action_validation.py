"""Historical lexical validation for pre-v21 evaluated-agent prompts.

ModelPolicy owns prompt construction and provider orchestration. This module
keeps old experiments reproducible. Active v21 generation does not use these
lexical rules.
"""

import re

from environment.dialogue_support import (
    contains_private_simulator_language,
    focus_retry_guidance,
)
from providers.text import (
    _candidate_advances_available_thread,
    asserts_ungrounded_institutional_procedure,
    asserts_ungrounded_performance_amount,
    asserts_ungrounded_remaining_amount,
    bounces_latest_stance_request,
    claims_other_speaker_commitment,
    claims_pending_commitment_completed,
    current_repayment_commitment_status,
    collapses_multiple_facets_early,
    confirms_ungrounded_numeric_detail,
    contradicts_explicit_installment_total,
    contradicts_pending_own_commitment,
    copies_goal_thread_label,
    copies_latest_other_utterance,
    directly_answers_latest_proposal,
    evades_latest_obligation,
    follows_dialogue_format,
    follows_policy_action_format,
    follows_latest_invited_scope,
    goal_thread_constraints,
    introduces_unprompted_coordination_actor,
    introduces_unprompted_legal_escalation,
    introduces_unrequested_artifact,
    lacks_natural_final_closure,
    overloads_consequential_terms,
    opens_followup_on_saturated_focus,
    opens_new_repayment_commitment,
    prematurely_reports_future_commitment_completion,
    mirrors_latest_speaker_move,
    normalize_text,
    opens_future_cycle_on_final_turn,
    premature_closure_with_untouched_goals,
    renews_pending_commitment_without_change,
    repeats_future_meeting_deferral,
    repeats_exactly_without_substantive_public_event,
    repeats_own_utterance_without_new_challenge,
    repeats_saturated_goal_focus,
    repeats_stalled_focus,
    rewrites_absent_commitment_as_nonperformance,
    suspends_existing_obligation,
    upgrades_tentative_to_agreement,
    violates_role_specific_action,
)


def validate_candidate_for_profile(policy, candidate, observation):
    if (
        policy.prompt_id == "task_t4_action_v21"
        and policy.validation_profile == "hard_only"
    ):
        if not follows_dialogue_format(candidate):
            return False, "malformed direct dialogue"
        if contains_private_simulator_language(candidate):
            return False, "private simulator language leakage"
        latest = observation.get("current_response", "")
        if normalize_text(candidate) == normalize_text(latest):
            return False, "exact echo of the latest other-speaker utterance"
        return True, ""
    if policy.validation_profile == "full":
        return policy._validate_candidate(
            candidate,
            observation,
            enforce_fixed_horizon=policy.horizon_mode == "fixed_20",
        )
    return _validate_legacy_hard_only(candidate, observation)


def _validate_legacy_hard_only(candidate, observation):
        ledger = observation.get("conversation_progress", {})
        latest = observation.get("current_response", "")
        record_status = current_repayment_commitment_status(
            ledger,
            observation.get("longitudinal_context", {}).get("public_timeline", []),
            latest,
        )
        if upgrades_tentative_to_agreement(candidate, latest):
            return False, "tentative move was upgraded to an agreement"
        if rewrites_absent_commitment_as_nonperformance(
            candidate,
            "没有形成可核验的还款承诺"
            if record_status == "no_verifiable_commitment" else latest,
        ):
            return False, "absence of a commitment was rewritten as nonperformance"
        if suspends_existing_obligation(candidate):
            return False, "existing obligation was suspended without grounding"
        if not follows_dialogue_format(candidate):
            return False, "malformed direct dialogue"
        if contains_private_simulator_language(candidate):
            return False, "private simulator language leakage"
        if copies_latest_other_utterance(candidate, latest):
            return False, "verbatim echo of the latest environment utterance"
        if mirrors_latest_speaker_move(candidate, latest):
            return False, "latest-speaker action ownership reversal"
        segment = observation.get("longitudinal_context", {}).get("segment", {})
        if (
            segment.get("forbid_new_repayment_commitment")
            and opens_new_repayment_commitment(candidate)
        ):
            return False, "current fragment forbids a new repayment commitment"
        observable = " ".join([
            str(observation.get("background", "")),
            str(observation.get("public_situation", {})),
            *(str(item.get("text", "")) for item in observation.get("history", [])),
            str(latest),
        ])
        if asserts_ungrounded_performance_amount(candidate, observable):
            return False, "precise completed-payment amount lacks a public record"
        if asserts_ungrounded_remaining_amount(candidate, observable):
            return False, "precise remaining balance lacks a public record"
        if contradicts_explicit_installment_total(candidate, latest):
            return False, "candidate contradicts the explicit installment total"
        if claims_pending_commitment_completed(candidate, ledger):
            return False, "pending commitment was described as completed or settled"
        public_record_text = " ".join(
            str(item.get("text", ""))
            for item in observation.get("longitudinal_context", {}).get(
                "public_timeline", []
            )
            if item.get("public", True)
        )
        if prematurely_reports_future_commitment_completion(
            candidate, ledger, "evaluated_agent", public_record_text
        ):
            return False, "future-timed commitment was reported complete without evidence"
        if claims_other_speaker_commitment(candidate, ledger, "evaluated_agent"):
            return False, "pending commitment belongs to environment_agent"
        if contradicts_pending_own_commitment(candidate, ledger, "evaluated_agent"):
            return False, "unsupported reversal of evaluated_agent pending commitment"
        if violates_role_specific_action(candidate, observation.get("role", {})):
            return False, "candidate action contradicts the public evaluated role"
        return True, ""


def retry_guidance(observation):
        ledger = observation.get("conversation_progress", {})
        parts = []
        latest_response = observation.get("current_response", "") or next((
            str(item.get("text", ""))
            for item in reversed(observation.get("history", []))
            if item.get("role") == "environment_agent"
        ), "")
        latest_open_proposal = next((
            item for item in reversed(ledger.get("active_proposals", []))
            if item.get("speaker") == "environment_agent"
            and item.get("status") in {"open", "tentative"}
        ), None)
        if (
            (ledger.get("latest_obligation") or {}).get("owner") == "evaluated_agent"
            and not latest_open_proposal
        ):
            parts.append(
                "You owe a direct answer to the newest request. Begin by explicitly "
                "accepting, refusing, or saying you cannot confirm it. Do not return "
                "the same feasibility/acceptance question to the other speaker."
            )
        if (
            (ledger.get("latest_obligation") or {}).get("owner") == "evaluated_agent"
            and latest_open_proposal
        ):
            parts.append(
                "The ledger says you owe a disposition of this open proposal now: "
                + repr(latest_open_proposal.get("text", ""))
                + ". Do not ask the speaker to repeat or clarify the same proposal. "
                "Explicitly accept it, refuse it, identify it as tentative/insufficient, "
                "give one grounded counterposition, or preserve the disagreement and pause. "
                "A pure question or topic switch does not discharge this obligation."
            )
        if re.search(
            r"(?:我建议|我提议|可以|可考虑|不如|要不要|是否愿意|是否可以|你若同意)",
            latest_response,
        ):
            parts.append(
                "The newest response contains a proposal. Choose one offered option or "
                "refuse it now. If that response explicitly invited a second existing "
                "facet, you may add one short question only about that invited facet; "
                "otherwise add no percentage, condition, question, future promise, "
                "document step, or substitute proposal."
            )
        own_pending = [
            item for item in ledger.get("commitments", [])
            if item.get("speaker") == "evaluated_agent"
            and item.get("status") == "pending"
        ]
        if own_pending:
            parts.append(
                "Your own pending promise is already preserved in the ledger. "
                "If the newest response explicitly asks you to supply that promised "
                "content now, either provide only facts already public in the dialogue "
                "or plainly admit that you cannot substantiate it now. Otherwise do "
                "not mention, reassure, renew, or withdraw the promise; omit its future "
                "action wording. 已有承诺不需要重述；若对方正要求兑现，只能基于"
                "公开事实当场回答，无法核实就直接承认，禁止换议题或假装已完成。"
            )
        parts.extend(focus_retry_guidance(ledger, goal_thread_constraints))
        return " ".join(parts)


def validate_candidate(
        candidate, observation, enforce_fixed_horizon=True
    ):
        ledger = observation.get("conversation_progress", {})
        turn_number = 1 + sum(
            item.get("role") == "evaluated_agent"
            for item in observation.get("history", [])
        )
        if collapses_multiple_facets_early(candidate, turn_number):
            return False, "early turn collapses multiple public goal facets at once"
        if overloads_consequential_terms(candidate, turn_number):
            return False, "candidate introduces too many consequential terms at once"
        if copies_goal_thread_label(candidate, ledger):
            return False, "candidate copied an internal public-goal label"
        if not follows_policy_action_format(
            candidate, allow_reported_claims=not enforce_fixed_horizon,
        ):
            return False, "policy format or unsupported off-screen claim"
        latest = observation.get("current_response", "")
        if copies_latest_other_utterance(candidate, latest):
            return False, "verbatim echo of the latest other-speaker utterance"
        if mirrors_latest_speaker_move(candidate, latest):
            return False, "latest-speaker action ownership reversal"
        segment = observation.get("longitudinal_context", {}).get(
            "segment", {}
        )
        if (
            segment.get("forbid_new_repayment_commitment")
            and opens_new_repayment_commitment(candidate)
        ):
            return False, "current fragment forbids a new repayment commitment"
        history = observation.get("history", [])
        latest = observation.get("current_response", "")
        if repeats_exactly_without_substantive_public_event(
            candidate, history, "evaluated_agent", latest,
        ):
            return False, "exact same-speaker refrain without a substantive public event"
        segment_turn = segment.get("segment_turn_id", 0)
        if repeats_own_utterance_without_new_challenge(
            candidate, history, "evaluated_agent", segment_turn, latest,
        ):
            return False, "exact same-speaker loop inside the current fragment"
        observable_balance = " ".join([
            str(observation.get("background", "")),
            str(observation.get("public_situation", {})),
            *(str(item.get("text", "")) for item in observation.get("history", [])),
            str(observation.get("current_response", "")),
        ])
        if asserts_ungrounded_performance_amount(candidate, observable_balance):
            return False, "precise completed-payment amount lacks a public record"
        if asserts_ungrounded_remaining_amount(candidate, observable_balance):
            return False, "precise remaining balance lacks a public record"
        if contradicts_explicit_installment_total(
            candidate, observation.get("current_response", "")
        ):
            return False, "candidate contradicts the explicit installment total"
        if upgrades_tentative_to_agreement(
            candidate, observation.get("current_response", "")
        ):
            return False, "tentative move was upgraded to an agreement"
        record_status = current_repayment_commitment_status(
            ledger,
            observation.get("longitudinal_context", {}).get("public_timeline", []),
            latest,
        )
        if rewrites_absent_commitment_as_nonperformance(
            candidate,
            "没有形成可核验的还款承诺" if record_status == "no_verifiable_commitment" else latest,
        ):
            return False, "absence of a commitment was rewritten as nonperformance"
        if suspends_existing_obligation(candidate):
            return False, "existing obligation was suspended without grounding"
        if bounces_latest_stance_request(
            candidate, observation.get("current_response", "")
        ):
            return False, "candidate bounces the latest stance request back to its asker"
        ledger = observation.get("conversation_progress", {})
        if claims_pending_commitment_completed(candidate, ledger):
            return False, "pending commitment was described as completed or settled"
        if prematurely_reports_future_commitment_completion(
            candidate, ledger, "evaluated_agent"
        ):
            return False, "future-timed commitment was reported complete without elapsed-time evidence"
        if claims_other_speaker_commitment(
            candidate, ledger, "evaluated_agent"
        ):
            return False, "pending commitment belongs to environment_agent"
        if contradicts_pending_own_commitment(
            candidate, ledger, "evaluated_agent"
        ):
            return False, "unsupported reversal of evaluated_agent pending commitment"
        if renews_pending_commitment_without_change(
            candidate,
            ledger,
            "evaluated_agent",
            observation.get("current_response", ""),
        ):
            return False, "same-owner pending commitment was merely renewed"
        if enforce_fixed_horizon and opens_future_cycle_on_final_turn(
            candidate, turn_number
        ):
            return False, "final turn opened another future cycle"
        if enforce_fixed_horizon and lacks_natural_final_closure(
            candidate, turn_number
        ):
            return False, "final turn lacked a natural decision or closure"
        if enforce_fixed_horizon and premature_closure_with_untouched_goals(
            candidate, ledger, turn_number
        ):
            return False, "premature closure left an untouched public goal"
        if repeats_future_meeting_deferral(
            candidate, observation.get("history", []), "evaluated_agent"
        ):
            return False, "future meeting was reused as dialogue progress"
        latest_response = observation.get("current_response", "") or next((
            str(item.get("text", ""))
            for item in reversed(observation.get("history", []))
            if item.get("role") == "environment_agent"
        ), "")
        if evades_latest_obligation(candidate, latest_response, "other"):
            return False, "candidate evades the latest obligation by changing domains"
        latest_is_proposal = re.search(
            r"(?:我建议|我提议|可以|可考虑|不如|要不要|是否愿意|是否可以|"
            r"你若同意|你如果同意)",
            latest_response,
        )
        starts_disposition = re.search(
            r"^(?:那)?(?:我)?(?:同意|接受|认可|不同意|不接受|拒绝|可以|不行)",
            str(candidate).strip(),
        )
        directly_disposes = directly_answers_latest_proposal(
            candidate, latest_response
        )
        follows_invited_scope = follows_latest_invited_scope(
            candidate, latest_response
        )
        current_obligation = ledger.get("latest_obligation") or {}
        owes_current_answer = current_obligation.get("owner") == "evaluated_agent"
        if (
            latest_is_proposal
            and starts_disposition
            and not directly_disposes
            and not _candidate_advances_available_thread(candidate, ledger)
            and not follows_invited_scope
        ):
            return False, "latest proposal answer added another condition or process"
        if opens_followup_on_saturated_focus(candidate, ledger):
            return False, "candidate opens another question on a saturated public goal"
        if (
            not directly_disposes
            and not follows_invited_scope
            and not owes_current_answer
            and repeats_saturated_goal_focus(candidate, ledger)
        ):
            return False, "candidate revisits a saturated public goal focus"
        if (
            not follows_invited_scope
            and not owes_current_answer
            and repeats_stalled_focus(candidate, ledger)
        ):
            return False, "same practical focus already occupied two full exchanges"
        if violates_role_specific_action(candidate, observation.get("role", {})):
            return False, "candidate action contradicts the public evaluated role"
        observable = (
            str(observation.get("public_situation", {})) + " "
            + " ".join(
                str(item.get("text", ""))
                for item in observation.get("history", [])
            )
            + " " + str(observation.get("current_response", ""))
        )
        if asserts_ungrounded_institutional_procedure(candidate, observable):
            return False, "candidate asserts an ungrounded institutional procedure or record fact"
        if introduces_unrequested_artifact(candidate, observable):
            return False, "candidate invents an unrequested artifact workflow"
        if introduces_unprompted_coordination_actor(candidate, observable):
            return False, "candidate invents an unprompted coordination actor"
        if introduces_unprompted_legal_escalation(candidate, observable):
            return False, "candidate invents an unprompted legal escalation"
        if confirms_ungrounded_numeric_detail(candidate, observable):
            return False, "candidate confirms a numeric detail absent from observable history"
        return True, ""
