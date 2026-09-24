"""Shared helpers for the two dialogue speakers.

This module contains only speaker-neutral prompt context.  Policy generation
and environment-response generation keep their own role-specific contracts
and validators.
"""

from __future__ import annotations

import re

from .interaction_ledger import compact_generation_ledger


VALIDATION_PROFILES = frozenset({"full", "hard_only"})
HORIZON_MODES = frozenset({"fixed_20", "natural_max_20"})

_PRIVATE_SIMULATOR_RE = re.compile(
    r"(?:隐藏意图|私有状态|内部状态|状态增量|动力学增量|"
    r"appraisal|state_delta|dynamics_delta|trigger_id|模拟器内部)",
    re.I,
)

_FOCUS_RESTRICTIONS = {
    "practical_execution": (
        "Do not mention plans, dates, amounts, funds, documents, sending, "
        "checking, repayment execution, or future meetings."
    ),
    "communication_boundary": (
        "Do not mention boundaries, communication rules, advance notice, "
        "contact frequency, or concealment."
    ),
    "trust_repair": (
        "Do not restate trust, friendship, respect, hurt, apology, or "
        "preserving the relationship."
    ),
    "authorship": (
        "Do not repeat authorship, contribution, author order, or "
        "paper-credit claims."
    ),
    "graduation": "Do not repeat graduation, defense, degree, or milestone planning.",
    "performance_basis": (
        "Do not repeat rating, scoring, promotion, or feedback-basis requests."
    ),
    "care_responsibility": (
        "Do not repeat caregiving division, shifts, appointments, or "
        "household-task allocation."
    ),
    "artifact_workflow": (
        "Do not mention records, files, documents, lists, retrieval, checking, "
        "signing, or written evidence; answer through a different public issue."
    ),
    "responsibility": (
        "Do not repeat responsibility, ownership, authorization, or blame; "
        "answer through a different public issue."
    ),
}


def validate_generation_options(validation_profile, horizon_mode):
    if validation_profile not in VALIDATION_PROFILES:
        raise ValueError("validation_profile must be full or hard_only")
    if horizon_mode not in HORIZON_MODES:
        raise ValueError("horizon_mode must be fixed_20 or natural_max_20")


def horizon_guidance(
    horizon_mode, turn_number, segment_turn, *, fragment_reference, history_scope,
    minimum_natural_turns=1,
):
    """Return one horizon instruction without duplicating mode branches."""
    if (
        horizon_mode == "natural_max_20"
        and turn_number < minimum_natural_turns
    ):
        return (
            "The interaction is before its minimum effective history depth. "
            "Answer the newest substantive move and add one material advancement. "
            "If the local issue is settled, surface or engage one different grounded "
            "dimension: a trade-off, timing window, resource limit, authority boundary, "
            "coordination dependency, verification criterion, or contingency. It may "
            "be framed as the speaker\x27s concern, uncertainty, or proposal, but never as "
            "a newly established external fact. A bare acknowledgment, repeated contact "
            "promise, repeated deadline, or stretched farewell is invalid progression. "
            "Do not invent a named actor, institution, document, exact rule, evidence, "
            "completed action, or external event."
        )
    if horizon_mode == "fixed_20" and turn_number == 20:
        return (
            "Final total turn: close this interaction in the present tense without "
            "opening another process or inventing a future event."
        )
    if segment_turn == 0 and turn_number > 1:
        return (
            "A new interaction fragment has begun. React to "
            f"{fragment_reference} while preserving {history_scope}."
        )
    if segment_turn <= 2:
        return (
            "Current fragment is early: address the live issue without trying to "
            "settle every part of the relationship at once."
        )
    return (
        "Continue only while the newest evidence supports a meaningful move; a "
        "locally justified pause or preserved disagreement is valid."
    )


def apply_hard_only_prompt_profile(payload, ledger_key):
    """Replace the verbose ledger with its public compact projection."""
    ledger = payload.get(ledger_key, {})
    payload[ledger_key] = compact_generation_ledger(ledger)
    payload.pop("next_move_constraints", None)
    payload["measurement_profile"] = (
        "Hard errors only. Repetition, topic duration, and focus switching are "
        "diagnostic signals rather than rejection rules."
    )


def contains_private_simulator_language(text):
    return bool(_PRIVATE_SIMULATOR_RE.search(str(text)))


def focus_retry_guidance(ledger, goal_thread_constraints):
    """Build the shared saturated-focus guidance used by both speakers."""
    threads = ledger.get("goal_threads", [])
    visible = [
        f"{str(item.get('text', '')).strip()} [status={item.get('status', 'open')}]"
        for item in threads
        if str(item.get("text", "")).strip()
    ]
    focus = ledger.get("progress", {}).get("current_focus")
    parts = []
    if focus and int(
        ledger.get("progress", {}).get("consecutive_focus_utterances", 0)
    ) >= 4:
        parts.append(
            f"The saturated practical focus is {focus}. "
            f"{_FOCUS_RESTRICTIONS.get(focus, '')} "
            "Choose a genuinely different public goal facet or give a brief "
            "present-tense closure/explicit unresolved boundary."
        )
    constraints = goal_thread_constraints(ledger)
    available = constraints.get("available_existing_facets", [])
    if available:
        parts.append(
            "Speak naturally through one of these unsaturated public facets: "
            + " / ".join(available)
            + ". Never quote or prefix the facet label; do not use a saturated "
            "facet as a bridge."
        )
    elif visible:
        parts.append(
            "All public facets have been discussed; answer the latest obligation "
            "or make one concise explicit unresolved statement without recap."
        )
    return parts
