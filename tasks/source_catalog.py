"""Batch-size-independent source-package and rollout-quality catalog."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from scripts.t2_common import load


ELIGIBLE_GENERATION_STATUSES = {
    "accepted",
    "short_natural_trajectory",
    "budget_truncated",
}
CRITICAL_SOURCE_CHECKS = {
    "turns_preserve_speaker_action_ownership",
    "pending_commitments_are_consistent",
}


def load_source_packages(source_root, *, expected_count=None):
    records = {}
    for path in sorted(Path(source_root).glob("shard*/scenario_*.json")):
        package = load(path)
        ordinal = int(package["ordinal"])
        if ordinal in records:
            raise ValueError(f"duplicate source package ordinal: {ordinal}")
        records[ordinal] = (path, package)
    if not records:
        raise ValueError(f"no source task packages found under {source_root}")
    expected_count = expected_count or max(records)
    expected = set(range(1, expected_count + 1))
    if set(records) != expected:
        raise ValueError(
            f"source task packages must cover ordinals 1..{expected_count}"
        )
    return records


def load_source_reviews(path):
    return {
        int(row["ordinal"]): row
        for row in load(path)["candidates"]
    }


def assess_source(review, source_package, root):
    latest = review.get("latest_attempt") or {}
    reasons = []
    if review.get("generation_status") not in ELIGIBLE_GENERATION_STATUSES:
        reasons.append(f"generation_status={review.get('generation_status')}")
    semantic = review.get("model_semantic_review") or {}
    if semantic.get("decision") != "approve":
        reasons.append(f"model_semantic_review={semantic.get('decision')}")
    if not latest.get("scenario_version_matches_current"):
        reasons.append("scenario_version_mismatch")
    source = source_package.get("source_artifact")
    if not source or source != latest.get("artifact_path"):
        reasons.append("source_artifact_not_latest_attempt")
    elif not (Path(root) / source).is_file():
        reasons.append("source_artifact_missing")
    if int(source_package.get("turn_count") or 0) < 1:
        reasons.append("empty_trajectory")
    checks = (
        (((latest.get("machine_precheck") or {}).get("structural") or {}).get(
            "checks"
        ))
        or {}
    )
    failed = sorted(name for name, passed in checks.items() if passed is False)
    reasons.extend(
        f"critical_precheck_failure={name}"
        for name in sorted(CRITICAL_SOURCE_CHECKS & set(failed))
    )
    return {
        "eligible": not reasons,
        "reasons": reasons,
        "generation_status": review.get("generation_status"),
        "model_semantic_review": deepcopy(semantic),
        "human_review": review.get("human_review", "pending"),
        "source_artifact": source,
        "source_artifact_sha256": latest.get("artifact_sha256"),
        "scenario_version_matches_current": latest.get(
            "scenario_version_matches_current"
        ),
        "turn_count": int(source_package.get("turn_count") or 0),
        "ending": deepcopy(latest.get("ending")),
        "saved_machine_precheck_false_checks": failed,
    }
