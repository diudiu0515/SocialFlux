"""Persona- and history-conditioned appraisal for arbitrary free-form actions."""

from copy import deepcopy
import re

from providers.structured import complete_json

from .calibration import FEATURE_NAMES
from .appraisal_normalization import (
    canonicalize_event_features,
    canonicalize_impact_lists,
    canonicalize_social_act,
)
from .delta_mapper import flatten_state
from .interaction_ledger import validate_semantic_ledger_events
from .prompts import build_appraisal_prompt
from .public_situation import render_public_background


SOCIAL_ACTS = {
    "inform", "question", "request", "proposal", "conditional_offer",
    "tentative_plan", "commitment", "delivery", "concession", "clarification",
    "challenge", "accusation", "threat", "boundary", "refusal", "deferral",
    "repair", "withdrawal", "pause", "other",
}


def _validate_impacts(impacts, allowed_variables, label):
    if not isinstance(impacts, list):
        raise ValueError(f"{label} must be a list")
    seen = set()
    required = {
        "variable", "direction", "evidence_strength",
        "directness", "new_evidence",
    }
    for impact in impacts:
        if not isinstance(impact, dict) or set(impact) != required:
            raise ValueError(f"each {label} entry must contain exactly {sorted(required)}")
        variable = impact["variable"]
        if variable not in allowed_variables:
            raise ValueError(f"{label} references unknown variable {variable!r}")
        if variable in seen:
            raise ValueError(f"{label} repeats variable {variable!r}")
        seen.add(variable)
        if impact["direction"] not in {"increase", "decrease"}:
            raise ValueError(f"{label} has invalid direction")
        strength = impact["evidence_strength"]
        if isinstance(strength, bool) or strength not in {1, 2}:
            raise ValueError(f"{label} evidence_strength must be 1 or 2")
        if impact["directness"] not in {"direct", "indirect"}:
            raise ValueError(f"{label} directness must be direct or indirect")
        if not isinstance(impact["new_evidence"], bool):
            raise ValueError(f"{label} new_evidence must be boolean")


def appraisal_preserves_action_owner(appraisal, environment_speaker=None):
    """The appraisal intent must describe the evaluated speaker's latest action."""
    intent = str((appraisal or {}).get("speaker_intent", "")).strip()
    speaker = environment_speaker or {}
    labels = {
        str(speaker.get("name", "")).strip(),
        "环境角色",
        "环境参与者",
    } - {""}
    actor_move = r"(?:正|正在|试图|需要|希望|要求|请求|想|意在|打算|寻求|旨在|准备)"
    return not any(
        re.match(rf"^{re.escape(label)}{actor_move}", intent)
        for label in labels
    )


NOVELTY_LABELS = {
    "new_explanation", "new_position", "new_tradeoff", "new_evidence",
    "new_decision", "necessary_confirmation", "none",
}
CLAIM_IMPACT_DOMAINS = {
    "responsibility", "rights", "action_feasibility", "task_answer",
}
CLAIM_GROUNDING = {
    "observable_fact", "proposal_or_hypothetical",
    "unsupported_assertion", "uncertain",
}
CONTINUATION_STATUS = {"must_answer", "continue", "can_close"}

_DIALOGUE_DIAGNOSTIC_PROMPTS = frozenset(
    f"environment_appraisal_v{version}" for version in range(4, 12)
)
_AFTER_DIRECT_RESPONSE_PROMPTS = frozenset(
    f"environment_appraisal_v{version}" for version in range(5, 12)
)
_LEDGER_EVENT_PROMPTS = frozenset(
    f"environment_appraisal_v{version}" for version in range(7, 12)
)
_LEDGER_NORMALIZATION_PROMPTS = frozenset(
    f"environment_appraisal_v{version}" for version in range(8, 12)
)
_LIVE_QUESTION_PARTITION_PROMPTS = frozenset(
    f"environment_appraisal_v{version}" for version in range(6, 10)
)
_ASSERTION_MODE_PROMPTS = frozenset({"environment_appraisal_v11"})


def _exact_span_or_empty(span, action_text, label, allow_empty=False):
    if not isinstance(span, str):
        raise ValueError(f"{label} evidence span must be text")
    if not span and allow_empty:
        return
    if not span or span not in action_text:
        raise ValueError(f"{label} evidence span must be an exact latest-action substring")


