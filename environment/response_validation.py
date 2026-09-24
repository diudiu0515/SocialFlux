"""Validation contract for state-conditioned environment responses.

Prompt construction and provider orchestration live in response_generator.
This module owns structured-output normalization, role/fact checks, and retry
instructions. Keeping it separate prevents generation control flow from
accumulating another layer of validators.
"""

import re
import json
from copy import deepcopy

from environment.dialogue_support import (
    contains_private_simulator_language,
    focus_retry_guidance,
)
from environment.public_situation import build_public_situation
from providers.text import (
    asserts_ungrounded_institutional_procedure,
    asserts_ungrounded_performance_amount,
    asserts_ungrounded_remaining_amount,
    bounces_latest_stance_request,
    addresses_speaker_as_other,
    avoids_unsupported_offscreen_claim,
    claims_other_speaker_commitment,
    claims_pending_commitment_completed,
    current_repayment_commitment_status,
    collapses_multiple_facets_early,
    confirms_unobserved_completion,
    confirms_ungrounded_numeric_detail,
    contradicts_explicit_installment_total,
    contradicts_pending_own_commitment,
    copies_goal_thread_label,
    copies_latest_other_utterance,
    introduces_unprompted_coordination_actor,
    introduces_unprompted_legal_escalation,
    introduces_unrequested_artifact,
    evades_latest_obligation,
    follows_dialogue_format,
    goal_thread_constraints,
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
    violates_environment_counterparty_role,
)

from .interaction_ledger import (
    creates_reply_obligation,
    uncovered_owned_commitment_spans,
    validate_semantic_ledger_events,
)


_SPECIFIC_NUMBER_RE = re.compile(
    r"(?P<number>\d+(?:\.\d+)?|[零一二两三四五六七八九十百千万]+)"
    r"(?P<unit>元|块|千|万|天|周|个月|月|年|成|%)"
)


def _observable_text(context):
    return json.dumps({
        "scenario": context.get("scenario", {}),
        "history": context.get("history", []),
        "action": context.get("action", {}),
        "longitudinal_context": context.get("longitudinal_context", {}),
        "established_facts": context.get(
            "interaction_ledger", {}
        ).get("established_facts", []),
    }, ensure_ascii=False, sort_keys=True)


def _chinese_number(value):
    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        return float(value)
    digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100, "千": 1000}
    total = section = number = 0
    for character in value:
        if character in digits:
            number = digits[character]
        elif character == "万":
            section += number
            total += (section or 1) * 10000
            section = number = 0
        elif character in units:
            section += (number or 1) * units[character]
            number = 0
    return float(total + section + number)


def _canonical_number(match):
    number = _chinese_number(match.group("number"))
    unit = match.group("unit")
    if unit == "千":
        number *= 1000
        unit = "count"
    elif unit == "万":
        number *= 10000
        unit = "count"
    elif unit in {"元", "块"}:
        unit = "currency"
    return number, unit


def _validate_new_specific_numbers(claims, text, context):
    observed = {
        _canonical_number(match)
        for match in _SPECIFIC_NUMBER_RE.finditer(_observable_text(context))
    }
    for match in _SPECIFIC_NUMBER_RE.finditer(text):
        term = match.group(0)
        if _canonical_number(match) in observed:
            continue
        covering = [
            claim for claim in claims
            if term in claim.get("claim_span", "")
        ]
        if not covering:
            raise ValueError(
                "new specific number must be covered by consequential_claims"
            )
        if any(claim["grounding"] == "observable_fact" for claim in covering):
            raise ValueError(
                "new specific number is absent from observable history and cannot "
                "be grounded as observable_fact"
            )


