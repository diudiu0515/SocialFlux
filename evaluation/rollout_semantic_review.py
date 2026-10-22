"""Validation and deterministic sampling for model rollout reviews."""

from __future__ import annotations

from copy import deepcopy
import hashlib

from evaluation.rollout_gate import HARD_REJECT_REASONS, QUALITY_DIMENSIONS


def validate_judgment(value, trajectory_id, valid_turn_ids=None):
    semantic_fields = {"scores", "hard_reject_reasons", "evidence", "rationale"}
    if set(value) not in (semantic_fields, semantic_fields | {"trajectory_id"}):
        raise ValueError("quality judgment fields mismatch")
    value = dict(value)
    value["trajectory_id"] = trajectory_id
    if set(value["scores"]) != set(QUALITY_DIMENSIONS):
        raise ValueError("quality judgment score dimensions mismatch")
    if not all(
        isinstance(item, int) and 1 <= item <= 5
        for item in value["scores"].values()
    ):
        raise ValueError("quality scores must be integer 1..5")
    if set(value["hard_reject_reasons"]) - set(HARD_REJECT_REASONS):
        raise ValueError("quality judgment contains unknown hard reject")
    if set(value["evidence"]) != set(QUALITY_DIMENSIONS):
        raise ValueError("quality judgment evidence dimensions mismatch")
    allowed = set(valid_turn_ids or [])
    for dimension, turn_ids in value["evidence"].items():
        if (
            not isinstance(turn_ids, list)
            or not 1 <= len(turn_ids) <= 3
            or len(set(turn_ids)) != len(turn_ids)
            or not all(
                isinstance(item, str)
                and item.startswith("t")
                and item[1:].isdigit()
                for item in turn_ids
            )
            or (allowed and not set(turn_ids) <= allowed)
        ):
            raise ValueError(
                f"quality judgment has invalid turn evidence: {dimension}"
            )
    if not str(value["rationale"]).strip():
        raise ValueError("quality judgment rationale is empty")
    return value


def deterministic_review_sampling(sampling, trajectory_id):
    """Make a review seed independent of pool ordering and prior calls."""
    result = deepcopy(sampling)
    if isinstance(result.get("seed"), int):
        digest = int(
            hashlib.sha256(trajectory_id.encode("utf-8")).hexdigest()[:8], 16
        )
        result["seed"] = (result["seed"] + digest) % 2_147_483_647
    return result


def validate_model_family(model, declared_family):
    """Validate legacy comparison declarations without selecting a model."""
    lowered = str(model).lower()
    aliases = {
        "qwen": ("qwen",),
        "glm": ("glm",),
        "deepseek": ("deepseek",),
        "minimax": ("minimax",),
        "mistral": ("mistral", "mixtral"),
        "kimi": ("kimi", "moonshot"),
        "claude": ("claude",),
        "openai": ("gpt", "o1", "o3", "o4"),
    }
    markers = aliases.get(declared_family.lower())
    if markers is None or not any(marker in lowered for marker in markers):
        raise ValueError(
            f"declared model family {declared_family!r} does not match model {model!r}"
        )
