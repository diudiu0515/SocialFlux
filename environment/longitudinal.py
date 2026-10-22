"""Deterministic multi-segment time and public-event progression.

Scenario-authored event possibilities are selected once at reset and stored in
the private snapshot. No event is created by an LLM and elapsed time alone has
no effect unless the scenario explicitly authors a separate time effect.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from .interaction_ledger import _response_disposition
import re

from .delta_mapper import apply_semantic_deltas


_EXPLICIT_PAUSE_RE = re.compile(
    r"(?:先这样|今天先到这里|暂时到这里|之后再谈|到时候再(?:说|联系)|"
    r"改天再谈|等.{0,18}(?:到了|有结果|有消息|到账).{0,10}再(?:说|联系|确认)|"
    r"按这个安排|就这么定|先按.{0,16}(?:执行|处理))"
)


def _stable_index(*parts, size):
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return int(hashlib.sha256(payload).hexdigest(), 16) % size


def _neutral_delta(values):
    return {
        key: _neutral_delta(value) if isinstance(value, dict) else "similar"
        for key, value in values.items()
    }


def _set_delta_path(delta, values, path, label):
    keys = path.split(".")
    delta_cursor = delta
    value_cursor = values
    for key in keys[:-1]:
        if key not in value_cursor or not isinstance(value_cursor[key], dict):
            raise ValueError(f"longitudinal effect references unknown group: {path}")
        value_cursor = value_cursor[key]
        delta_cursor = delta_cursor[key]
    leaf = keys[-1]
    if leaf not in value_cursor or isinstance(value_cursor[leaf], dict):
        raise ValueError(f"longitudinal effect references unknown variable: {path}")
    delta_cursor[leaf] = label


def _apply_sparse_effect(values, sparse_effect):
    semantic = _neutral_delta(values)
    for path, label in (sparse_effect or {}).items():
        _set_delta_path(semantic, values, path, label)
    updated, numeric = apply_semantic_deltas(values, semantic)
    return updated, semantic, numeric


def _event_plan(design, scenario_id, trajectory_id):
    selected = {}
    for pool in design.get("event_pools", []):
        outcomes = pool.get("outcomes", [])
        if not outcomes:
            continue
        index = _stable_index(
            scenario_id,
            trajectory_id,
            pool["event_pool_id"],
            size=len(outcomes),
        )
        selected[pool["event_pool_id"]] = deepcopy(outcomes[index])
    canonical = json.dumps(selected, ensure_ascii=False, sort_keys=True)
    return {
        "selection": "sha256_scenario_policy_sampling_pool",
        "selected_outcomes": selected,
        "plan_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def _runtime_segment(segment, *, started_after_turn, planned_end_turn, next_segment=None, time_unit="turn"):
    record = {
        "segment_id": segment["segment_id"],
        "reason": segment["reason"],
        "started_after_turn": started_after_turn,
        "planned_end_turn": planned_end_turn,
        "interaction_goal": segment.get("interaction_goal", ""),
        "all_live_questions": deepcopy(segment.get("live_questions", [])),
        "resolved_live_questions": [],
        "live_questions": deepcopy(segment.get("live_questions", [])),
        "pause_when": segment.get("pause_when", ""),
        "forbid_new_repayment_commitment": bool(
            segment.get("forbid_new_repayment_commitment", False)
        ),
    }
    if next_segment is not None:
        record["next_interaction"] = {
            "known_schedule": True,
            "after": int(next_segment["advance_by"]),
            "unit": time_unit,
            "reason": next_segment["reason"],
        }
    return record


def initialize_longitudinal_session(scenario, trajectory_id, event_selection_key=None):
    design = deepcopy(scenario.get("longitudinal_design") or {})
    segments = design.get("segments") or []
    if not segments:
        return {
            "longitudinal_enabled": False,
            "elapsed_time": 0,
            "time_unit": "turn",
            "segment_index": 0,
            "segment_turn_id": 0,
            "current_segment": {
                "segment_id": "single_interaction",
                "reason": "single continuous interaction",
                "started_after_turn": 0,
                "planned_end_turn": scenario.get("max_turns", 20),
            },
            "segments": [],
            "public_timeline": [],
            "event_plan": {"selection": "none", "selected_outcomes": {}, "plan_hash": None},
            "counterfactual_timeline_lock": False,
        }

    first = deepcopy(segments[0])
    current = _runtime_segment(
        first,
        started_after_turn=0,
        planned_end_turn=int(first["max_turns"]),
        next_segment=segments[1] if len(segments) > 1 else None,
        time_unit=design["time_unit"],
    )
    return {
        "longitudinal_enabled": True,
        "elapsed_time": int(design.get("start_elapsed", 0)),
        "time_unit": design["time_unit"],
        "segment_index": 0,
        "segment_turn_id": 0,
        "current_segment": current,
        "segments": [{
            **deepcopy(current),
            "start_elapsed_time": int(design.get("start_elapsed", 0)),
            "status": "active",
        }],
        "public_timeline": [],
        "event_plan": _event_plan(
            design,
            scenario["scenario_id"],
            event_selection_key or trajectory_id,
        ),
        "counterfactual_timeline_lock": False,
        "numeric_obligation": (
            {
                **deepcopy(design.get("numeric_obligation", {})),
                "current_amount": int(
                    design.get("numeric_obligation", {}).get("initial_amount", 0)
                ),
            }
            if design.get("numeric_obligation") else None
        ),
    }


def public_longitudinal_view(session):
    current = deepcopy(session.get("current_segment", {}))
    segment_turn = int(session.get("segment_turn_id", 0))
    live_questions = deepcopy(current.get("live_questions", []))
    turn_guidance = {
        "mode": "optional_discussion_space",
        "suggested_live_question": "",
        "instruction": (
            "Live questions describe possible discussion space only. Follow the "
            "latest exchange; do not select a question merely because it remains listed."
        ),
        "hard_gate": False,
    }
    view = {
        "trajectory_unit": "same_people_relationship_shared_history",
        "segment": {
            "segment_id": current.get("segment_id", "single_interaction"),
            "segment_index": int(session.get("segment_index", 0)) + 1,
            "segment_turn_id": segment_turn,
            "reason": current.get("reason", ""),
            "interaction_goal": current.get("interaction_goal", ""),
            "all_live_questions": deepcopy(current.get("all_live_questions", live_questions)),
            "resolved_live_questions": deepcopy(current.get("resolved_live_questions", [])),
            "live_questions": live_questions,
            "turn_guidance": turn_guidance,
            "pause_when": current.get("pause_when", ""),
            "terminal_fragment": not bool(current.get("next_interaction")),
            "turns_remaining_in_fragment": max(
                0,
                int(current.get("planned_end_turn", session.get("turn_id", 0)))
                - int(session.get("turn_id", 0)),
            ),
            "forbid_new_repayment_commitment": bool(
                current.get("forbid_new_repayment_commitment", False)
            ),
        },
        "time": {
            "elapsed": session.get("elapsed_time", 0),
            "unit": session.get("time_unit", "turn"),
        },
        "public_timeline": deepcopy(session.get("public_timeline", [])),
    }
    if current.get("next_interaction"):
        view["next_interaction"] = deepcopy(current["next_interaction"])
    return view


def _commitment_has_required_terms(item, required_terms):
    text = " ".join(str(item.get(key, "")) for key in ("text", "object"))
    checks = {
        "amount": bool(item.get("amounts")) or bool(re.search(
            r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十百千万]+)"
            r"\s*(?:元|块|千|万)", text
        )),
        "deadline": bool(re.search(
            r"(?:今天|明天|后天|本周|下周|本月|下月|月底|月初|"
            r"(?:\d+|[一二两三四五六七八九十]+)\s*(?:小时|天)(?:后|内))",
            text,
        )) or bool(re.search(
            r"(?:\d+|[一二两三四五六七八九十]+)\s*天"
            r"(?=[^。；]{0,8}(?:还|转(?:给|账|出)?|付款|汇款))", text
        )),
        "repayment_action": (
            item.get("semantic_event_type") == "commitment"
            and item.get("action_owner") == item.get("speaker")
            and item.get("focus") == "practical_execution"
        ) or bool(re.search(
            r"(?:还给|还款|还钱|还你|还清|偿还|转账|转出|汇款|付款|支付|"
            r"补上|归还|先还|再还|转给)", text,
        )),
    }
    return all(checks.get(term, False) for term in required_terms or [])


def _has_pending_commitment(ledger, speaker, focus, required_terms=None):
    return any(
        item.get("speaker") == speaker
        and item.get("status") == "pending"
        and not (
            item.get("commitment_strength") == "conditional"
            and item.get("condition_status") != "satisfied_by_public_event"
        )
        and (not focus or item.get("focus") == focus)
        and _commitment_has_required_terms(item, required_terms)
        for item in (ledger or {}).get("commitments", [])
    )


def _accumulate_live_question_progress(
    session, action_text, response_text, appraisal=None
):
    current = session.get("current_segment", {})
    all_questions = list(current.get("all_live_questions", []))
    if not all_questions:
        return
    if _response_disposition(response_text, action_text) != "direct":
        return
    after_direct = (
        (appraisal or {}).get("dialogue_diagnostics", {})
        .get("continuation", {}).get("after_direct_response", {})
    )
    supported = set(after_direct.get("resolved_live_questions", []))
    existing = set(current.get("resolved_live_questions", []))
    resolved = [
        item for item in all_questions if item in existing or item in supported
    ]
    current["resolved_live_questions"] = resolved
    current["live_questions"] = [
        item for item in all_questions if item not in set(resolved)
    ]
    if session.get("segments"):
        session["segments"][-1]["resolved_live_questions"] = deepcopy(resolved)
        session["segments"][-1]["live_questions"] = deepcopy(
            current["live_questions"]
        )


def _should_advance(
    session, segment, action_text, response_text, appraisal=None,
    response_events=None, final_segment=False,
):
    local_turn = int(session.get("segment_turn_id", 0))
    if session.get("counterfactual_timeline_lock"):
        # T3 branches share one authored external timeline.  A deterministic
        # segment boundary may advance that frozen timeline identically across
        # candidate actions, but ordinary online rollouts never advance merely
        # because a conversational turn cap was reached.
        if local_turn >= int(segment["max_turns"]) and not final_segment:
            return True, "counterfactual_timeline_boundary"
        return False, None
    if local_turn < int(segment.get("min_turns", 1)):
        return False, None
    if segment.get("end_on_pending_commitment") and _has_pending_commitment(
        session.get("interaction_ledger", {}),
        segment.get("commitment_speaker", "environment_agent"),
        segment.get("commitment_focus"),
        segment.get("commitment_required_terms", []),
    ):
        return True, "pending_commitment_with_future_node"
    semantic_pause = any(
        event.get("event_type") == "pause" and event.get("status") == "explicit"
        for event in (response_events or [])
    )
    no_reply_obligation = not (
        session.get("interaction_ledger", {}).get("latest_obligation")
    )
    if segment.get("allow_explicit_pause", True) and (
        semantic_pause or _EXPLICIT_PAUSE_RE.search(f"{action_text}\n{response_text}")
    ) and no_reply_obligation:
        return True, "explicit_dialogue_pause"
    continuation = (
        (appraisal or {}).get("dialogue_diagnostics", {}).get("continuation", {})
    )
    if (
        final_segment
        and segment.get("allow_semantic_pause", True)
        and continuation.get("status") == "can_close"
        and no_reply_obligation
    ):
        return True, "appraisal_semantic_final_pause"
    if (
        segment.get("allow_semantic_pause", True)
        and continuation.get("status") == "can_close"
        and no_reply_obligation
    ):
        return True, "appraisal_semantic_pause"
    after_direct = continuation.get("after_direct_response", {})
    if (
        segment.get("allow_semantic_pause", True)
        and continuation.get("status") in {"must_answer", "continue"}
        and after_direct.get("status") == "can_close"
        and _response_disposition(response_text, action_text) == "direct"
        and no_reply_obligation
    ):
        return True, "appraisal_direct_answer_pause"
    return False, None


def _select_pending_commitment(ledger, outcome, required_terms=None):
    speaker = outcome.get("commitment_speaker", "environment_agent")
    focus = outcome.get("commitment_focus")
    for item in reversed((ledger or {}).get("commitments", [])):
        if item.get("speaker") != speaker or item.get("status") != "pending":
            continue
        if (
            item.get("commitment_strength") == "conditional"
            and item.get("condition_status") != "satisfied_by_public_event"
        ):
            continue
        if focus and item.get("focus") != focus:
            continue
        if not _commitment_has_required_terms(item, required_terms):
            continue
        return item
    return None


def _commitment_amount(item):
    promised = str(item.get("object") or item.get("text", ""))
    stated_total = re.search(
        r"(?:共计|合计|总计|总共|共)\s*(\d+(?:\.\d+)?)\s*(?:元|块)",
        promised,
    )
    if stated_total:
        return float(stated_total.group(1))
    part_of_balance = re.search(
        r"(?:剩余|尚欠|还欠|欠款)[^。；]{0,16}?\d+(?:\.\d+)?\s*(?:元|块)"
        r"[^。；]{0,6}?(?:中(?:的)?|里面(?:的)?|其中)\s*"
        r"(\d+(?:\.\d+)?)\s*(?:元|块)",
        promised,
    )
    if part_of_balance:
        return float(part_of_balance.group(1))
    match = re.search(
        r"(?:还给|还你|还钱|还清|偿还|支付|转账|转出|汇款|付款|补上|还)"
        r"[^\d。；]{0,10}(\d+(?:\.\d+)?)\s*(?:元|块)",
        promised,
    )
    if match:
        return float(match.group(1))
    reverse = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:元|块)[^。；]{0,10}"
        r"(?:还给|还款|还钱|还你|还清|偿还|转账|转出|汇款|付款|支付|补上|归还)",
        promised,
    )
    return float(reverse.group(1)) if reverse else None


def _display_amount(value):
    value = float(value)
    return str(int(value)) if value.is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")


def _materialize_numeric_outcome(session, outcome, commitment):
    rendered = deepcopy(outcome)
    obligation = session.get("numeric_obligation")
    committed = _commitment_amount(commitment or {})
    if not obligation or committed is None:
        return rendered
    effect = outcome.get("commitment_effect", "none")
    fraction = float(outcome.get("performance_fraction", {
        "fulfilled": 1.0,
        "partially_fulfilled": 0.5,
        "unfulfilled": 0.0,
    }.get(effect, 0.0)))
    performed = min(committed, max(0.0, committed * fraction))
    before = float(obligation.get("current_amount", 0))
    after = max(0.0, before - performed)
    obligation["current_amount"] = int(after) if after.is_integer() else after
    due = _display_amount(committed)
    paid = _display_amount(performed)
    unpaid = _display_amount(committed - performed)
    balance = _display_amount(after)
    if effect == "fulfilled":
        record = (
            f"公开转账记录显示：本节点约定的{due}元已经足额到账；"
            f"剩余未还金额为{balance}元。"
        )
    elif effect == "partially_fulfilled":
        record = (
            f"公开转账记录显示：本节点约定{due}元，实际到账{paid}元，"
            f"该笔仍有{unpaid}元未履行；剩余未还金额为{balance}元。"
        )
    elif effect == "unfulfilled":
        record = (
            f"公开转账记录显示：本节点约定的{due}元没有到账；"
            f"剩余未还金额仍为{balance}元。"
        )
    else:
        return rendered
    rendered["public_record"] = record
    rendered["numeric_performance"] = {
        "currency": obligation.get("currency", "CNY"),
        "committed_amount": committed,
        "performed_amount": performed,
        "unperformed_amount": committed - performed,
        "balance_before": before,
        "balance_after": after,
        "calculation": "deterministic_from_public_commitment_and_authored_outcome_fraction",
    }
    return rendered


def _record_commitment_outcome(
    ledger, outcome, event_id, elapsed_time, required_terms=None
):
    result = deepcopy(ledger)
    effect = outcome.get("commitment_effect", "none")
    if effect == "none":
        return result, None
    speaker = outcome.get("commitment_speaker", "environment_agent")
    selected_source = _select_pending_commitment(result, outcome, required_terms)
    selected = selected_source
    if selected is None:
        return result, None
    selected.setdefault("performance_events", []).append({
        "event_id": event_id,
        "elapsed_time": elapsed_time,
        "outcome": effect,
        "evidence": outcome["public_record"],
    })
    selected["performance_status"] = effect
    selected["status"] = {
        "fulfilled": "completed_by_public_event",
        "partially_fulfilled": "partially_fulfilled_by_public_event",
        "unfulfilled": "unfulfilled_by_public_event",
    }.get(effect, "resolved_by_public_event")
    if effect == "fulfilled":
        result.setdefault("progress", {})["completed_commitment_count"] = int(
            result.get("progress", {}).get("completed_commitment_count", 0)
        ) + 1
    for companion in result.get("commitments", []):
        if (
            companion.get("speaker") == speaker
            and companion.get("status") == "pending"
            and companion.get("focus") == "communication_boundary"
        ):
            companion["status"] = (
                "condition_not_observed_by_public_event"
                if effect == "fulfilled"
                else "performance_not_established_by_public_event"
            )
            companion.setdefault("performance_events", []).append({
                "event_id": event_id,
                "elapsed_time": elapsed_time,
                "outcome": "not_adjudicated",
                "evidence": outcome["public_record"],
            })
    return result, selected.get("id")


def _event_entry(event_id, event_type, text, elapsed_time, unit, **extra):
    return {
        "event_id": event_id,
        "evidence_id": f"event:{event_id}",
        "event_type": event_type,
        "source": "scenario_authored_schedule",
        "public": True,
        "elapsed_time": elapsed_time,
        "time_unit": unit,
        "text": str(text).strip(),
        **extra,
    }


def maybe_advance_segment(
    scenario, session, *, action_text, response_text, appraisal=None,
    response_events=None,
):
    """Advance between fragments after a completed model-response turn.

    Returns a private transition log or ``None``. All numeric changes here are
    deterministic scenario effects and occur after the response LLM call.
    """
    design = scenario.get("longitudinal_design") or {}
    segments = design.get("segments") or []
    index = int(session.get("segment_index", 0))
    if not session.get("longitudinal_enabled") or index >= len(segments):
        return None
    segment = segments[index]
    _accumulate_live_question_progress(
        session, action_text, response_text, appraisal
    )
    should_advance, reason = _should_advance(
        session, segment, action_text, response_text, appraisal, response_events,
        final_segment=index == len(segments) - 1,
    )
    if not should_advance:
        return None

    if index == len(segments) - 1:
        session["segments"][-1].update({
            "status": "completed",
            "ended_after_turn": session["turn_id"],
            "end_elapsed_time": session.get("elapsed_time", 0),
            "end_reason": reason,
        })
        session["status"] = "completed"
        session["ending"] = {
            "reason": "natural_completion",
            "turn_id": session["turn_id"],
        }
        return {
            "transition_id": f"{segment['segment_id']}--to--terminal",
            "from_segment_id": segment["segment_id"],
            "to_segment_id": None,
            "boundary_reason": reason,
            "terminal": True,
            "elapsed_before": session.get("elapsed_time", 0),
            "elapsed_after": session.get("elapsed_time", 0),
            "time_unit": design["time_unit"],
            "public_events": [],
        }

    next_segment = segments[index + 1]
    elapsed_before = int(session.get("elapsed_time", 0))
    elapsed_after = elapsed_before + int(next_segment["advance_by"])
    state_before = deepcopy(session["state"])
    dynamics_before = deepcopy(session["dynamics"])

    time_effect = next_segment.get("time_effect", {})
    state_after_time, time_state_delta, time_state_numeric = _apply_sparse_effect(
        state_before, time_effect.get("state_delta", {})
    )
    dynamics_after_time, time_dynamics_delta, time_dynamics_numeric = _apply_sparse_effect(
        dynamics_before, time_effect.get("dynamics_delta", {})
    )

    transition_id = f"{segment['segment_id']}--to--{next_segment['segment_id']}"
    unit = design["time_unit"]
    public_events = [_event_entry(
        f"{transition_id}:time",
        "time_advance",
        next_segment["public_time_record"],
        elapsed_after,
        unit,
        elapsed_from=elapsed_before,
        elapsed_to=elapsed_after,
        reason=next_segment["reason"],
        time_only_effect=time_effect.get("policy", "none"),
    )]

    outcome = None
    event_state_effect = {}
    event_dynamics_effect = {}
    pool_id = next_segment.get("event_pool_id")
    precondition_met = True
    if next_segment.get("requires_pending_commitment"):
        precondition_met = _has_pending_commitment(
            session.get("interaction_ledger", {}),
            next_segment.get("commitment_speaker", "environment_agent"),
            next_segment.get("commitment_focus"),
            next_segment.get("commitment_required_terms", []),
        )
    if pool_id and precondition_met:
        outcome = deepcopy(
            session.get("event_plan", {}).get("selected_outcomes", {}).get(pool_id)
        )
    if outcome:
        selected_commitment = _select_pending_commitment(
            session.get("interaction_ledger", {}), outcome,
            next_segment.get("commitment_required_terms", []),
        )
        outcome = _materialize_numeric_outcome(
            session, outcome, selected_commitment
        )
        event_id = f"{transition_id}:{outcome['outcome_id']}"
        public_events.append(_event_entry(
            event_id,
            "commitment_performance" if outcome.get("commitment_effect") != "none" else "scheduled_event",
            outcome["public_record"],
            elapsed_after,
            unit,
            outcome_id=outcome["outcome_id"],
            causal_scope=outcome.get("causal_scope", "exogenous"),
            numeric_performance=deepcopy(outcome.get("numeric_performance")),
        ))
        event_state_effect = outcome.get("state_delta", {})
        event_dynamics_effect = outcome.get("dynamics_delta", {})
        ledger_after, commitment_id = _record_commitment_outcome(
            session["interaction_ledger"], outcome, event_id, elapsed_after,
            next_segment.get("commitment_required_terms", []),
        )
    elif pool_id:
        event_id = f"{transition_id}:precondition_not_met"
        fallback = next_segment.get(
            "precondition_not_met_record",
            "此前没有形成可核验的明确承诺；双方因问题仍未解决而再次联系。",
        )
        public_events.append(_event_entry(
            event_id,
            "scheduled_recontact",
            fallback,
            elapsed_after,
            unit,
            outcome_id="precondition_not_met",
            causal_scope="dialogue_contingent",
        ))
        ledger_after = deepcopy(session["interaction_ledger"])
        commitment_id = None
    else:
        # A scheduled recontact without an event pool is only a time/interaction
        # boundary. It must not fabricate a failed commitment precondition.
        ledger_after = deepcopy(session["interaction_ledger"])
        commitment_id = None

    state_after, event_state_delta, event_state_numeric = _apply_sparse_effect(
        state_after_time, event_state_effect
    )
    dynamics_after, event_dynamics_delta, event_dynamics_numeric = _apply_sparse_effect(
        dynamics_after_time, event_dynamics_effect
    )

    for event in public_events:
        ledger_after.setdefault("established_facts", []).append({
            "id": event["evidence_id"],
            "speaker": "public_record",
            "turn_id": f"after_t{session['turn_id']}",
            "text": event["text"],
            "event_id": event["event_id"],
        })
        session["history"].append({
            "turn_id": session["turn_id"],
            "role": "public_event",
            "text": event["text"],
            "evidence_id": event["evidence_id"],
            "event_id": event["event_id"],
            "elapsed_time": elapsed_after,
            "time_unit": unit,
        })

    reentry = str(
        next_segment.get("precondition_not_met_opening_response")
        if pool_id and outcome is None
        else next_segment["opening_response"]
    ).strip()
    opening_event_id = f"{transition_id}:opening"
    opening_event = _event_entry(
        opening_event_id,
        "segment_opening",
        reentry,
        elapsed_after,
        unit,
        speaker="environment_agent",
    )
    public_events.append(opening_event)
    session["history"].append({
        "turn_id": session["turn_id"],
        "role": "environment_agent",
        "text": reentry,
        "evidence_id": opening_event["evidence_id"],
        "event_id": opening_event_id,
        "elapsed_time": elapsed_after,
        "time_unit": unit,
    })

    session["segments"][-1].update({
        "status": "paused",
        "ended_after_turn": session["turn_id"],
        "end_elapsed_time": elapsed_before,
        "end_reason": reason,
    })
    following_segment = segments[index + 2] if index + 2 < len(segments) else None
    current = _runtime_segment(
        next_segment,
        started_after_turn=session["turn_id"],
        planned_end_turn=session["turn_id"] + int(next_segment["max_turns"]),
        next_segment=following_segment,
        time_unit=unit,
    )
    session["segment_index"] = index + 1
    session["segment_turn_id"] = 0
    session["current_segment"] = current
    session["segments"].append({
        **deepcopy(current),
        "start_elapsed_time": elapsed_after,
        "status": "active",
    })
    session["elapsed_time"] = elapsed_after
    session["state"] = state_after
    session["dynamics"] = dynamics_after
    session["interaction_ledger"] = ledger_after
    session["current_response"] = reentry
    session["public_timeline"].extend(deepcopy(public_events))

    return {
        "transition_id": transition_id,
        "from_segment_id": segment["segment_id"],
        "to_segment_id": next_segment["segment_id"],
        "boundary_reason": reason,
        "elapsed_before": elapsed_before,
        "elapsed_after": elapsed_after,
        "time_unit": unit,
        "public_events": public_events,
        "event_plan_hash": session.get("event_plan", {}).get("plan_hash"),
        "selected_outcome_id": (
            outcome.get("outcome_id") if outcome
            else ("precondition_not_met" if pool_id else None)
        ),
        "commitment_id": commitment_id,
        "state_before_time": state_before,
        "time_state_delta": time_state_delta,
        "numeric_time_state_delta": time_state_numeric,
        "state_after_time": state_after_time,
        "event_state_delta": event_state_delta,
        "numeric_event_state_delta": event_state_numeric,
        "state_after_events": state_after,
        "dynamics_before_time": dynamics_before,
        "time_dynamics_delta": time_dynamics_delta,
        "numeric_time_dynamics_delta": time_dynamics_numeric,
        "dynamics_after_time": dynamics_after_time,
        "event_dynamics_delta": event_dynamics_delta,
        "numeric_event_dynamics_delta": event_dynamics_numeric,
        "dynamics_after_events": dynamics_after,
    }