def _validate_v25_semantics(value, text, events, context):
    obligation = value.get("reply_obligation")
    if obligation not in {None, "evaluated_agent"}:
        raise ValueError("reply_obligation must be null or evaluated_agent")
    has_request = any(
        event["event_type"] == "request"
        and event["action_owner"] == "evaluated_agent"
        for event in events
    )
    if bool(obligation) != has_request:
        raise ValueError("reply_obligation and asserted request events disagree")

    claims = value.get("consequential_claims")
    if not isinstance(claims, list) or len(claims) > 3:
        raise ValueError("consequential_claims must contain at most three items")
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {
            "claim_span", "impact_domains", "grounding"
        }:
            raise ValueError("response consequential claim has invalid shape")
        span = claim["claim_span"]
        if not isinstance(span, str) or not span or span not in text:
            raise ValueError("response consequential claim must quote response_text")
        if claim["grounding"] not in {
            "observable_fact", "proposal_or_hypothetical",
            "unsupported_assertion", "uncertain",
        }:
            raise ValueError("response consequential claim grounding is invalid")
        if claim["grounding"] == "unsupported_assertion":
            raise ValueError(
                "response_text asserts a consequential fact absent from public history"
            )
    _validate_new_specific_numbers(claims, text, context)


def _validate_expression(value, controlled):
    intent = str(value.get("expression_intent", "")).strip()
    if not intent or len(intent) > 160:
        raise ValueError("expression_intent must be a concise non-empty string")
    behavior = controlled.get("observable_expression")
    if behavior is None:
        behavior = value.get("observable_behavior")
    keys = {
        "facial_expression", "gaze", "speech_style", "prosody",
        "behavioral_cues",
    }
    if not isinstance(behavior, dict) or set(behavior) != keys:
        raise ValueError("observable_behavior has invalid keys")
    if any(not isinstance(behavior[key], str) for key in keys - {"behavioral_cues"}):
        raise ValueError("observable_behavior text fields must be strings")
    cues = behavior.get("behavioral_cues")
    if not isinstance(cues, list) or any(
        not isinstance(cue, str) or not cue.strip() for cue in cues
    ):
        raise ValueError("observable_behavior behavioral_cues must be strings")
    return intent, behavior


def validate_structured_response(generator, value, context):
    prompt_id = getattr(generator, "prompt_id", None)
    expression_mode = prompt_id == "environment_response_v25"
    semantic_mode = prompt_id == "environment_response_v25"
    expected_keys = {"response_text", "ledger_events"}
    if expression_mode:
        expected_keys.update({"expression_intent", "observable_behavior"})
    if semantic_mode:
        expected_keys.update({"consequential_claims", "reply_obligation"})
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise ValueError(
            "response JSON must contain exactly "
            + ", ".join(sorted(expected_keys))
        )

    controlled = context.get("controlled_observation") or {}
    controlled_text = str(controlled.get("current_response", "")).strip()
    text = controlled_text or str(value.get("response_text", "")).strip()
    if not text or not follows_dialogue_format(text):
        raise ValueError("response_text must be a direct utterance")
    if contains_private_simulator_language(text):
        raise ValueError("response_text leaks private simulator language")
    if semantic_mode:
        scenario = context.get("scenario", {})
        environment_agent = scenario.get("environment_agent", {})
        persona = environment_agent.get("persona", environment_agent)
        latest = context.get("action", {}).get("text", "")
        if addresses_speaker_as_other(text, persona):
            raise ValueError("response addresses its own speaker as the counterparty")
        if copies_latest_other_utterance(text, latest):
            raise ValueError("response verbatim-echoes the latest other-speaker turn")
    else:
        valid, reason = generator._validate_candidate_for_profile(text, context)
        if not valid:
            raise ValueError(reason or "response_text failed runtime validation")

    normalizations = []
    events = validate_semantic_ledger_events(
        value["ledger_events"], text, "environment_agent",
        drop_ungrounded=True,
        normalize_tentative_commitments=True,
        normalize_owned_future_requests=True,
        drop_irrelevant=True,
        drop_acceptance_events=True,
        active_proposals=context.get(
            "interaction_ledger", {}
        ).get("active_proposals", []),
        normalization_log=normalizations,
        require_assertion_mode=semantic_mode,
    )
    if semantic_mode:
        _validate_v25_semantics(value, text, events, context)
    else:
        if creates_reply_obligation(text) and not any(
            event["event_type"] == "request" for event in events
        ):
            raise ValueError(
                "response_text contains an explicit request but ledger_events omits it"
            )
        for span in uncovered_owned_commitment_spans(
            text, events, "environment_agent"
        ):
            event = {
                "event_type": "commitment",
                "owner": "environment_agent",
                "action_owner": "environment_agent",
                "evidence_span": span,
                "status": "firm",
            }
            events.append(event)
            normalizations.append({
                "operation": "add_missing_explicit_commitment_event",
                "reason": "explicit_non_tentative_owned_future_action",
                "event": dict(event),
            })

    result = {
        "response_text": text,
        "ledger_events": events,
        "ledger_event_normalizations": normalizations,
    }
    if expression_mode:
        intent, behavior = _validate_expression(value, controlled)
        result.update({
            "expression_intent": intent,
            "observable_behavior": behavior,
        })
    if semantic_mode:
        result.update({
            "reply_obligation": value["reply_obligation"],
            "consequential_claims": deepcopy(value["consequential_claims"]),
        })
    return result


