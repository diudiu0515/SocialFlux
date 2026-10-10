"""Private, non-forcing opportunities for naturally observable slow evidence."""

from __future__ import annotations

from environment.delta_mapper import flatten_state
from environment.state_ontology import build_state_semantics


STATE_OPPORTUNITY_PROFILE_V1 = "state_transition_opportunity_v1"
STATE_OPPORTUNITY_PROFILE_V2 = "state_transition_opportunity_v2"
STATE_OPPORTUNITY_PROFILE_V3 = "state_transition_opportunity_v3"
STATE_OPPORTUNITY_PROFILE_V4 = "state_transition_opportunity_v4"
STATE_OPPORTUNITY_PROFILE_V5 = "state_transition_opportunity_event_driven_v5"
STATE_OPPORTUNITY_PROFILE_V6 = "state_transition_opportunity_event_driven_v6"
# Backward-compatible public names for v1/v2 evidence.
STATE_OPPORTUNITY_PROFILE = STATE_OPPORTUNITY_PROFILE_V1
STATE_OPPORTUNITY_TRIGGER_TURNS = (8, 12, 16)
STATE_OPPORTUNITY_V3_TRIGGER_TURNS = (6, 10, 14, 18)
STATE_OPPORTUNITY_V4_TRIGGER_TURNS = (4, 7, 10, 13, 16, 19)


def _trigger_turns(profile):
    if profile in {STATE_OPPORTUNITY_PROFILE_V5, STATE_OPPORTUNITY_PROFILE_V6}:
        return ()
    if profile == STATE_OPPORTUNITY_PROFILE_V4:
        return STATE_OPPORTUNITY_V4_TRIGGER_TURNS
    if profile == STATE_OPPORTUNITY_PROFILE_V3:
        return STATE_OPPORTUNITY_V3_TRIGGER_TURNS
    return STATE_OPPORTUNITY_TRIGGER_TURNS


def _inactive(
    turn_id, reason, slow_paths=(), *, profile=STATE_OPPORTUNITY_PROFILE_V1,
    trigger_turns=None,
):
    if trigger_turns is None:
        trigger_turns = _trigger_turns(profile)
    return {
        "profile": profile,
        "active": False,
        "turn_id": int(turn_id),
        "trigger_turns": list(trigger_turns),
        "reason": reason,
        "eligible_slow_paths": list(slow_paths),
    }


def _changed_paths(turns, current_numeric_delta):
    changed = set()
    deltas = [
        turn.get("numeric_state_delta") or {}
        for turn in turns or []
    ]
    deltas.append(current_numeric_delta or {})
    for delta in deltas:
        for path, value in flatten_state(delta).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value:
                changed.add(path)
    return changed


def _slow_evidence_strands(turns, slow_paths):
    """Summarize unresolved evidence without exposing its desired direction.

    Calibration remains the sole owner of whether two observations are
    independent and directionally consistent.  This summary only lets the
    response stage avoid repeatedly opening unrelated constructs.
    """
    allowed = set(slow_paths)
    evidence = {path: {} for path in slow_paths}
    turn_ids = {path: set() for path in slow_paths}
    for turn in turns or []:
        calibration = turn.get("calibration") or {}
        for item in calibration.get("state_impacts") or []:
            path = item.get("variable")
            direction = item.get("direction")
            if (
                path not in allowed
                or direction not in {"increase", "decrease"}
                or item.get("timescale") != "cross_turn_slow"
                or not item.get("explicit_evidence")
                or not item.get("feature_compatible")
                or not item.get("new_evidence")
                or item.get("calibrated_level", 0) <= 0
            ):
                continue
            key = (
                turn.get("turn_id"),
                item.get("evidence_feature"),
                item.get("evidence_span"),
            )
            evidence[path].setdefault(direction, set()).add(key)
            if turn.get("turn_id") is not None:
                turn_ids[path].add(str(turn["turn_id"]))
    result = {}
    for path in slow_paths:
        counts = [len(values) for values in evidence[path].values()]
        result[path] = {
            "candidate_count": sum(counts),
            "max_consistent_candidate_count": max(counts, default=0),
            "candidate_turn_ids": sorted(turn_ids[path]),
        }
    return result


