#!/usr/bin/env python3
"""Apply a real browser Gate 1 review and create the final hash-bound registry."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.review_registry import (
    REQUIRED_ATTESTATIONS,
    REQUIRED_QUALITY_SCORES,
    file_sha256,
    load_review_registry,
    validate_human_review,
)
from pipeline.scenarios import load_scenario_records
from schemas.validate import validate_scenario
from scripts.scenario_docs import write_document


BROWSER_FORMAT = "socialflux_gpt50_gate1_browser_export_v1"
REGISTRY_FORMAT = "socialflux_scenario_review_registry_v1"


def _validate_timestamp(value, scenario_id):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{scenario_id} reviewed_at_utc is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{scenario_id} reviewed_at_utc must include timezone")


def _validate_approved_draft(record):
    scenario_id = record.get("scenario_id", "unknown")
    if not str(record.get("reviewer", "")).strip():
        raise ValueError(f"{scenario_id} reviewer is empty")
    _validate_timestamp(record.get("reviewed_at_utc", ""), scenario_id)
    if record.get("human_attestation") is not True:
        raise ValueError(f"{scenario_id} is missing real-human attestation")
    attestations = record.get("attestations", {})
    if set(attestations) != set(REQUIRED_ATTESTATIONS) or not all(
        attestations.values()
    ):
        raise ValueError(f"{scenario_id} review attestations are incomplete")
    scores = record.get("quality_scores", {})
    if set(scores) != set(REQUIRED_QUALITY_SCORES) or any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not 1 <= value <= 5
        for value in scores.values()
    ):
        raise ValueError(f"{scenario_id} human quality scores are incomplete")
    if any(
        scores[key] < 4
        for key in ("social_plausibility", "tradeoff_quality", "history_necessity")
    ):
        raise ValueError(f"{scenario_id} fails a required >=4 quality dimension")
    if any(scores[key] < 3 for key in REQUIRED_QUALITY_SCORES):
        raise ValueError(f"{scenario_id} fails a required >=3 quality dimension")
    if sum(scores.values()) / len(REQUIRED_QUALITY_SCORES) < 4:
        raise ValueError(f"{scenario_id} human quality mean is below 4.0")


def apply_review(draft_path, scenario_root, output_path, *, dry_run=False):
    draft = json.loads(Path(draft_path).read_text(encoding="utf-8"))
    if draft.get("format") != BROWSER_FORMAT:
        raise ValueError(f"invalid browser review format: expected {BROWSER_FORMAT}")
    records = draft.get("records")
    if not isinstance(records, list):
        raise ValueError("browser review records must be a list")
    by_id = {}
    for record in records:
        scenario_id = record.get("scenario_id")
        if not scenario_id:
            raise ValueError("browser review record is missing scenario_id")
        if scenario_id in by_id:
            raise ValueError(f"duplicate browser review record: {scenario_id}")
        by_id[scenario_id] = record

    scenario_records = load_scenario_records(scenario_root)
    scenarios = {
        scenario["scenario_id"]: (path, scenario)
        for path, scenario in scenario_records
    }
    unknown = sorted(set(by_id) - set(scenarios))
    if unknown:
        raise ValueError(f"review contains scenarios outside this batch: {unknown}")

    approved = []
    final_registry_records = []
    mutations = []
    for scenario_id, record in by_id.items():
        path, scenario = scenarios[scenario_id]
        if record.get("scenario_sha256") != file_sha256(path):
            raise ValueError(f"{scenario_id} changed after browser review")
        decision = record.get("decision", "pending")
        if decision not in {"pending", "approved", "needs_revision", "rejected"}:
            raise ValueError(f"{scenario_id} has unsupported decision: {decision}")
        canonical = {
            key: value
            for key, value in record.items()
            if key != "record_type"
        }
        if decision == "approved":
            _validate_approved_draft(record)
            checklist = scenario.get("quality_gate", {})
            if not checklist or any(value != "pass" for value in checklist.values()):
                raise ValueError(
                    f"{scenario_id} canonical machine checklist is not fully passed"
                )
            frozen = json.loads(json.dumps(scenario))
            frozen["construction_status"]["quality_gate"] = "approved"
            frozen["construction_status"]["initial_state"] = "human_frozen"
            validate_scenario(frozen)
            mutations.append((path, frozen))
            approved.append(scenario_id)
        final_registry_records.append(canonical)

    if dry_run:
        return {
            "reviewed": len(final_registry_records),
            "approved": len(approved),
            "approved_scenario_ids": approved,
            "dry_run": True,
        }

    for path, scenario in mutations:
        path.write_text(
            json.dumps(scenario, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        write_document(path)

    for record in final_registry_records:
        path, scenario = scenarios[record["scenario_id"]]
        if record["decision"] == "approved":
            scenario = json.loads(path.read_text(encoding="utf-8"))
        record["scenario_sha256"] = file_sha256(path)

    registry = {
        "format": REGISTRY_FORMAT,
        "instructions": (
            "GPT experiment Gate 1 records exported by a real reviewer and "
            "bound to the exact post-freeze scenario files."
        ),
        "records": final_registry_records,
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    loaded = load_review_registry(output_path)
    for scenario_id in approved:
        path, _ = scenarios[scenario_id]
        frozen = json.loads(path.read_text(encoding="utf-8"))
        validate_human_review(frozen, path, loaded)
    return {
        "reviewed": len(final_registry_records),
        "approved": len(approved),
        "approved_scenario_ids": approved,
        "output": str(output_path),
        "dry_run": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Freeze human-approved GPT scenarios and write Gate 1 registry"
    )
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--scenarios", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = apply_review(
        args.draft,
        args.scenarios,
        args.output,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
