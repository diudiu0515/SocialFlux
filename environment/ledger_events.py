"""Quote-grounded semantic events used by the interaction ledger.

This module owns the event schema, normalization rules, and exact evidence
binding.  It does not mutate conversation state.
"""

from copy import deepcopy
import re

from providers.text import text_similarity


_SEMANTIC_LEDGER_EVENT_STATUSES = {
    "proposal": {"open", "tentative"},
    "commitment": {"conditional", "firm"},
    "payment": {"reported_complete"},
    "request": {"open"},
    "pause": {"explicit"},
    "claim": {"reported"},
}

_ASSERTION_MODES = {
    "asserted", "negated", "hypothetical", "quoted", "definitional",
}

ACTION_OWNERS = frozenset({"evaluated_agent", "environment_agent", "collective", "unspecified"})
LEDGER_EVENT_FIELDS = frozenset({"event_type", "owner", "action_owner", "evidence_span", "status", "assertion_mode"})


def semantic_ledger_wire_contract():
    """Shared source for prompt schema and runtime enum validation."""
    return {"required_fields": sorted(LEDGER_EVENT_FIELDS),
            "event_status_pairs": {key: sorted(values) for key, values in _SEMANTIC_LEDGER_EVENT_STATUSES.items()},
            "assertion_modes": sorted(_ASSERTION_MODES), "action_owners": sorted(ACTION_OWNERS)}


_TENTATIVE_COMMITMENT_RE = re.compile(
    r"(?:我|我们)(?:目前|现在|这边)?(?:觉得|认为)?(?:可以|能)?(?:会|将)?"
    r"(?:尽量|预计|初步考虑|尝试|争取|打算|计划)|"
    r"暂时(?:能|可以)?(?:接受|确认|确定|安排)|"
    r"(?:但|不过).{0,12}(?:不确定|可能|要看|取决于|根据实际情况调整)|"
    r"(?:具体|实际)(?:金额|执行)?.{0,10}(?:可能|不确定|调整)|"
    r"^(?:尽量|预计|初步考虑|尝试|争取|打算|计划)"
)


_FIRST_PERSON_COMMITMENT_PREFIX = (
    r"(?:我(?:这边|这里)?(?:今天|明天|稍后|之后|届时)?(?:会|将)(?!记(?:下|录)|觉得|认为|理解|接受|同意|认可|感到|希望|担心|知道|清楚)|"
    r"我(?:这边|这里)?"
    r"(?:(?:这|接下来|未来)?(?:\d+|[一二两三四五六七八九十]+)\s*天(?:内|后))?"
    r"(?:最多|目前|现在)?(?:能确定(?=(?:先)?(?:还|偿还|支付|转账))(?:先)?|先)"
    r"(?!看|听|理解|确认|确定|回答|说明|接受|记(?:下|录))|"
    r"我(?:这边|这里)?(?:今天|明天|稍后|之后|届时)(?!看|听|理解)|"
    r"我(?:这边|这里)?(?:目前|现在)?(?:预计|计划|打算|准备)(?!好)|"
    r"我(?:这边|这里)?可以(?!确认|说明|解释|回答|明确|接受|同意|认可|理解|觉得|认为|保留)|"
    r"我答应|我承诺|"
    r"我(?:同意|接受)(?![^。！？；]{0,32}(?:请|需要|希望|要求)(?:你|您))"
    r"(?=[^。！？；]{0,32}(?:还款|还钱|偿还|归还|转账|汇款|付款|支付))|"
    r"由我来|我负责)"
)


_FIRST_PERSON_COMMITMENT_PREFIX_RE = re.compile(_FIRST_PERSON_COMMITMENT_PREFIX)


_FIRST_PERSON_COMMITMENT_RE = re.compile(
    _FIRST_PERSON_COMMITMENT_PREFIX
    + r"(?P<object>[^。！？；]{1,64})"
)


def has_tentative_commitment_language(text):
    """Return whether explicit wording presents an effort/intention, not a promise."""
    return bool(_TENTATIVE_COMMITMENT_RE.search(str(text).strip()))


