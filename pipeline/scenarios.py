"""Scenario catalog loading shared by every pipeline stage."""

import json
from pathlib import Path

from schemas.validate import STATE_CONTRACT_VERSION, validate_scenario
from scenario_design.catalog import discover_scenario_paths


def load_scenario_records(directory, *, require_documents=True):
    """Load a deterministic scenario catalog without assuming a 20-item manifest."""
    directory = Path(directory)
    records = []
    for path in discover_scenario_paths(directory):
        document = path.with_suffix(".md")
        if require_documents and not document.is_file():
            raise ValueError(f"scenario documentation is missing: {document}")
        scenario = json.loads(path.read_text(encoding="utf-8"))
        validate_scenario(scenario)
        records.append((path, scenario))
    if not records:
        raise ValueError(f"no scenarios found under {directory}")
    identifiers = [scenario["scenario_id"] for _, scenario in records]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("scenario catalog contains duplicate scenario IDs")
    return records


def load_scenarios(directory, *, require_documents=True):
    return [
        scenario
        for _, scenario in load_scenario_records(
            directory, require_documents=require_documents
        )
    ]


def select_scenario_records(records, scenario_ids=None):
    if not scenario_ids:
        return list(records)
    requested = list(dict.fromkeys(scenario_ids))
    by_id = {scenario["scenario_id"]: (path, scenario) for path, scenario in records}
    missing = [scenario_id for scenario_id in requested if scenario_id not in by_id]
    if missing:
        raise ValueError(f"unknown scenario IDs: {missing}")
    return [by_id[scenario_id] for scenario_id in requested]


def require_human_frozen(scenario, *, allow_unreviewed=False):
    """Enforce Gate 1 before production rollout."""
    if allow_unreviewed:
        return
    if scenario.get("state_contract_version") != STATE_CONTRACT_VERSION:
        raise ValueError(
            f"{scenario['scenario_id']} does not use {STATE_CONTRACT_VERSION}; "
            "legacy contracts are diagnostic-only"
        )
    status = scenario["construction_status"]
    if status["quality_gate"] != "approved":
        raise ValueError(
            f"{scenario['scenario_id']} has no approved scenario quality gate; "
            "use --allow-unreviewed only for diagnostics"
        )
    if status["initial_state"] != "human_frozen":
        raise ValueError(
            f"{scenario['scenario_id']} initial state is not human_frozen; "
            "use --allow-unreviewed only for diagnostics"
        )