def _validate_dialogue_diagnostics(
    value, action_text, require_after_direct_response=False,
    live_questions=None, require_live_question_partition=False,
):
    if not isinstance(value, dict) or set(value) != {
        "substantive_novelty", "consequential_claims", "continuation"
    }:
        raise ValueError("dialogue_diagnostics has an invalid shape")
    novelty = value["substantive_novelty"]
    if not isinstance(novelty, dict) or set(novelty) != {"label", "evidence_span"}:
        raise ValueError("substantive_novelty has an invalid shape")
    novelty_aliases = {
        "new_confirmation": "necessary_confirmation",
        "new_question": "new_position",
        "new_request": "new_position",
        "new_inquiry": "new_position",
        "new_clarification": "new_position",
        "new_proposal": "new_position",
        "question": "new_position",
        "confirmation": "necessary_confirmation",
        "no_novelty": "none",
    }
    novelty["label"] = novelty_aliases.get(novelty["label"], novelty["label"])
    if novelty["label"] not in NOVELTY_LABELS:
        raise ValueError("substantive_novelty label is invalid")
    try:
        _exact_span_or_empty(
            novelty["evidence_span"], action_text, "substantive_novelty",
            allow_empty=novelty["label"] == "none",
        )
    except ValueError:
        novelty["evidence_span"] = (
            "" if novelty["label"] == "none" else action_text
        )
    claims = value["consequential_claims"]
    if not isinstance(claims, list) or len(claims) > 3:
        raise ValueError("consequential_claims must be a list of at most three")
    valid_claims = []
    for claim in claims:
        if (
            isinstance(claim, dict)
            and "claim_span" not in claim
            and ("span" in claim or "evidence_span" in claim)
        ):
            claim = dict(claim)
            alias = "span" if "span" in claim else "evidence_span"
            claim["claim_span"] = claim.pop(alias)
        if (
            isinstance(claim, dict)
            and set(claim) == {"claim_span", "impact_domain", "grounding"}
        ):
            domain = claim.pop("impact_domain")
            claim["impact_domains"] = (
                list(domain) if isinstance(domain, list) else [domain]
            )
        if not isinstance(claim, dict) or set(claim) != {
            "claim_span", "impact_domains", "grounding"
        }:
            # Consequential claims are diagnostic only.  Preserve uncertainty by
            # dropping a malformed annotation instead of inventing its grounding
            # or aborting an otherwise valid state appraisal.
            continue
        try:
            _exact_span_or_empty(claim["claim_span"], action_text, "claim")
        except ValueError:
            # Consequential claims are diagnostic annotations. An unsupported
            # annotation is discarded rather than aborting a valid appraisal.
            continue
        domains = claim["impact_domains"]
        domain_aliases = {
            "communication_boundary": "responsibility",
            "feasibility": "action_feasibility",
            "answer": "task_answer",
        }
        if isinstance(domains, list):
            domains = list(dict.fromkeys(
                domain_aliases.get(domain, domain) for domain in domains
            ))
            claim["impact_domains"] = domains
        if (
            not isinstance(domains, list) or not domains
            or len(domains) != len(set(domains))
            or not set(domains).issubset(CLAIM_IMPACT_DOMAINS)
        ):
            continue
        if isinstance(claim["grounding"], list):
            if (
                len(claim["grounding"]) == 1
                and claim["grounding"][0] in CLAIM_GROUNDING
            ):
                claim["grounding"] = claim["grounding"][0]
            else:
                continue
        if claim["grounding"] not in CLAIM_GROUNDING:
            continue
        valid_claims.append(claim)
    value["consequential_claims"] = valid_claims
    continuation = value["continuation"]
    allowed_continuation = {"status", "evidence_span", "after_direct_response"}
    if (
        not isinstance(continuation, dict)
        or not {"status", "evidence_span"}.issubset(continuation)
        or not set(continuation).issubset(allowed_continuation)
        or (require_after_direct_response and "after_direct_response" not in continuation)
    ):
        raise ValueError("continuation has an invalid shape")
    if continuation["status"] not in CONTINUATION_STATUS:
        raise ValueError("continuation status is invalid")
    try:
        _exact_span_or_empty(
            continuation["evidence_span"], action_text, "continuation",
            allow_empty=continuation["status"] == "can_close",
        )
    except ValueError:
        continuation["evidence_span"] = (
            "" if continuation["status"] == "can_close" else action_text
        )
    after_direct = continuation.get("after_direct_response")
    if after_direct is not None:
        # Some otherwise valid appraisals reuse the pre-response ``must_answer``
        # label here. After a direct response that can only mean "continue":
        # canonicalize conservatively and never let this alias create a pause.
        if (
            isinstance(after_direct, dict)
            and after_direct.get("status") == "must_answer"
        ):
            after_direct["status"] = "continue"
        base_after_keys = {"status", "evidence_span"}
        partition_keys = {"resolved_live_questions", "remaining_live_questions"}
        supplied_after_keys = set(after_direct) if isinstance(after_direct, dict) else set()
        shape_valid = (
            supplied_after_keys == base_after_keys | partition_keys
            if require_live_question_partition
            else (
                base_after_keys.issubset(supplied_after_keys)
                and supplied_after_keys.issubset(base_after_keys | partition_keys)
            )
        )
        if (
            not isinstance(after_direct, dict)
            or not shape_valid
            or after_direct.get("status") not in {"can_close", "continue"}
        ):
            raise ValueError("after_direct_response has an invalid shape")
        try:
            _exact_span_or_empty(
                after_direct["evidence_span"], action_text,
                "after_direct_response",
            )
        except ValueError:
            after_direct["evidence_span"] = action_text
        if require_live_question_partition:
            supplied = list(live_questions or [])
            resolved = after_direct["resolved_live_questions"]
            remaining = after_direct["remaining_live_questions"]
            if not isinstance(resolved, list) or not isinstance(remaining, list):
                raise ValueError("live-question partition must use lists")
            if (
                any(not isinstance(item, str) for item in resolved + remaining)
                or len(supplied) != len(set(supplied))
            ):
                raise ValueError("live-question partition must use unique text questions")
            raw_resolved = set(resolved)
            raw_remaining = set(remaining)
            # Only an exact, unconflicted copy counts as resolved. Unknown,
            # paraphrased, omitted, duplicated, or conflicting entries remain
            # unresolved. This can delay a pause but can never create one.
            canonical_resolved = [
                item for item in supplied
                if item in raw_resolved and item not in raw_remaining
            ]
            canonical_remaining = [
                item for item in supplied if item not in canonical_resolved
            ]
            after_direct["resolved_live_questions"] = canonical_resolved
            after_direct["remaining_live_questions"] = canonical_remaining
            # Keep the exact partition as diagnostic evidence.  Live questions
            # describe possible discussion space; they do not override the
            # model's semantic judgment that this contact can naturally close.
    return value


