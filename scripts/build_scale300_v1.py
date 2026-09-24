#!/usr/bin/env python3
"""Validate and index a directly authored Scale300 catalog.

Claude authors the 300 canonical scenario JSON files directly. This command
does not generate scenarios, inherit an older scale, call a model, or rewrite
scenario content. It validates the complete catalog and refreshes only the
deterministic Markdown, manifest, coverage, and design-matrix projections.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas.validate import validate_scenario
from scripts.scenario_docs import write_catalog, write_document


ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = ROOT / "configs" / "scale300_v1" / "scenarios"
SCENARIO_COUNT = 300


def expected_path(root: Path, ordinal: int) -> Path:
    name = f"scenario_{ordinal:03d}"
    return root / name / f"{name}.json"


def load_catalog(root: Path):
    """Load exactly scenario_001..scenario_300 in ordinal order."""
    root = Path(root)
    expected = [expected_path(root, ordinal) for ordinal in range(1, SCENARIO_COUNT + 1)]
    missing = [path for path in expected if not path.is_file()]
    discovered = sorted(root.glob("scenario_*/scenario_*.json"))
    unexpected = sorted(set(discovered) - set(expected))
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing={len(missing)} (first: {missing[0]})")
        if unexpected:
            details.append(f"unexpected={len(unexpected)} (first: {unexpected[0]})")
        raise ValueError("Scale300 requires exactly 300 canonical files: " + "; ".join(details))

    records = []
    identifiers = set()
    for ordinal, path in enumerate(expected, start=1):
        scenario = json.loads(path.read_text(encoding="utf-8"))
        expected_id = f"IA_PIPE_{ordinal:03d}"
        if scenario.get("scenario_id") != expected_id:
            raise ValueError(
                f"{path} must contain scenario_id={expected_id}, "
                f"got {scenario.get('scenario_id')!r}"
            )
        if expected_id in identifiers:
            raise ValueError(f"duplicate scenario_id: {expected_id}")
        validate_scenario(scenario)
        identifiers.add(expected_id)
        records.append((ordinal, path, scenario))
    return records


def _time_organization(scenario):
    segments = (scenario.get("longitudinal_design") or {}).get("segments", [])
    identifiers = [item.get("segment_id") for item in segments if item.get("segment_id")]
    return " → ".join(identifiers) if identifiers else "single continuous interaction"


def design_row(ordinal, scenario):
    source = scenario["source"]
    narrative = scenario["narrative_design"]
    return {
        "scenario_id": scenario["scenario_id"],
        "title": scenario["title"],
        "relationship_category": narrative["relationship_structure"],
        "conflict_structure": narrative["goal_conflict"],
        "source_type": source["type"],
        "source_work": source.get("work_title"),
        "source_verification": source.get("provenance_note", ""),
        "primary_states": scenario.get("target_state_ids", []),
        "time_organization": _time_organization(scenario),
        "task_potential": {
            "T1": "check_after_rollout",
            "T2": "controlled_history_pair_after_canonical_selection",
            "T3": "counterfactual_branch_after_canonical_selection",
            "T4": "online_shared_environment",
        },
        "design_family": "direct_claude_authoring",
        "configuration_status": "schema_validated_pending_human_gate1",
        "generation_status": "not_rolled_out",
        "semantic_review_status": "pending_human_gate1",
        "ordinal": ordinal,
    }


def build_design_matrix(records):
    rows = [design_row(ordinal, scenario) for ordinal, _, scenario in records]
    source_counts = Counter(row["source_type"] for row in rows)
    relationship_counts = Counter(row["relationship_category"] for row in rows)
    return {
        "format": "socialflux_scale300_design_matrix_v2",
        "scenario_count": len(rows),
        "construction": "direct_claude_authoring_no_parent_catalog",
        "design_contract": {
            "turn_target": "10-20 natural; short retained; 20 cap",
            "architecture": (
                "structured appraisal LLM -> deterministic Python update -> response LLM"
            ),
            "gate1": "human review freezes initial state before rollout; runtime dynamics seed is machine-validated",
            "retention_policy": "retain every generated rollout candidate and gate failure",
            "automatic_gate_policy": (
                "machine validation cannot approve Gate 1 or set human attestation"
            ),
        },
        "source_counts": dict(sorted(source_counts.items())),
        "relationship_counts": dict(sorted(relationship_counts.items())),
        "scenarios": rows,
    }


def write_json(path: Path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate a directly authored 300-scenario catalog and refresh projections."
    )
    parser.add_argument("--scenarios", type=Path, default=SCENARIO_ROOT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate source JSON only; do not refresh Markdown or catalog projections",
    )
    args = parser.parse_args(argv)

    records = load_catalog(args.scenarios)
    matrix_path = args.scenarios.parent / "design_matrix.json"
    if not args.check:
        for _, path, _ in records:
            write_document(path)
        write_catalog(args.scenarios)
        write_json(matrix_path, build_design_matrix(records))

    print(json.dumps({
        "scenario_count": len(records),
        "source": str(args.scenarios),
        "design_matrix": str(matrix_path),
        "mode": "check" if args.check else "refresh",
        "parent_catalog": None,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