def _is_acceptance_only_event(
    source, event_type, span, action_owner, expected_owner, active_proposals
):
    """Identify acceptance/restatement without treating it as a new ledger event."""
    if event_type not in {
        "proposal", "commitment", "acceptance", "concession", "boundary"
    }:
        return False
    acknowledgement_accepts = bool(re.match(r"^好的[，,]", source.strip()))
    source_accepts = acknowledgement_accepts or bool(re.search(
        r"(?:接受|同意|认可)(?:你|您|对方|这个|该|这种)?|"
        r"(?:可以|可行)[，, ]*(?:我|我们)?接受",
        source,
    ))
    if not source_accepts:
        return False
    if re.search(
        r"(?:就按|会|将|今后|以后).{0,24}(?:保持|执行|联系|问候|沟通|做)",
        span,
    ):
        return False
    pure_acceptance_span = bool(re.search(
        r"^(?:好的?[，,。；;]?)?(?:我|我们)?"
        r"(?:接受|同意|认可).{0,32}"
        r"(?:提议|建议|方案|安排|方式|频率|联系)?[。！？]?$|"
        r"^(?:这种|这个|该)?.{0,16}(?:可以|可行)[，, ]*"
        r"(?:我|我们)?(?:接受|同意|认可)[。！？]?$",
        span.strip(),
    ))
    if pure_acceptance_span:
        return True
    if re.search(r"(?:但|不过|只是|改为|改成|条件是|前提是|除非)", source):
        return False
    if (
        acknowledgement_accepts
        and action_owner == "collective"
        and any(
            proposal.get("speaker") != expected_owner
            and proposal.get("status") in {"open", "tentative"}
            for proposal in (active_proposals or [])
        )
    ):
        return True
    return (
        action_owner == "collective"
        and any(
            proposal.get("speaker") != expected_owner
            and proposal.get("status") in {"open", "tentative"}
            and text_similarity(span, proposal.get("text", "")) >= 0.5
            for proposal in (active_proposals or [])
        )
    )


def _align_whitespace_variant_to_source(span, source):
    """Return an exact source slice when the only difference is whitespace."""
    if span in source:
        return span
    compact_source = []
    source_positions = []
    for index, character in enumerate(source):
        if character.isspace():
            continue
        compact_source.append(character)
        source_positions.append(index)
    compact_span = "".join(character for character in span if not character.isspace())
    if not compact_span:
        return None
    start = "".join(compact_source).find(compact_span)
    if start < 0:
        return None
    end = start + len(compact_span) - 1
    return source[source_positions[start]:source_positions[end] + 1]


def _creates_reply_obligation(text):
    """Detect a current request, excluding embedded future yes/no clauses."""
    value = str(text)
    if re.search(r"[？?]", value):
        return True
    if re.search(
        r"(?:请(?:立即|立刻|同步|先|直接|具体)?"
        r"(?:发送|提供|说明|确认|解释|告知|列出|明确|回答)|"
        r"为什么|怎么|如何|哪(?:个|些|种|一)|谁)",
        value,
    ):
        return True
    reduced = re.sub(
        r"(?:观察|判断|评估|核对|说明|证明|反映|记录).{0,18}(?:是否|能否)",
        "",
        value,
    )
    return bool(re.search(
        r"(?:希望|要求|需要|让)(?:你|您).{0,16}"
        r"(?:说明|确认|确保|提供|回答|完成|落实|履行|还款|转账|付款|执行)|"
        r"(?:请问|想知道|需要(?:你|您)|请(?:你|您)|告诉我).{0,24}"
        r"(?:能否|是否|可否)|"
        r"(?:你|您)看.{0,12}(?:行吗|可以吗|可行吗)|"
        r"(?:这个|该|上述).{0,12}(?:行吗|可以吗|可行吗)|"
        r"(?:你|您).{0,16}(?:能否|是否|可否)|"
        r"我们(?:能否|是否|可否)|"
        r"^(?:能否|是否|可否)",
        reduced,
    ))


def creates_reply_obligation(text):
    """Public structural check for an explicit current reply obligation."""
    return _creates_reply_obligation(text)