def _validate_appraisal(
    result,
    allowed_evidence_ids=None,
    state_variables=None,
    dynamics_variables=None,
    environment_speaker=None,
    action_text="",
    require_dialogue_diagnostics=False,
    require_after_direct_response=False,
    live_questions=None,
    require_live_question_partition=False,
    require_ledger_events=False,
    require_assertion_mode=False,
    normalize_ledger_noise=False,
    active_proposals=None,
):
    if not isinstance(result, dict):
        raise ValueError("model appraiser must return an object")
    appraisal = result.get("appraisal")
    # A known schema-only variation places diagnostics beside appraisal. Move
    # the supplied object to its canonical location without changing any
    # semantic value or making another model request.
    if (
        set(result) == {"appraisal", "dialogue_diagnostics", "evidence_turn_ids"}
        and isinstance(appraisal, dict)
        and "dialogue_diagnostics" not in appraisal
        and isinstance(result.get("dialogue_diagnostics"), dict)
    ):
        appraisal = dict(appraisal)
        appraisal["dialogue_diagnostics"] = result["dialogue_diagnostics"]
        result = {
            "appraisal": appraisal,
            "evidence_turn_ids": result["evidence_turn_ids"],
        }
    if (
        set(result) == {"appraisal"}
        and isinstance(appraisal, dict)
        and "evidence_turn_ids" in appraisal
    ):
        appraisal = dict(appraisal)
        evidence = appraisal.pop("evidence_turn_ids")
        result = {"appraisal": appraisal, "evidence_turn_ids": evidence}
    if set(result) != {"appraisal", "evidence_turn_ids"}:
        raise ValueError("model appraiser must return appraisal and evidence_turn_ids")
    evidence = result["evidence_turn_ids"]
    if not isinstance(result["appraisal"], dict) or not isinstance(evidence, list):
        raise ValueError("model appraisal has an invalid shape")
    appraisal = result["appraisal"]
    required = {
        "speaker_intent", "social_act", "event_features",
        "state_impacts", "dynamics_impacts",
    }
    allowed = required | {
        "dialogue_diagnostics", "ledger_events", "ledger_event_normalizations"
    }
    if not required.issubset(appraisal) or not set(appraisal).issubset(allowed):
        raise ValueError(
            f"structured appraisal must contain {sorted(required)} and only optional dialogue_diagnostics"
        )
    if require_dialogue_diagnostics and "dialogue_diagnostics" not in appraisal:
        raise ValueError("structured appraisal must include dialogue_diagnostics")
    if require_ledger_events and "ledger_events" not in appraisal:
        raise ValueError("structured appraisal must include ledger_events")
    appraisal.pop("ledger_event_normalizations", None)
    if "ledger_events" in appraisal:
        ledger_event_normalizations = []
        appraisal["ledger_events"] = validate_semantic_ledger_events(
            appraisal["ledger_events"], str(action_text).strip(),
            "evaluated_agent", drop_irrelevant=normalize_ledger_noise,
            normalize_tentative_commitments=normalize_ledger_noise,
            normalize_pending_commitments=normalize_ledger_noise,
            drop_acceptance_commitments=normalize_ledger_noise,
            drop_acceptance_events=normalize_ledger_noise,
            active_proposals=active_proposals,
            normalization_log=ledger_event_normalizations,
            require_assertion_mode=require_assertion_mode,
        )
        if ledger_event_normalizations:
            appraisal["ledger_event_normalizations"] = ledger_event_normalizations
    if "dialogue_diagnostics" in appraisal:
        _validate_dialogue_diagnostics(
            appraisal["dialogue_diagnostics"], str(action_text).strip(),
            require_after_direct_response=require_after_direct_response,
            live_questions=live_questions,
            require_live_question_partition=require_live_question_partition,
        )
    raw_impact_count = sum(
        len(appraisal.get(key, []))
        for key in ("state_impacts", "dynamics_impacts")
        if isinstance(appraisal.get(key), list)
    )
    if state_variables is not None and dynamics_variables is not None:
        appraisal = canonicalize_impact_lists(
            appraisal, state_variables, dynamics_variables
        )
        result = dict(result)
        result["appraisal"] = appraisal
    if not isinstance(appraisal["speaker_intent"], str) or not appraisal["speaker_intent"].strip():
        raise ValueError("speaker_intent must be non-empty text")
    if not appraisal_preserves_action_owner(appraisal, environment_speaker):
        raise ValueError(
            "speaker_intent assigned the evaluated action to the environment character"
        )
    appraisal["social_act"] = canonicalize_social_act(appraisal["social_act"], SOCIAL_ACTS)
    features = canonicalize_event_features(appraisal["event_features"], FEATURE_NAMES)
    appraisal["event_features"] = features
    if "ledger_events" in appraisal and features.get("commitment_signal", 0) <= 0:
        inconsistent = [
            event for event in appraisal["ledger_events"]
            if event["event_type"] == "commitment"
            and event["status"] in {"firm", "conditional"}
        ]
        if inconsistent:
            appraisal["ledger_events"] = [
                event for event in appraisal["ledger_events"]
                if event not in inconsistent
            ]
            appraisal.setdefault("ledger_event_normalizations", []).extend([{
                "operation": "drop_internally_inconsistent_commitment",
                "reason": "commitment_event_conflicts_with_nonpositive_commitment_signal",
                "event": deepcopy(event),
            } for event in inconsistent])
    result["appraisal"] = appraisal
    if not isinstance(features, dict) or set(features) != set(FEATURE_NAMES):
        raise ValueError("event_features must contain the fixed feature set exactly once")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < -2 or value > 2
        for value in features.values()
    ):
        raise ValueError("every event feature must be an integer from -2 to 2")
    if state_variables is not None:
        _validate_impacts(appraisal["state_impacts"], set(state_variables), "state_impacts")
    if dynamics_variables is not None:
        _validate_impacts(
            appraisal["dynamics_impacts"], set(dynamics_variables), "dynamics_impacts"
        )
    normalized_impact_count = (
        len(appraisal["state_impacts"]) + len(appraisal["dynamics_impacts"])
    )
    if raw_impact_count and not normalized_impact_count:
        raise ValueError(
            "candidate impacts were unusable; every impact needs a valid variable path"
        )
    allowed_ids = (
        set(allowed_evidence_ids) if allowed_evidence_ids is not None else None
    )
    normalized_evidence = []
    for evidence_id in evidence:
        if not isinstance(evidence_id, str):
            continue
        if allowed_ids is not None and evidence_id not in allowed_ids:
            continue
        if evidence_id not in normalized_evidence:
            normalized_evidence.append(evidence_id)
        if len(normalized_evidence) == 4:
            break
    result["evidence_turn_ids"] = normalized_evidence
    return result


