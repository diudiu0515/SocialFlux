"""Dependency-free benchmark metrics with explicit missing-label handling."""

import math


def brier_score(probabilities, outcome):
    if outcome not in probabilities:
        raise ValueError("outcome missing from probability distribution")
    return sum((probabilities.get(label, 0.0) - (1.0 if label == outcome else 0.0)) ** 2
               for label in probabilities)


def accuracy(predictions, labels):
    pairs = [(prediction, label) for prediction, label in zip(predictions, labels) if label is not None]
    return sum(prediction == label for prediction, label in pairs) / len(pairs) if pairs else None


def macro_f1(predictions, labels, label_set=None):
    gold_labels = list(labels)
    classes = list(label_set or sorted(set(predictions) | set(gold_labels)))
    scores = []
    for label in classes:
        tp = sum(p == label and y == label for p, y in zip(predictions, gold_labels))
        fp = sum(p == label and y != label for p, y in zip(predictions, gold_labels))
        fn = sum(p != label and y == label for p, y in zip(predictions, gold_labels))
        if not tp and not fp and not fn:
            continue
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return sum(scores) / len(scores) if scores else None


def score_t1(rows):
    return _score_direction_rows(rows, "change_direction")


def score_t2(rows):
    return _score_direction_rows(rows, "direction")


def score_t3(rows):
    return _score_direction_rows(rows, "change_direction")


def _score_direction_rows(rows, field):
    evaluated = [row for row in rows if row.get("prediction") is not None and row.get("label") is not None]
    return {
        "n": len(evaluated),
        "accuracy": accuracy([row["prediction"] for row in evaluated],
                             [row["label"] for row in evaluated]),
        "metric": "direction_accuracy",
        "field": field,
    }


def score_t4(rubric):
    dimensions = ("goal_achievement", "state_adaptation", "risk_management", "recovery", "relationship_outcome")
    result = {key: rubric.get(key) for key in dimensions}
    available = [value for value in result.values() if isinstance(value, (int, float))]
    result["n_scored_dimensions"] = len(available)
    result["profile_mean"] = sum(available) / len(available) if available else None
    return result
