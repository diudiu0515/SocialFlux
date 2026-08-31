#!/usr/bin/env python3
"""Canonical probability and confidence calculations for EmoTree T2 v0.2."""

import math
from collections import Counter

DIRECTION_LABELS = ("higher_in_a", "similar", "higher_in_b", "cannot_determine")
HUMAN_CONFIDENCE_VALUES = {"low": 1, "medium": 2, "high": 3, "very_high": 4}


def validate_probabilities(probabilities, labels=DIRECTION_LABELS, tolerance=1e-6):
    if set(probabilities) != set(labels):
        raise ValueError("probability keys do not match required labels")
    values = [float(probabilities[label]) for label in labels]
    if any(value < 0 or value > 1 or not math.isfinite(value) for value in values):
        raise ValueError("probabilities must be finite and within [0, 1]")
    if abs(sum(values) - 1.0) > tolerance:
        raise ValueError("probabilities must sum to 1")
    return True


def human_direction_distribution(labels):
    if not labels:
        raise ValueError("at least one accepted human label is required")
    unknown = set(labels) - set(DIRECTION_LABELS)
    if unknown:
        raise ValueError(f"unknown direction labels: {sorted(unknown)}")
    counts = Counter(labels)
    return {label: counts[label] / len(labels) for label in DIRECTION_LABELS}


def causal_relevance(is_causal_labels):
    if not is_causal_labels or any(type(value) is not bool for value in is_causal_labels):
        raise ValueError("causal labels must be a non-empty list of booleans")
    return sum(is_causal_labels) / len(is_causal_labels)


def normalized_entropy_confidence(distribution):
    validate_probabilities(distribution)
    entropy = -sum(value * math.log(value) for value in distribution.values() if value > 0)
    return 1.0 - entropy / math.log(len(distribution))


def model_confidence(distribution):
    validate_probabilities(distribution)
    ranked = sorted(distribution.items(), key=lambda item: item[1], reverse=True)
    return {"predicted_direction": ranked[0][0], "max_probability": ranked[0][1], "margin": ranked[0][1] - ranked[1][1], "entropy_confidence": normalized_entropy_confidence(distribution)}


def aggregate_human_confidence(confidence_labels):
    if not confidence_labels:
        raise ValueError("at least one confidence label is required")
    unknown = set(confidence_labels) - set(HUMAN_CONFIDENCE_VALUES)
    if unknown:
        raise ValueError(f"unknown confidence labels: {sorted(unknown)}")
    mean = sum(HUMAN_CONFIDENCE_VALUES[label] for label in confidence_labels) / len(confidence_labels)
    return {"mean_1_to_4": mean, "normalized_0_to_1": (mean - 1.0) / 3.0}
