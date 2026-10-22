#!/usr/bin/env python3
"""Build a blind human annotation packet from complete scenario/rollout context."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from environment.state_ontology import build_state_semantics


DEFAULT_MANIFEST = (
    ROOT
    / "data/gpt50/experiment/state_v3_validation"
    / "v3227_independent_per_variable/fixed_set_preregistration.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "data/gpt50/experiment/state_v3_validation"
    / "human_annotation_round1/packet.json"
)

JUDGMENTS = (
    "no_relevant_evidence",
    "repeated_evidence_only",
    "ordinary_new_evidence",
    "decisive_new_evidence",
)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative(path):
    return str(Path(path).resolve().relative_to(ROOT))


def blank_annotation():
    return {
        "status": "pending",
        "judgment": None,
        "direction": None,
        "evidence_span": "",
        "directness": None,
        "should_update_this_turn": None,
        "rationale": "",
        "confidence_1_to_5": None,
        "label_is_ambiguous": None,
        "ambiguity_note": "",
        "reviewer_note": "",
    }


def blind_turn(turn):
    """Keep full dialogue and pre-turn context, but hide model judgments/deltas."""
    return {
        "turn_id": turn.get("turn_id"),
        "policy_action": turn.get("policy_action"),
        "environment_response": turn.get("environment_response"),
        "state_before": turn.get("state_before"),
        "dynamics_before": turn.get("dynamics_before"),
        "memory_view": turn.get("memory_view"),
        "interaction_ledger_before": turn.get("interaction_ledger_before"),
        "observation": turn.get("observation"),
    }


def build_packet(manifest_path):
    manifest = load(manifest_path)
    grouped = []
    by_source = {}
    for case in manifest["cases"]:
        source = case["source"]
        if source not in by_source:
            record = {
                "source": source,
                "scenario": case["scenario"],
                "targets": [],
            }
            grouped.append(record)
            by_source[source] = record
        by_source[source]["targets"].append(case)

    records = []
    for ordinal, source_record in enumerate(grouped, start=1):
        scenario_path = ROOT / source_record["scenario"]
        rollout_path = ROOT / source_record["source"]
        scenario = load(scenario_path)
        rollout = load(rollout_path)
        semantics = build_state_semantics(scenario)["variables"]
        targets = []
        for case in source_record["targets"]:
            variable = case["target"]
            targets.append({
                "annotation_id": case["case_id"],
                "turn_id": case["turn_id"],
                "variable": variable,
                "variable_semantics": semantics[variable],
                "human_annotation": blank_annotation(),
            })
        records.append({
            "record_id": f"round1_{ordinal:02d}_{rollout['scenario_id']}",
            "scenario_id": rollout["scenario_id"],
            "trajectory_id": rollout["trajectory_id"],
            "scenario_path": relative(scenario_path),
            "scenario_sha256": sha256(scenario_path),
            "rollout_path": relative(rollout_path),
            "rollout_sha256": sha256(rollout_path),
            "turn_count": len(rollout.get("turns", [])),
            "target_count": len(targets),
            "scenario": scenario,
            "rollout_overview": {
                key: rollout.get(key)
                for key in (
                    "trajectory_id", "scenario_id", "policy_id",
                    "policy_provenance", "environment_provenance",
                    "initial_state", "initial_dynamics", "segments",
                    "public_timeline", "ending", "public_scenario_context",
                )
            },
            "turns": [blind_turn(turn) for turn in rollout.get("turns", [])],
            "targets": targets,
        })

    packet = {
        "format": "socialflux_state_human_annotation_round_v2",
        "round_id": "state_semantics_v7_round1_20261004",
        "interface_revision": "state_judgment_primary_v7",
        # Bind metadata to the frozen preregistration so rebuilding the same
        # packet produces the same content hash.
        "generated_at_utc": manifest["created_at_utc"],
        "source_manifest": relative(manifest_path),
        "blind_to_model_answers": True,
        "model_calls": 0,
        "instructions": {
            "purpose": (
                "Independently label the target variable using the complete "
                "scenario and dialogue history. Existing model labels are hidden."
            ),
            "actor_rule": (
                "The latest policy_action is authored by evaluated_agent. "
                "Mutable state belongs to environment_agent and expresses that "
                "character's judgment or disposition toward evaluated_agent."
            ),
            "evidence_rule": (
                "Only the target turn's policy_action can be new evidence. "
                "Earlier turns determine meaning and whether it is repeated."
            ),
            "judgments": list(JUDGMENTS),
            "feature_policy": (
                "Generic event features are auxiliary diagnostics and are not "
                "human ground-truth fields. Do not infer a feature merely to "
                "justify the variable judgment."
            ),
            "features": [],
            "privacy": (
                "Scenario private fields are shown to the human annotator only; "
                "they must not be added to evaluated policy input."
            ),
            "recommended_order": [
                "Read the complete scenario and variable definition.",
                "Read only through the target action; do not use its response or future turns.",
                "Copy an exact evidence span from the target policy_action.",
                "Choose the four-way judgment before deciding whether v7 should update this turn.",
                "Do not label a generic feature or numeric delta; Python handles calibration.",
                "Mark ambiguity explicitly rather than forcing agreement.",
            ],
        },
        "annotation_schema": blank_annotation(),
        "summary": {
            "record_count": len(records),
            "scenario_count": len({item["scenario_id"] for item in records}),
            "complete_rollout_turn_count": sum(item["turn_count"] for item in records),
            "required_target_count": sum(item["target_count"] for item in records),
        },
        "records": records,
    }
    canonical = json.dumps(
        packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    packet["packet_sha256"] = hashlib.sha256(canonical).hexdigest()
    return packet


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    packet = build_packet(args.manifest.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(json.dumps({
        "output": str(args.output),
        "packet_sha256": packet["packet_sha256"],
        **packet["summary"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