def validate_candidate_for_profile(generator, candidate, context):
        if generator.validation_profile == "full":
            return generator._validate_candidate(
                candidate, context,
                enforce_fixed_horizon=generator.horizon_mode == "fixed_20",
            )
        ledger = context.get("interaction_ledger", {})
        latest = context.get("action", {}).get("text", "")
        record_status = current_repayment_commitment_status(
            ledger,
            context.get("longitudinal_context", {}).get("public_timeline", []),
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
        observable = (
            str(context.get("scenario", {}).get("background", "")) + " "
            + str(build_public_situation(context.get("scenario", {}))) + " "
            + " ".join(str(item.get("text", "")) for item in context.get("history", []))
            + " " + str(latest)
        )
        if contains_private_simulator_language(candidate):
            return False, "private simulator language leakage"
        if confirms_unobserved_completion(candidate, latest):
            return False, "promise incorrectly treated as observable completion"
        if copies_latest_other_utterance(candidate, latest):
            return False, "verbatim echo of the latest evaluated-agent utterance"
        if (
            mirrors_latest_speaker_move(candidate, latest)
            and not generator._answers_current_owned_action_request(candidate, context)
        ):
            return False, "latest evaluated-agent action was taken over by environment_agent"
        segment = context.get("longitudinal_context", {}).get("segment", {})
        if (
            int(segment.get("segment_turn_id", 0) or 0) == 0
            and any(
                item.get("role") == "environment_agent"
                and normalize_text(item.get("text", "")) == normalize_text(candidate)
                for item in context.get("history", [])
            )
        ):
            return False, "stale environment response repeated across a public event boundary"
        if (
            segment.get("forbid_new_repayment_commitment")
            and opens_new_repayment_commitment(candidate)
        ):
            return False, "current fragment forbids a new repayment commitment"
        if asserts_ungrounded_performance_amount(candidate, observable):
            return False, "precise completed-payment amount lacks a public record"
        if asserts_ungrounded_remaining_amount(candidate, observable):
            return False, "precise remaining balance lacks a public record"
        if contradicts_explicit_installment_total(candidate, latest):
            return False, "response contradicts the explicit installment total"
        if claims_pending_commitment_completed(candidate, ledger):
            return False, "pending commitment was described as completed or settled"
        public_record_text = " ".join(
            str(item.get("text", ""))
            for item in context.get("longitudinal_context", {}).get(
                "public_timeline", []
            )
            if item.get("public", True)
        )
        if prematurely_reports_future_commitment_completion(
            candidate, ledger, "environment_agent", public_record_text
        ):
            return False, "future-timed commitment was reported complete without evidence"
        if claims_other_speaker_commitment(candidate, ledger, "environment_agent"):
            return False, "pending commitment belongs to evaluated_agent"
        if contradicts_pending_own_commitment(candidate, ledger, "environment_agent"):
            return False, "unsupported reversal of environment_agent pending commitment"
        scenario = context.get("scenario", {})
        if violates_environment_counterparty_role(
            candidate, scenario.get("evaluated_agent_role", {})
        ):
            return False, "environment response contradicts counterparty role ownership"
        environment_agent = scenario.get("environment_agent", {})
        persona = environment_agent.get("persona", environment_agent)
        if addresses_speaker_as_other(candidate, persona):
            return False, "environment character addressed itself as the other speaker"
        return True, ""


def answers_current_owned_action_request(candidate, context):
        """Allow only the action that a current semantic request assigns here.

        A turn may contain both the evaluated speaker's own planned action and a
        request to the environment speaker.  The request does not license taking
        over the self-owned action; match the candidate against the quoted request.
        """
        obligation = (
            context.get("interaction_ledger", {}).get("latest_obligation") or {}
        )
        turn_id = context.get("turn_id", 0)
        owns_current_obligation = (
            obligation.get("owner") == "environment_agent"
            and obligation.get("source_thread_id")
            == f"t{turn_id}:evaluated_agent:thread"
        )
        if not owns_current_obligation:
            return False
        request_events = [
            event for event in context.get("appraisal", {}).get("ledger_events", [])
            if event.get("event_type") == "request"
            and event.get("action_owner") == "environment_agent"
            and event.get("evidence_span")
        ]
        for event in request_events:
            requested = str(event["evidence_span"])
            requested = re.sub(
                r"(?:请|希望|需要|要求)(?:你|您)", "我会", requested,
            )
            requested = re.sub(
                r"(?:你|您)(?:能否|是否|可否|可以|可不可以)?", "我会", requested,
            )
            requested = re.sub(r"(?:能否|是否|可否|可不可以)", "", requested)
            if "我" not in requested:
                requested = "我会" + requested
            if mirrors_latest_speaker_move(candidate, requested):
                return True
        return False


def structured_retry_guidance(context):
        controlled = context.get("controlled_observation") or {}
        if controlled:
            return (
                "This is a controlled T2 observation. Keep response_text byte-for-byte "
                "equal to controlled_observation.current_response and keep "
                "observable_behavior exactly equal to "
                "controlled_observation.observable_expression. Do not paraphrase either "
                "controlled field in a retry. Correct only expression_intent, JSON shape, "
                "or ledger_events as required by the reported validation error; every "
                "ledger evidence_span must remain an exact span of the controlled text."
            )
        latest_obligation = (
            context.get("interaction_ledger", {}).get("latest_obligation") or {}
        )
        must_answer = latest_obligation.get("owner") == "environment_agent"
        disposition = (
            "The newest utterance has an unanswered request: answer that request "
            "directly with currently available information. "
            if must_answer else
            "If the newest utterance only acknowledges or records an existing "
            "arrangement, use a brief present-tense explicit pause instead of "
            "restating its date, amount, plan, or future action. "
        )
        terminal = context.get("longitudinal_context", {}).get("segment", {})
        terminal_guidance = (
            "This is the last response of the terminal fragment. Replace the "
            "rejected future/conditional move with a present-tense conclusion or "
            "explicitly preserved disagreement, then pause this exchange. Do not "
            "create a condition, question, request, process, or future commitment. "
            if terminal.get("terminal_fragment")
            and int(terminal.get("turns_remaining_in_fragment", 0) or 0) == 1
            else ""
        )
        return (
            "Validation can reject response content even when the JSON shape is "
            "correct. Produce a materially different response_text and rebuild "
            "ledger_events from that revised text only. "
            + disposition
            + terminal_guidance
            + "Each ledger event uses a status valid for its event type and an "
            "assertion_mode from asserted, negated, hypothetical, quoted, or "
            "definitional; direct is not an assertion_mode. Do not invent a new "
            "condition, deadline, event, or conflict."
        )


def retry_guidance(context):
        ledger = context.get("interaction_ledger", {})
        parts = []
        own_pending = [
            item for item in ledger.get("commitments", [])
            if item.get("speaker") == "environment_agent"
            and item.get("status") == "pending"
        ]
        if own_pending:
            parts.append(
                "Your own pending promise is already preserved in the ledger. "
                "Do not mention, summarize, reassure, renew, or withdraw it; omit its "
                "amounts, dates, plan, execution, and future-action wording entirely. "
                "Answer only the newest action's different question or boundary in "
                "present tense. 已有承诺不需要重述；本轮禁止再提其金额、日期、"
                "计划、执行或‘我会’，只回答对方最新提出的另一个问题。"
            )
        parts.extend(focus_retry_guidance(ledger, goal_thread_constraints))
        return " ".join(parts)


def validate_candidate(
        candidate, context, enforce_fixed_horizon=True
    ):
        ledger = context.get("interaction_ledger", {})
        if collapses_multiple_facets_early(
            candidate, context.get("turn_id", 0)
        ):
            return False, "early response collapses multiple public goal facets at once"
        if overloads_consequential_terms(candidate, context.get("turn_id", 0)):
            return False, "candidate introduces too many consequential terms at once"
        if copies_goal_thread_label(candidate, ledger):
            return False, "candidate copied an internal public-goal label"
        if (
            enforce_fixed_horizon
            and not avoids_unsupported_offscreen_claim(candidate, environment=True)
        ):
            return False, "unsupported off-screen or institutional outcome"
        latest_action = context.get("action", {}).get("text", "")
        observable = (
            str(context.get("scenario", {}).get("background", "")) + " "
            + str(build_public_situation(context.get("scenario", {}))) + " "
            + " ".join(
                str(item.get("text", ""))
                for item in context.get("history", [])
            )
            + " " + str(latest_action)
        )
        if (
            enforce_fixed_horizon
            and asserts_ungrounded_institutional_procedure(candidate, observable)
        ):
            return False, "candidate asserts an ungrounded institutional procedure or record fact"
        if bounces_latest_stance_request(candidate, latest_action):
            return False, "candidate bounces the latest stance request back to its asker"
        if evades_latest_obligation(
            candidate,
            latest_action,
            context.get("appraisal", {}).get("social_act", "other"),
        ):
            return False, "candidate evades the latest obligation by changing domains"
        if confirms_unobserved_completion(candidate, latest_action):
            return False, "promise incorrectly treated as observable completion"
        if copies_latest_other_utterance(candidate, latest_action):
            return False, "verbatim echo of the latest evaluated-agent utterance"
        if mirrors_latest_speaker_move(candidate, latest_action):
            return False, "latest evaluated-agent action was taken over by environment_agent"
        segment = context.get("longitudinal_context", {}).get(
            "segment", {}
        )
        if (
            segment.get("forbid_new_repayment_commitment")
            and opens_new_repayment_commitment(candidate)
        ):
            return False, "current fragment forbids a new repayment commitment"
        history = context.get("history", [])
        if repeats_exactly_without_substantive_public_event(
            candidate, history, "environment_agent", latest_action,
        ):
            return False, "exact same-speaker refrain without a substantive public event"
        segment_turn = segment.get("segment_turn_id", 0)
        if repeats_own_utterance_without_new_challenge(
            candidate, history, "environment_agent", segment_turn, latest_action,
        ):
            return False, "exact same-speaker loop inside the current fragment"
        if asserts_ungrounded_performance_amount(candidate, observable):
            return False, "precise completed-payment amount lacks a public record"
        if asserts_ungrounded_remaining_amount(candidate, observable):
            return False, "precise remaining balance lacks a public record"
        if contradicts_explicit_installment_total(candidate, latest_action):
            return False, "response contradicts the explicit installment total"
        if upgrades_tentative_to_agreement(candidate, latest_action):
            return False, "tentative move was upgraded to an agreement"
        record_status = current_repayment_commitment_status(
            ledger,
            context.get("longitudinal_context", {}).get("public_timeline", []),
            latest_action,
        )
        if rewrites_absent_commitment_as_nonperformance(
            candidate,
            "没有形成可核验的还款承诺" if record_status == "no_verifiable_commitment" else latest_action,
        ):
            return False, "absence of a commitment was rewritten as nonperformance"
        if suspends_existing_obligation(candidate):
            return False, "existing obligation was suspended without grounding"
        ledger = context.get("interaction_ledger", {})
        if claims_pending_commitment_completed(candidate, ledger):
            return False, "pending commitment was described as completed or settled"
        if prematurely_reports_future_commitment_completion(
            candidate, ledger, "environment_agent"
        ):
            return False, "future-timed commitment was reported complete without elapsed-time evidence"
        if claims_other_speaker_commitment(
            candidate,
            ledger,
            "environment_agent",
        ):
            return False, "pending commitment belongs to evaluated_agent"
        if contradicts_pending_own_commitment(
            candidate, ledger, "environment_agent"
        ):
            return False, "unsupported reversal of environment_agent pending commitment"
        if renews_pending_commitment_without_change(
            candidate,
            ledger,
            "environment_agent",
            context.get("action", {}).get("text", ""),
        ):
            return False, "same-owner pending commitment was merely renewed"
        if enforce_fixed_horizon and opens_future_cycle_on_final_turn(
            candidate, context.get("turn_id", 0)
        ):
            return False, "final turn opened another future cycle"
        if enforce_fixed_horizon and lacks_natural_final_closure(
            candidate, context.get("turn_id", 0)
        ):
            return False, "final turn lacked a natural decision or closure"
        if enforce_fixed_horizon and premature_closure_with_untouched_goals(
            candidate, ledger, context.get("turn_id", 0)
        ):
            return False, "premature closure left an untouched public goal"
        if repeats_future_meeting_deferral(
            candidate, context.get("history", []), "environment_agent"
        ):
            return False, "future meeting was reused as dialogue progress"
        current_obligation = ledger.get("latest_obligation") or {}
        owes_current_answer = (
            current_obligation.get("owner") == "environment_agent"
            and current_obligation.get("source_thread_id")
            == f"t{context.get('turn_id', 0)}:evaluated_agent:thread"
        )
        if opens_followup_on_saturated_focus(candidate, ledger):
            return False, "candidate opens another question on a saturated public goal"
        if not owes_current_answer and repeats_saturated_goal_focus(candidate, ledger):
            return False, "candidate revisits a saturated public goal focus"
        if not owes_current_answer and repeats_stalled_focus(candidate, ledger):
            return False, "same practical focus already occupied two full exchanges"
        if introduces_unrequested_artifact(candidate, observable):
            return False, "candidate invents an unrequested artifact workflow"
        if introduces_unprompted_coordination_actor(candidate, observable):
            return False, "candidate invents an unprompted coordination actor"
        if introduces_unprompted_legal_escalation(candidate, observable):
            return False, "candidate invents an unprompted legal escalation"
        if confirms_ungrounded_numeric_detail(candidate, observable):
            return False, "response confirms a numeric detail absent from observable history"
        scenario = context.get("scenario", {})
        if violates_environment_counterparty_role(
            candidate, scenario.get("evaluated_agent_role", {})
        ):
            return False, "environment response contradicts counterparty role ownership"
        environment_agent = scenario.get("environment_agent", {})
        persona = environment_agent.get("persona", environment_agent)
        if addresses_speaker_as_other(candidate, persona):
            return False, "environment character addressed itself as the other speaker"
        return True, ""