def _neutral_evidence_pattern(value):
    text = str(value or "").strip()
    for marker in (", causing ", " causing ", "，导致", "导致"):
        if marker in text:
            text = text.split(marker, 1)[0].strip()
            break
    return text


def _select_v2_path(slow_paths, turns, trigger_index):
    strands = _slow_evidence_strands(turns, slow_paths)
    with_prior = [
        path for path in slow_paths
        if strands[path]["max_consistent_candidate_count"] > 0
    ]
    if with_prior:
        order = {path: index for index, path in enumerate(slow_paths)}
        path = max(
            with_prior,
            key=lambda item: (
                strands[item]["max_consistent_candidate_count"],
                -order[item],
            ),
        )
        return path, strands[path], "existing_unresolved_slow_evidence"
    path = slow_paths[trigger_index % len(slow_paths)]
    return path, strands[path], "sparse_cadence"


def build_state_transition_opportunity(
    scenario, turns, current_numeric_delta, turn_id,
    *, profile=STATE_OPPORTUNITY_PROFILE_V1,
):
    """Expose optional context for naturally observable slow evidence.

    This never edits state, asks for a direction, or treats an authored example as
    observed evidence.  It only gives the private environment response model a
    chance to surface a grounded unresolved issue before the next policy action.
    """
    if profile not in {
        STATE_OPPORTUNITY_PROFILE_V1,
        STATE_OPPORTUNITY_PROFILE_V2,
        STATE_OPPORTUNITY_PROFILE_V3,
        STATE_OPPORTUNITY_PROFILE_V4,
        STATE_OPPORTUNITY_PROFILE_V5,
        STATE_OPPORTUNITY_PROFILE_V6,
    }:
        raise ValueError(f"unsupported state opportunity profile {profile!r}")
    trigger_turns = _trigger_turns(profile)
    semantics = build_state_semantics(scenario)["variables"]
    slow_paths = sorted(
        path for path, value in semantics.items()
        if value.get("timescale") == "cross_turn_slow"
    )
    if not slow_paths:
        return _inactive(
            turn_id, "no_selected_slow_path", profile=profile,
            trigger_turns=trigger_turns,
        )
    if profile in {STATE_OPPORTUNITY_PROFILE_V5, STATE_OPPORTUNITY_PROFILE_V6}:
        changed = _changed_paths(turns, current_numeric_delta)
        if any(path in changed for path in slow_paths):
            return _inactive(
                turn_id,
                "slow_transition_already_realized",
                slow_paths,
                profile=profile,
                trigger_turns=trigger_turns,
            )
        strands = _slow_evidence_strands(turns, slow_paths)
        has_prior_candidate = any(
            value["max_consistent_candidate_count"] > 0
            for value in strands.values()
        )
        eligible_constructs = []
        for path in slow_paths:
            item = {
                "path": path,
                "construct_definition": semantics[path].get("definition", ""),
                **strands[path],
            }
            if profile == STATE_OPPORTUNITY_PROFILE_V6:
                guides = semantics[path].get("scenario_transition_evidence") or {}
                item["scenario_evidence_patterns"] = [
                    pattern
                    for pattern in (
                        _neutral_evidence_pattern(guides.get("increase_evidence")),
                        _neutral_evidence_pattern(guides.get("decrease_evidence")),
                    )
                    if pattern
                ]
            eligible_constructs.append(item)
        return {
            "profile": profile,
            "active": True,
            "activation_mode": "event_driven_prompt",
            "turn_id": int(turn_id),
            "trigger_turns": [],
            "reason": "prompt_decides_from_current_public_context",
            "eligible_slow_paths": list(slow_paths),
            "eligible_constructs": eligible_constructs,
            "evidence_stage": (
                "independent_followup"
                if has_prior_candidate else "open_probe"
            ),
            "followup_guidance": (
                "Only if a genuinely different public situation, choice, or "
                "trade-off already follows naturally from the live exchange, "
                "the response may let the evaluated agent answer freely. Do "
                "not repeat, summarize, or seek confirmation of prior evidence."
                if has_prior_candidate else
                "Only when the live public exchange already makes one construct "
                "relevant, the response may surface one non-leading uncertainty, "
                "choice, or trade-off. Otherwise ignore this context."
            ),
            "guardrails": [
                "not a task, schedule, state-coverage target, or requirement to change",
                "answer the current action before considering a new issue",
                "choose at most one construct only when grounded in the live public exchange",
                "do not reveal state paths, request a direction, or copy authored examples",
                "do not introduce an issue merely because a construct is eligible",
                "only a later exact evaluated-agent utterance may become evidence",
            ],
        }
    if turn_id not in trigger_turns:
        return _inactive(
            turn_id,
            "off_sparse_trigger_cadence",
            slow_paths,
            profile=profile,
            trigger_turns=trigger_turns,
        )

    changed = _changed_paths(turns, current_numeric_delta)
    if any(path in changed for path in slow_paths):
        return _inactive(
            turn_id,
            "slow_transition_already_realized",
            slow_paths,
            profile=profile,
            trigger_turns=trigger_turns,
        )

    trigger_index = trigger_turns.index(turn_id)
    if profile in {
        STATE_OPPORTUNITY_PROFILE_V2,
        STATE_OPPORTUNITY_PROFILE_V3,
        STATE_OPPORTUNITY_PROFILE_V4,
    }:
        path, strand, selection_basis = _select_v2_path(
            slow_paths, turns, trigger_index
        )
    else:
        path = slow_paths[trigger_index % len(slow_paths)]
        strand = {
            "candidate_count": 0,
            "max_consistent_candidate_count": 0,
            "candidate_turn_ids": [],
        }
        selection_basis = "sparse_cadence"
    guides = semantics[path].get("scenario_transition_evidence") or {}
    result = {
        "profile": profile,
        "active": True,
        "turn_id": int(turn_id),
        "trigger_turns": list(trigger_turns),
        "reason": "selected_slow_paths_have_no_realized_change",
        "selected_path": path,
        "construct_definition": semantics[path].get("definition", ""),
        "increase_example": guides.get("increase_evidence", ""),
        "decrease_example": guides.get("decrease_evidence", ""),
        "guardrails": [
            "optional opportunity only; not a coverage target",
            "answer the current action before surfacing another issue",
            "use only a concern, uncertainty, question, or trade-off grounded in public context",
            "do not assert that either authored example occurred",
            "do not request a particular state direction or copy exemplar wording",
            "the next evaluated action still needs its own exact evidence",
        ],
    }
    if profile in {
        STATE_OPPORTUNITY_PROFILE_V2,
        STATE_OPPORTUNITY_PROFILE_V3,
        STATE_OPPORTUNITY_PROFILE_V4,
    }:
        prior_count = strand["max_consistent_candidate_count"]
        result.update({
            "selection_basis": selection_basis,
            "evidence_stage": (
                "independent_followup"
                if prior_count > 0 else "open_probe"
            ),
            "prior_candidate_count": prior_count,
            "prior_candidate_turn_ids": strand["candidate_turn_ids"],
            "followup_guidance": (
                "If natural after answering the current action, use one new "
                "publicly grounded situation, choice, or trade-off that is "
                "different from the earlier candidate context and lets the "
                "evaluated agent answer freely. Do not seek confirmation, "
                "repeat prior evidence, or imply a preferred direction."
                if prior_count > 0 else
                "If natural after answering the current action, surface one "
                "concrete, non-leading, publicly grounded uncertainty, choice, "
                "or trade-off through which the construct may become observable."
            ),
        })
    return result
