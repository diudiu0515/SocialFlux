"""Active evaluated-agent validation and explicit legacy dispatch."""

from environment.dialogue_support import contains_private_simulator_language
from providers.text import follows_dialogue_format, normalize_text

from . import legacy_action_validation


ACTIVE_PROMPT_ID = "task_t4_action_v21"


def _validate_semantic_core(candidate, observation):
    """Reject only direct format, privacy, and exact ownership-risk errors.

    Consequential factual grounding is checked by Structured Appraisal before
    any state mutation. Naturalness and semantic repetition remain review
    signals rather than lexical hard gates.
    """
    if not follows_dialogue_format(candidate):
        return False, "malformed direct dialogue"
    if contains_private_simulator_language(candidate):
        return False, "private simulator language leakage"
    latest = observation.get("current_response", "")
    if latest and normalize_text(candidate) == normalize_text(latest):
        return False, "exact echo of the latest other-speaker utterance"
    return True, ""


def validate_candidate_for_profile(policy, candidate, observation):
    if (
        policy.prompt_id == ACTIVE_PROMPT_ID
        and policy.validation_profile == "hard_only"
    ):
        return _validate_semantic_core(candidate, observation)
    return legacy_action_validation.validate_candidate_for_profile(
        policy, candidate, observation
    )


def retry_guidance(policy, observation):
    """Return generic semantic guidance without topic-specific word rules."""
    if policy.prompt_id != ACTIVE_PROMPT_ID:
        return legacy_action_validation.retry_guidance(observation)
    obligation = (
        observation.get("conversation_progress", {}).get("latest_obligation") or {}
    )
    if obligation.get("owner") == "evaluated_agent":
        return (
            "Answer the newest request or proposal directly from your own role. "
            "Accept, refuse, counter, clarify, or state what cannot be confirmed; "
            "do not report another speaker's action as your own."
        )
    return (
        "Respond from your assigned role using only public facts. Continue only "
        "when the reply adds understanding, affects a choice, or preserves a real "
        "disagreement; otherwise pause naturally."
    )


def validate_candidate(candidate, observation, enforce_fixed_horizon=True):
    """Compatibility entry point used by historical full-profile policies."""
    return legacy_action_validation.validate_candidate(
        candidate,
        observation,
        enforce_fixed_horizon=enforce_fixed_horizon,
    )