class ModelAppraiser:
    def __init__(
        self, scenario, provider, sampling=None,
        prompt_id="environment_appraisal_v6",
    ):
        self.scenario = deepcopy(scenario)
        self.provider = provider
        self.sampling = dict(sampling or {})
        self.prompt_id = prompt_id
        configured_max = self.sampling.get("max_tokens")
        if configured_max is None:
            provider_defaults = getattr(provider, "generation_defaults", {})
            provider_max = getattr(provider, "max_tokens", None)
            if not isinstance(provider_max, int) or isinstance(provider_max, bool):
                provider_max = (
                    provider_defaults.get("max_tokens")
                    if isinstance(provider_defaults, dict) else None
                )
            self.sampling["max_tokens"] = (
                provider_max
                if isinstance(provider_max, int)
                and not isinstance(provider_max, bool)
                and provider_max > 0
                else 2800
            )
        elif (
            not isinstance(configured_max, int)
            or isinstance(configured_max, bool)
            or configured_max < 1
        ):
            raise ValueError("appraisal max_tokens must be a positive integer")

    @property
    def provenance(self):
        return {
            **getattr(self.provider, "provenance", {}),
            "prompt_id": self.prompt_id,
            "sampling": dict(self.sampling),
        }

    def appraise(
        self, *, action, previous_state, previous_dynamics, memory,
        longitudinal_context=None, interaction_ledger=None,
    ):
        agent = self.scenario["environment_agent"]
        prompt = build_appraisal_prompt(
            persona=agent["persona"],
            background=render_public_background(self.scenario),
            explicit_goal=agent["explicit_goal"],
            hidden_intention=agent["hidden_intention"],
            previous_state=previous_state,
            previous_dynamics=previous_dynamics,
            memory=memory,
            action=action,
            longitudinal_context=longitudinal_context,
            interaction_ledger=interaction_ledger,
            prompt_id=self.prompt_id,
        )
        evaluated = self.scenario.get("evaluated_agent_role", {})
        environment_persona = agent.get("persona", agent)
        system_prompt = (
            "你是结构化 appraisal 分析器，不扮演任何对话人物。最新 action 的唯一作者是 "
            f"evaluated_agent：{evaluated.get('name', '被评估参与者')}（"
            f"{evaluated.get('role', '被评估参与者')}）；被该行动影响并将在之后回应的是 "
            f"environment_agent：{environment_persona.get('name', '环境参与者')}（"
            f"{environment_persona.get('role', '环境参与者')}）。speaker_intent 必须描述 "
            "evaluated_agent 此刻在做什么，绝不能把 action 写成 environment_agent 的意图、"
            "请求、承诺或行动。只返回指定 JSON。"
        )
        retry_diagnostics = []
        result = complete_json(
            self.provider,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            self.sampling,
            lambda result: _validate_appraisal(
                result,
                memory.get("relevant_turn_ids", []),
                flatten_state(previous_state),
                flatten_state(previous_dynamics),
                environment_speaker=agent.get("persona", agent),
                action_text=action.get("text", ""),
                require_dialogue_diagnostics=(
                    self.prompt_id in _DIALOGUE_DIAGNOSTIC_PROMPTS
                ),
                require_after_direct_response=(
                    self.prompt_id in _AFTER_DIRECT_RESPONSE_PROMPTS
                ),
                live_questions=(longitudinal_context or {}).get(
                    "segment", {}
                ).get("live_questions", []),
                require_live_question_partition=(
                    self.prompt_id in _LIVE_QUESTION_PARTITION_PROMPTS
                ),
                require_ledger_events=self.prompt_id in _LEDGER_EVENT_PROMPTS,
                require_assertion_mode=self.prompt_id in _ASSERTION_MODE_PROMPTS,
                normalize_ledger_noise=(
                    self.prompt_id in _LEDGER_NORMALIZATION_PROMPTS
                ),
                active_proposals=(interaction_ledger or {}).get(
                    "active_proposals", []
                ),
            ),
            context="model appraiser",
            diagnostics_sink=retry_diagnostics,
        )
        result["request_retry_diagnostics"] = retry_diagnostics
        return result
