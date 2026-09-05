"""Primary/secondary rollout-judge protocol required by gate.md.

The protocol deterministically sends a stratified subset and every borderline
or rejected primary judgment to a judge from a different model family.  A
missing required secondary judgment remains pending rather than silently using
the primary result.
"""

from __future__ import annotations

from collections import defaultdict
import hashlib

from evaluation.rollout_gate import HARD_REJECT_REASONS, QUALITY_DIMENSIONS


def _index_records(bundle, role):
    records = bundle.get("records", [])
    identifiers = [item.get("trajectory_id") for item in records]
    if any(not item for item in identifiers) or len(set(identifiers)) != len(identifiers):
        raise ValueError(f"{role} judge bundle has empty or duplicate trajectory IDs")
    for item in records:
        if set(item.get("scores", {})) != set(QUALITY_DIMENSIONS):
            raise ValueError(f"{role} judge score dimensions mismatch")
        if any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not 1 <= value <= 5
            for value in item["scores"].values()
        ):
            raise ValueError(f"{role} judge score must be in 1..5")
        unknown = set(item.get("hard_reject_reasons", [])) - set(HARD_REJECT_REASONS)
        if unknown or not str(item.get("rationale", "")).strip():
            raise ValueError(f"{role} judge hard reject or rationale is invalid")
    return {item["trajectory_id"]: item for item in records}


def validate_judge_independence(primary_metadata, secondary_metadata):
    for metadata, role in ((primary_metadata, "primary"), (secondary_metadata, "secondary")):
        if metadata.get("judge_role") != role:
            raise ValueError(f"{role} judge metadata has the wrong role")
        if not metadata.get("model") or not metadata.get("model_family"):
            raise ValueError(f"{role} judge must record model and model_family")
    if primary_metadata["model"] == secondary_metadata["model"]:
        raise ValueError("primary and secondary judges must use different models")
    if primary_metadata["model_family"] == secondary_metadata["model_family"]:
        raise ValueError("primary and secondary judges must use different model families")


def _stratified_ids(trajectories, fraction=0.20):
    groups = defaultdict(list)
    for trajectory in trajectories:
        provenance = trajectory.get("policy_provenance", {})
        groups[(trajectory.get("scenario_id"), provenance.get("model_family", "unknown"))].append(
            trajectory["trajectory_id"]
        )
    chosen = set()
    for key, identifiers in groups.items():
        ordered = sorted(
            identifiers,
            key=lambda value: hashlib.sha256((repr(key) + value).encode("utf-8")).hexdigest(),
        )
        count = max(1, round(len(ordered) * fraction))
        chosen.update(ordered[:count])
    return chosen


def required_secondary_ids(trajectories, primary_records, fraction=0.20):
    """Return deterministic second-judge targets plus selection reasons."""
    if len({item.get("trajectory_id") for item in primary_records}) != len(primary_records):
        raise ValueError("primary judge has duplicate trajectory IDs")
    by_id = {item["trajectory_id"]: item for item in primary_records}
    expected = {item["trajectory_id"] for item in trajectories}
    missing = sorted(expected - set(by_id))
    if missing:
        raise ValueError("primary judge is incomplete: " + ", ".join(missing))
    stratified = _stratified_ids(trajectories, fraction)
    reasons = {}
    for trajectory_id in sorted(expected):
        record = by_id[trajectory_id]
        scores = record.get("scores", {})
        selected = []
        if trajectory_id in stratified:
            selected.append("deterministic_stratified_sample")
        if record.get("hard_reject_reasons"):
            selected.append("primary_hard_reject")
        if any(value <= 3 for value in scores.values() if isinstance(value, (int, float))):
            selected.append("borderline_or_failed_dimension")
        if selected:
            reasons[trajectory_id] = selected
    return reasons


def merge_judgments(trajectories, primary_bundle, secondary_bundle, fraction=0.20):
    """Merge two independent judges conservatively and expose disagreements."""
    validate_judge_independence(primary_bundle, secondary_bundle)
    primary = _index_records(primary_bundle, "primary")
    secondary = _index_records(secondary_bundle, "secondary")
    reasons = required_secondary_ids(trajectories, list(primary.values()), fraction)
    extra_secondary = sorted(set(secondary) - set(reasons))
    if extra_secondary:
        raise ValueError("secondary judge contains unselected trajectories: " + ", ".join(extra_secondary))
    missing_secondary = sorted(set(reasons) - set(secondary))
    merged = []
    disagreements = []
    for trajectory in trajectories:
        trajectory_id = trajectory["trajectory_id"]
        left = primary[trajectory_id]
        right = secondary.get(trajectory_id)
        if trajectory_id not in reasons:
            merged.append(dict(left))
            continue
        if right is None:
            continue
        unknown = (set(left.get("hard_reject_reasons", [])) | set(right.get("hard_reject_reasons", []))) - set(HARD_REJECT_REASONS)
        if unknown:
            raise ValueError("unknown hard-reject reason in judge bundle")
        if set(left.get("scores", {})) != set(QUALITY_DIMENSIONS) or set(right.get("scores", {})) != set(QUALITY_DIMENSIONS):
            raise ValueError("judge score dimensions mismatch")
        score_gaps = {
            key: abs(float(left["scores"][key]) - float(right["scores"][key]))
            for key in QUALITY_DIMENSIONS
        }
        reject_disagreement = bool(left.get("hard_reject_reasons")) != bool(right.get("hard_reject_reasons"))
        material = reject_disagreement or any(value >= 2 for value in score_gaps.values())
        if material:
            disagreements.append({
                "trajectory_id": trajectory_id,
                "selection_reasons": reasons[trajectory_id],
                "reject_disagreement": reject_disagreement,
                "score_gaps": score_gaps,
                "resolution": "conservative_union_and_mean",
            })
        merged.append({
            "trajectory_id": trajectory_id,
            "scores": {
                key: round((float(left["scores"][key]) + float(right["scores"][key])) / 2, 2)
                for key in QUALITY_DIMENSIONS
            },
            "hard_reject_reasons": sorted(set(left.get("hard_reject_reasons", [])) | set(right.get("hard_reject_reasons", []))),
            "rationale": "Primary: " + left["rationale"] + " Secondary: " + right["rationale"],
        })
    complete = not missing_secondary and len(merged) == len(trajectories)
    return {
        "format": "socialflux_dual_judge_merge_v1",
        "complete": complete,
        "trajectory_count": len(trajectories),
        "secondary_required_count": len(reasons),
        "secondary_selection_reasons": reasons,
        "missing_secondary_ids": missing_secondary,
        "material_disagreements": disagreements,
        "primary_judge": {key: primary_bundle[key] for key in ("judge_role", "model", "model_family")},
        "secondary_judge": {key: secondary_bundle[key] for key in ("judge_role", "model", "model_family")},
        "records": merged,
    }
