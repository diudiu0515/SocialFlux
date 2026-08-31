"""Human-annotation overlay export and aggregation helpers."""

from collections import Counter
from copy import deepcopy
import json
from pathlib import Path


def make_overlay(instance_id, task_type, annotator_id, response, confidence=None,
                 elapsed_seconds=None, quality_status="pending"):
    return {
        "overlay_version": "annotation_overlay_v1",
        "instance_id": instance_id,
        "task_type": task_type,
        "annotator_id": annotator_id,
        "response": deepcopy(response),
        "confidence": confidence,
        "elapsed_seconds": elapsed_seconds,
        "quality_status": quality_status,
    }


def aggregate_labels(responses, labels=None):
    values = list(responses)
    counts = Counter(values)
    labels = list(labels or sorted(counts))
    total = len(values)
    return {
        "n": total,
        "distribution": {label: (counts[label] / total if total else 0.0) for label in labels},
        "mode": max(labels, key=lambda label: counts[label]) if values and labels else None,
    }


def export_overlays(overlays, path):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for overlay in overlays:
            handle.write(json.dumps(overlay, ensure_ascii=False) + "\n")
    return target
