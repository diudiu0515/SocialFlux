"""Executable SocialFlux Rollout Screening Protocol v1 rules.

This module keeps the protocol's three-way automatic decision separate from
human audit and from the project-level one-trajectory-per-scenario selection.
Missing evidence is exposed; it is never converted into a pass.
"""

from __future__ import annotations

from hashlib import sha256
import math

from evaluation.rollout_gate import HARD_REJECT_REASONS, QUALITY_DIMENSIONS


PROTOCOL_VERSION = "socialflux_rollout_screening_protocol_v1"
DECISION_ORDER = {"PASS": 2, "REVIEW": 1, "REJECT": 0}


def normalize_scores(scores):
    """Return valid 1--5 scores, accepting legacy normalized 0--1 records."""
    values = {}
    for dimension in QUALITY_DIMENSIONS:
        value = (scores or {}).get(dimension)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        value = float(value)
        if 0 <= value <= 1:
            value *= 5
        if 1 <= value <= 5:
            values[dimension] = round(value, 3)
    return values


def automatic_decision(scores, hard_failures=None):
    """Apply the exact PASS/REVIEW/REJECT thresholds from the protocol."""
    scores = normalize_scores(scores)
    hard_failures = sorted(set(hard_failures or []))
    unknown_hard_failures = sorted(set(hard_failures) - set(HARD_REJECT_REASONS))
    missing = [key for key in QUALITY_DIMENSIONS if key not in scores]
    if missing or unknown_hard_failures:
        return {
            "decision": "REVIEW",
            "mean_quality_score": None,
            "scores": scores,
            "hard_failures": hard_failures,
            "missing_evidence": missing,
            "rule_reasons": [
                *(f"missing_score:{key}" for key in missing),
                *(f"unknown_hard_failure:{key}" for key in unknown_hard_failures),
            ],
        }

    mean = round(sum(scores.values()) / len(QUALITY_DIMENSIONS), 3)
    if (
        hard_failures
        or scores["history_dependence"] <= 2
        or scores["character_consistency"] <= 2
        or scores["naturalness"] <= 2
        or mean < 3.0
    ):
        reasons = [f"hard_reject:{key}" for key in hard_failures]
        reasons.extend(
            f"{key}<={int(limit)}"
            for key, limit in (
                ("history_dependence", 2),
                ("character_consistency", 2),
                ("naturalness", 2),
            )
            if scores[key] <= limit
        )
        if mean < 3.0:
            reasons.append("mean_quality_score<3.0")
        decision = "REJECT"
    elif (
        scores["dialogue_coherence"] >= 3
        and scores["history_dependence"] >= 4
        and scores["character_consistency"] >= 4
        and scores["state_response_consistency"] >= 3
        and scores["interaction_progression"] >= 3
        and scores["naturalness"] >= 4
        and mean >= 3.8
    ):
        decision = "PASS"
        reasons = ["all_pass_thresholds_met"]
    else:
        decision = "REVIEW"
        reasons = ["between_pass_and_reject_thresholds"]
    return {
        "decision": decision,
        "mean_quality_score": mean,
        "scores": scores,
        "hard_failures": hard_failures,
        "missing_evidence": [],
        "rule_reasons": reasons,
    }


def deterministic_sample(records, fraction, salt):
    """Choose a reproducible ceil(fraction) audit sample from records."""
    if not records:
        return set()
    count = max(1, math.ceil(len(records) * fraction))
    ordered = sorted(
        records,
        key=lambda item: sha256(
            f"{PROTOCOL_VERSION}:{salt}:{item['trajectory_id']}".encode("utf-8")
        ).hexdigest(),
    )
    return {item["trajectory_id"] for item in ordered[:count]}


def choose_one(records):
    """Return one quality-first provisional winner without model-family quotas."""
    if not records:
        return None, []

    def ranking(record):
        scores = record.get("scores", {})
        critical_floor = min(
            (scores.get(key, 0) for key in (
                "history_dependence", "character_consistency", "naturalness"
            )),
            default=0,
        )
        return (
            DECISION_ORDER.get(record.get("automatic_decision"), -1),
            record.get("mean_quality_score") or 0,
            critical_floor,
            scores.get("state_response_consistency", 0),
            scores.get("interaction_progression", 0),
            record.get("trajectory_id", ""),
        )

    ordered = sorted(records, key=ranking, reverse=True)
    return ordered[0], ordered