def validate_semantic_ledger_events(
    events, text, expected_owner, *, drop_ungrounded=False,
    drop_nonrequests=False, normalize_tentative_commitments=False,
    normalize_owned_future_requests=False, drop_irrelevant=False,
    normalize_pending_commitments=False,
    drop_acceptance_commitments=False,
    normalization_log=None,
    drop_acceptance_events=False, active_proposals=None,
    require_assertion_mode=False,
):
    """Validate quote-grounded semantic events without inferring new content."""
    if not isinstance(events, list):
        raise ValueError("ledger_events must be a list")
    if normalization_log is None:
        normalization_log = []
    source = str(text).strip()
    normalized = []
    seen = set()
    for event in events:
        required_keys = set(LEDGER_EVENT_FIELDS) - {"assertion_mode"}
        allowed_keys = required_keys | {"assertion_mode"}
        if (
            not isinstance(event, dict)
            or not required_keys.issubset(event)
            or not set(event).issubset(allowed_keys)
            or (require_assertion_mode and "assertion_mode" not in event)
        ):
            raise ValueError(
                "each ledger event must contain event_type, owner, "
                "action_owner, evidence_span, status"
                + (", assertion_mode" if require_assertion_mode else "")
                + " and no other keys"
            )
        assertion_mode = event.get("assertion_mode", "asserted")
        if assertion_mode not in _ASSERTION_MODES:
            raise ValueError(f"ledger event assertion_mode is invalid: {assertion_mode!r}; allowed={sorted(_ASSERTION_MODES)}")
        preflight_span = event.get("evidence_span")
        preflight_grounded = (
            isinstance(preflight_span, str)
            and bool(preflight_span.strip())
            and _align_whitespace_variant_to_source(preflight_span, source) is not None
        )
        if drop_irrelevant and (
            event.get("owner") != expected_owner or not preflight_grounded
        ):
            reasons = []
            if event.get("owner") != expected_owner:
                reasons.append("owner_is_not_current_speaker")
            if not preflight_grounded:
                reasons.append("evidence_is_not_in_current_speaker_text")
            normalization_log.append({
                "operation": "drop_irrelevant_speaker_or_history_event",
                "reason": "+".join(reasons),
                "event": deepcopy(event),
            })
            continue
        if assertion_mode != "asserted":
            if event.get("owner") != expected_owner or not preflight_grounded:
                raise ValueError(
                    "non-asserted event candidates still require current-speaker "
                    "ownership and quote-grounded evidence"
                )
            normalization_log.append({
                "operation": "exclude_nonasserted_event_candidate",
                "reason": assertion_mode,
                "event": deepcopy(event),
            })
            continue
        raw_event_type = event["event_type"]
        event_type = {
            "inform": "claim",
            "statement": "claim",
            "question": "request",
            "challenge": "claim",
            "conditional_offer": "proposal",
            "conditional_commitment": "commitment",
            "tentative_plan": "proposal",
        }.get(raw_event_type, raw_event_type)
        status = event["status"]
        if raw_event_type == "conditional_offer" and status == "conditional":
            normalization_log.append({
                "operation": "normalize_conditional_offer_status",
                "reason": "conditional_offer_is_a_tentative_proposal",
                "event": deepcopy(event),
                "normalized_as": "proposal/tentative",
            })
            status = "tentative"
        if (
            event_type == "commitment"
            and status == "tentative"
            and normalize_tentative_commitments
        ):
            normalization_log.append({
                "operation": "downgrade_tentative_commitment_to_proposal",
                "reason": "tentative_status_is_not_a_firm_commitment",
                "event": deepcopy(event),
            })
            event_type = "proposal"
        if (
            drop_acceptance_events
            and preflight_grounded
            and _is_acceptance_only_event(
                source, event_type,
                _align_whitespace_variant_to_source(preflight_span, source),
                event.get("action_owner"), expected_owner, active_proposals,
            )
        ):
            legacy_acceptance_commitment = (
                event_type == "commitment"
                and drop_acceptance_commitments
                and re.search(
                    r"^(?:我|我们)(?:接受|同意|认可)(?:你|您|对方).{0,40}"
                    r"(?:提议|建议|方案|安排)[。！？]?$",
                    str(preflight_span).strip(),
                )
            )
            normalization_log.append({
                "operation": (
                    "drop_acceptance_mislabeled_as_commitment"
                    if legacy_acceptance_commitment
                    else "drop_acceptance_mislabeled_as_new_event"
                ),
                "reason": "acceptance_or_restatement_does_not_create_a_new_proposal_or_commitment",
                "event": deepcopy(event),
            })
            continue
        normalized_action_owner = None
        if (
            event_type == "commitment"
            and status in {"pending", "open"}
            and normalize_pending_commitments
        ):
            tentative = has_tentative_commitment_language(event["evidence_span"])
            normalization_log.append({
                "operation": "normalize_pending_commitment_status",
                "reason": "pending_is_ledger_storage_status_not_semantic_event_status",
                "event": deepcopy(event),
                "normalized_as": "proposal/tentative" if tentative else "commitment/firm",
            })
            if tentative:
                event_type = "proposal"
                status = "tentative"
            else:
                status = "firm"
        owned_request_is_typed_commitment = (
            event.get("action_owner") == expected_owner
            and status in {"firm", "conditional"}
        )
        lexical_owned_future = (
            isinstance(event.get("evidence_span"), str)
            and _FIRST_PERSON_COMMITMENT_PREFIX_RE.search(event["evidence_span"])
        )
        if (
            event_type == "request"
            and normalize_owned_future_requests
            and (owned_request_is_typed_commitment or lexical_owned_future)
        ):
            normalization_log.append({
                "operation": "normalize_owned_future_request_to_commitment",
                "reason": (
                    "request_status_and_action_owner_encode_speaker_commitment"
                    if owned_request_is_typed_commitment
                    else "first_person_future_action_is_not_a_request"
                ),
                "event": deepcopy(event),
            })
            event_type = "commitment"
            if status not in {"firm", "conditional"}:
                status = (
                    "conditional" if re.search(
                        r"(?:如果|若|遇到|有困难|有变化|有变动)", event["evidence_span"]
                    ) else "firm"
                )
            normalized_action_owner = expected_owner
        if (
            event_type == "commitment"
            and drop_acceptance_commitments
            and re.search(
                r"^(?:我|我们)(?:接受|同意|认可)(?:你|您|对方).{0,40}"
                r"(?:提议|建议|方案|安排)$",
                str(event.get("evidence_span", "")).strip(),
            )
        ):
            normalization_log.append({
                "operation": "drop_acceptance_mislabeled_as_commitment",
                "reason": "accepting_counterparty_proposal_is_not_owned_performance",
                "event": deepcopy(event),
            })
            continue
        if raw_event_type == "challenge" and status == "open":
            status = "reported"
        span = event["evidence_span"]
        if event_type not in _SEMANTIC_LEDGER_EVENT_STATUSES:
            if drop_irrelevant:
                normalization_log.append({
                    "operation": "drop_unsupported_ledger_event",
                    "reason": "unsupported_event_type_preserved_as_semantic_uncertainty",
                    "event": deepcopy(event),
                })
                continue
            raise ValueError(f"unsupported ledger event type {event_type!r}")
        if status not in _SEMANTIC_LEDGER_EVENT_STATUSES[event_type]:
            raise ValueError(f"invalid {event_type} status {status!r}")
        if event.get("owner") != expected_owner:
            raise ValueError("ledger event owner does not match the current speaker")
        if event.get("action_owner") not in ACTION_OWNERS:
            raise ValueError(f"ledger event action_owner is invalid: {event.get('action_owner')!r}; use role IDs, not names; allowed={sorted(ACTION_OWNERS)}")
        if event_type == "pause" and event.get("action_owner") != expected_owner:
            raise ValueError("pause event must be owned by its speaker")
        if not isinstance(span, str) or not span.strip():
            raise ValueError("ledger event evidence_span must be an exact non-empty utterance substring")
        span = _align_whitespace_variant_to_source(span, source)
        if span is None:
            if drop_ungrounded:
                normalization_log.append({
                    "operation": "drop_nonverbatim_ledger_event",
                    "reason": "evidence_span_not_in_current_speaker_text",
                    "event": deepcopy(event),
                })
                continue
            raise ValueError("ledger event evidence_span must be an exact non-empty utterance substring")
        if (
            event_type == "commitment"
            and normalize_tentative_commitments
            and has_tentative_commitment_language(span)
        ):
            normalization_log.append({
                "operation": "downgrade_tentative_commitment_to_proposal",
                "reason": "evidence_span_expresses_effort_or_intention_not_promise",
                "event": deepcopy(event),
            })
            event_type = "proposal"
            status = "tentative"
        if (
            event_type == "request"
            and drop_nonrequests
            and not _creates_reply_obligation(span)
            and not re.search(
                r"^(?:请)?(?:你|您)(?:先|再|现在|今天|直接|具体)", span.strip()
            )
        ):
            normalization_log.append({
                "operation": "drop_nonrequest_ledger_event",
                "reason": "evidence_span_has_no_current_request",
                "event": deepcopy(event),
            })
            continue
        key = (event_type, status, span)
        if key in seen:
            raise ValueError("duplicate ledger event")
        seen.add(key)
        action_owner = normalized_action_owner or event["action_owner"]
        if event_type == "request" and action_owner != "collective":
            action_owner = (
                "environment_agent"
                if expected_owner == "evaluated_agent"
                else "evaluated_agent"
            )
        normalized.append({
            "event_type": event_type,
            "owner": expected_owner,
            "action_owner": action_owner,
            "evidence_span": span,
            "status": status,
        })
    return normalized


def uncovered_owned_commitment_spans(text, events, speaker):
    """Find definite first-person future actions omitted from semantic events."""
    missing = []
    for match in _FIRST_PERSON_COMMITMENT_RE.finditer(str(text)):
        span = match.group(0).strip()
        if has_tentative_commitment_language(span) or re.search(
            r"(?:不|不能|无法|拒绝|暂不|先不).{0,6}(?:承诺|答应|保证)", span
        ):
            continue
        span_key = re.sub(r"\s+", "", span)
        covered = any(
            event.get("event_type") in {"commitment", "pause"}
            and event.get("owner") == speaker
            and event.get("action_owner") == speaker
            and (
                re.sub(r"\s+", "", str(event.get("evidence_span", ""))) in span_key
                or span_key in re.sub(r"\s+", "", str(event.get("evidence_span", "")))
            )
            for event in events
        )
        if not covered:
            missing.append(span)
    return missing
