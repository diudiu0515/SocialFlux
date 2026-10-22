"""Shared validation for explicit model-assignment policies."""

from __future__ import annotations


SINGLE_MODEL_STRATEGY = "single_model_all_llm_roles"


def validate_single_model_assignment(
    assignment,
    provider_configs,
    *,
    require_explicit=False,
    has_versioned_routes=False,
):
    """Validate one declared model shared by logically independent LLM roles."""
    if assignment is None:
        if require_explicit:
            raise ValueError("run requires explicit model_assignment")
        return

    expected = {"strategy", "model", "independent_calls"}
    if not isinstance(assignment, dict) or set(assignment) != expected:
        raise ValueError(f"model_assignment fields must be {sorted(expected)}")
    if assignment["strategy"] != SINGLE_MODEL_STRATEGY:
        raise ValueError("unsupported model_assignment.strategy")
    if assignment["independent_calls"] is not True:
        raise ValueError("unified model assignment still requires independent calls")

    configured_models = {
        provider.get("model")
        for provider in provider_configs
        if isinstance(provider, dict)
    }
    if not assignment["model"] or configured_models != {assignment["model"]}:
        raise ValueError("every LLM role must match model_assignment.model")
    if not has_versioned_routes:
        raise ValueError("single-model assignment requires versioned model routes")
