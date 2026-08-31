#!/usr/bin/env python3
"""Canonical probability and confidence calculations for EmoTree T1 v0.2."""

import math
from collections import Counter

INTENSITY_LABELS = ("absent", "mild", "moderate", "strong", "very_strong", "cannot_determine")
ORDINAL_VALUES = {"absent": 0, "mild": 1, "moderate": 2, "strong": 3, "very_strong": 4}
HUMAN_CONFIDENCE_VALUES = {"low": 1, "medium": 2, "high": 3, "very_high": 4}


def normalize_scores(scores, labels=INTENSITY_LABELS):
    values = {label: float(scores.get(label, 0.0)) for label in labels}
    if any(value < 0 or not math.isfinite(value) for value in values.values()):
        raise ValueError("scores must be finite and non-negative")
    total = sum(values.values())
    if total <= 0:
        raise ValueError("at least one score must be positive")
    return {label: value / total for label, value in values.items()}


def validate_probabilities(probabilities, labels=INTENSITY_LABELS, tolerance=1e-6):
    if set(probabilities) != set(labels):
        raise ValueError("probability keys do not match required labels")
    values = [float(probabilities[label]) for label in labels]
    if any(value < 0 or value > 1 or not math.isfinite(value) for value in values):
        raise ValueError("probabilities must be finite and within [0, 1]")
    if abs(sum(values) - 1.0) > tolerance:
        raise ValueError("probabilities must sum to 1")
    return True


def human_label_distribution(labels):
    if not labels:
        raise ValueError("at least one accepted human label is required")
    unknown = set(labels) - set(INTENSITY_LABELS)
    if unknown:
        raise ValueError(f"unknown intensity labels: {sorted(unknown)}")
    counts = Counter(labels)
    total = len(labels)
    return {label: counts[label] / total for label in INTENSITY_LABELS}


def ordinal_mean(distribution):
    validate_probabilities(distribution)
    known_mass = sum(distribution[label] for label in ORDINAL_VALUES)
    if known_mass <= 0:
        return None
    return sum(distribution[label] * value for label, value in ORDINAL_VALUES.items()) / known_mass


def normalized_entropy_confidence(distribution):
    validate_probabilities(distribution)
    entropy = -sum(p * math.log(p) for p in distribution.values() if p > 0)
    return 1.0 - entropy / math.log(len(distribution))


def model_confidence(distribution):
    validate_probabilities(distribution)
    ranked = sorted(distribution.items(), key=lambda item: item[1], reverse=True)
    return {
        "predicted_label": ranked[0][0],
        "max_probability": ranked[0][1],
        "margin": ranked[0][1] - ranked[1][1],
        "entropy_confidence": normalized_entropy_confidence(distribution),
    }


def aggregate_human_confidence(confidence_labels):
    if not confidence_labels:
        raise ValueError("at least one confidence label is required")
    unknown = set(confidence_labels) - set(HUMAN_CONFIDENCE_VALUES)
    if unknown:
        raise ValueError(f"unknown confidence labels: {sorted(unknown)}")
    mean = sum(HUMAN_CONFIDENCE_VALUES[label] for label in confidence_labels) / len(confidence_labels)
    return {"mean_1_to_4": mean, "normalized_0_to_1": (mean - 1.0) / 3.0}
