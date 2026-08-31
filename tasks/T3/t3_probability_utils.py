#!/usr/bin/env python3
"""Canonical probability, confidence, and ranking calculations for EmoTree T3 v0.2."""

import math
from collections import Counter

DIRECTION_LABELS = ("increase", "similar", "decrease", "cannot_determine")
DIRECTION_VALUES = {"increase": 1.0, "similar": 0.0, "decrease": -1.0}
HUMAN_CONFIDENCE_VALUES = {"low": 1, "medium": 2, "high": 3, "very_high": 4}


def validate_probabilities(probabilities, tolerance=1e-6):
    if set(probabilities) != set(DIRECTION_LABELS):
        raise ValueError("probability keys do not match required labels")
    values = [float(probabilities[label]) for label in DIRECTION_LABELS]
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
        raise ValueError("unknown direction labels: {}".format(sorted(unknown)))
    counts = Counter(labels)
    return {label: counts[label] / len(labels) for label in DIRECTION_LABELS}


def normalized_entropy_confidence(distribution):
    validate_probabilities(distribution)
    entropy = -sum(value * math.log(value) for value in distribution.values() if value > 0)
    return 1.0 - entropy / math.log(len(distribution))


def model_confidence(distribution):
    validate_probabilities(distribution)
    ranked = sorted(distribution.items(), key=lambda item: item[1], reverse=True)
    return {"predicted_direction": ranked[0][0], "max_probability": ranked[0][1], "margin": ranked[0][1] - ranked[1][1], "entropy_confidence": normalized_entropy_confidence(distribution)}


def expected_change(distribution):
    validate_probabilities(distribution)
    decidable_mass = 1.0 - distribution["cannot_determine"]
    if decidable_mass <= 0:
        return None
    return sum(distribution[label] * value for label, value in DIRECTION_VALUES.items()) / decidable_mass


def rank_options(option_distributions):
    scores = {option_id: expected_change(distribution) for option_id, distribution in option_distributions.items()}
    if any(score is None for score in scores.values()):
        return None
    return sorted(scores, key=lambda option_id: (-scores[option_id], option_id))


def aggregate_human_confidence(confidence_labels):
    if not confidence_labels:
        raise ValueError("at least one confidence label is required")
    unknown = set(confidence_labels) - set(HUMAN_CONFIDENCE_VALUES)
    if unknown:
        raise ValueError("unknown confidence labels: {}".format(sorted(unknown)))
    mean = sum(HUMAN_CONFIDENCE_VALUES[label] for label in confidence_labels) / len(confidence_labels)
    return {"mean_1_to_4": mean, "normalized_0_to_1": (mean - 1.0) / 3.0}
