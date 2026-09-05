"""Cryptographically bind human scenario approval to exact scenario files."""

from datetime import datetime
import hashlib
import json
from pathlib import Path

from schemas.validate import QUALITY_CHECKS


REQUIRED_ATTESTATIONS = (
    "variables_relevant",
    "values_justified",
    "no_policy_effect_baked_in",
    "initial_triggers_inactive",
    "multiple_future_paths_possible",
    "shared_across_models_and_seeds",
)

REQUIRED_QUALITY_SCORES = (
    "social_plausibility",
    "character_coherence",
    "tradeoff_quality",
    "history_necessity",
    "interaction_richness",
    "t1_t4_suitability",
)


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_review_registry(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("format") != "socialflux_scenario_review_registry_v1":
        raise ValueError("invalid scenario review registry format")
    records = value.get("records", [])
    if len({item.get("scenario_id") for item in records}) != len(records):
        raise ValueError("duplicate scenario review records")
    return {item["scenario_id"]: item for item in records}


def validate_human_review(scenario, scenario_path, registry):
    scenario_id = scenario["scenario_id"]
    record = registry.get(scenario_id)
    if not record:
        raise ValueError(f"{scenario_id} has no human review record")
    if record.get("decision") != "approved" or record.get("human_attestation") is not True:
        raise ValueError(f"{scenario_id} is not human-approved")
    if not str(record.get("reviewer", "")).strip():
        raise ValueError(f"{scenario_id} reviewer is empty")
    try:
        reviewed = datetime.fromisoformat(record["reviewed_at_utc"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{scenario_id} reviewed_at_utc is invalid") from exc
    if reviewed.tzinfo is None:
        raise ValueError(f"{scenario_id} reviewed_at_utc must include timezone")
    attestations = record.get("attestations", {})
    if set(attestations) != set(REQUIRED_ATTESTATIONS) or not all(attestations.values()):
        raise ValueError(f"{scenario_id} review attestations are incomplete")
    quality_scores = record.get("quality_scores", {})
    if set(quality_scores) != set(REQUIRED_QUALITY_SCORES) or any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not 1 <= value <= 5
        for value in quality_scores.values()
    ):
        raise ValueError(f"{scenario_id} human quality scores are incomplete or invalid")
    if any(
        quality_scores[key] < 4
        for key in ("social_plausibility", "tradeoff_quality", "history_necessity")
    ):
        raise ValueError(f"{scenario_id} fails a required >=4 human quality dimension")
    if any(quality_scores[key] < 3 for key in REQUIRED_QUALITY_SCORES):
        raise ValueError(f"{scenario_id} fails a required >=3 human quality dimension")
    if sum(quality_scores.values()) / len(REQUIRED_QUALITY_SCORES) < 4.0:
        raise ValueError(f"{scenario_id} human quality mean is below 4.0")
    if record.get("scenario_sha256") != file_sha256(scenario_path):
        raise ValueError(f"{scenario_id} changed after human review")
    status = scenario["construction_status"]
    if status["quality_gate"] != "approved" or status["initial_state"] != "human_frozen":
        raise ValueError(f"{scenario_id} JSON status does not match approved review")
    checklist = scenario.get("quality_gate", {})
    if set(checklist) != set(QUALITY_CHECKS) or any(
        value != "pass" for value in checklist.values()
    ):
        raise ValueError(f"{scenario_id} canonical quality checklist is not fully passed")
    return True
