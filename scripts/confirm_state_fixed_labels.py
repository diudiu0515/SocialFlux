#!/usr/bin/env python3
"""Validate a complete blind annotation export and freeze adjudicated labels."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    ROOT
    / "data/gpt50/experiment/state_v3_validation"
    / "v3227_independent_per_variable/fixed_set_preregistration.json"
)
DEFAULT_PACKET = (
    ROOT
    / "data/gpt50/experiment/state_v3_validation"
    / "human_annotation_round1/packet.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "data/gpt50/experiment/state_v3_validation"
    / "v323_state_judgment_primary/human_confirmed_fixed_set.json"
)

JUDGMENT_STRENGTH = {
    "no_relevant_evidence": 0,
    "repeated_evidence_only": 0,
    "ordinary_new_evidence": 1,
    "decisive_new_evidence": 2,
}


def load(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def packet_content_sha256(packet: dict) -> str:
    value = {key: item for key, item in packet.items() if key != "packet_sha256"}
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def relative(path: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def validate_annotation(annotation_id: str, annotation: dict) -> dict:
    if annotation.get("status") != "complete":
        raise ValueError(f"{annotation_id}: annotation status is not complete")
    judgment = annotation.get("judgment")
    if judgment not in JUDGMENT_STRENGTH:
        raise ValueError(f"{annotation_id}: invalid or missing judgment")
    is_new = judgment in {"ordinary_new_evidence", "decisive_new_evidence"}
    direction = annotation.get("direction")
    if is_new and direction not in {"increase", "decrease"}:
        raise ValueError(f"{annotation_id}: new evidence requires a direction")
    if not is_new and direction is not None:
        raise ValueError(f"{annotation_id}: non-new evidence must not have a direction")
    if is_new and annotation.get("directness") not in {"direct", "indirect"}:
        raise ValueError(f"{annotation_id}: new evidence requires directness")
    if is_new and not str(annotation.get("evidence_span") or "").strip():
        raise ValueError(f"{annotation_id}: new evidence requires an exact span")
    if not is_new and str(annotation.get("evidence_span") or "").strip():
        raise ValueError(f"{annotation_id}: non-new evidence must not cite a new span")
    if not is_new and annotation.get("directness") is not None:
        raise ValueError(f"{annotation_id}: non-new evidence must not have directness")
    if not is_new and annotation.get("evidence_feature") is not None:
        raise ValueError(f"{annotation_id}: non-new evidence must not have a feature")
    if not str(annotation.get("rationale") or "").strip():
        raise ValueError(f"{annotation_id}: rationale is required")
    confidence = annotation.get("confidence_1_to_5")
    if confidence not in {1, 2, 3, 4, 5}:
        raise ValueError(f"{annotation_id}: confidence must be 1..5")
    ambiguous = annotation.get("label_is_ambiguous")
    if ambiguous not in {"yes", "no"}:
        raise ValueError(f"{annotation_id}: ambiguity decision is required")
    if ambiguous == "yes" and not str(annotation.get("ambiguity_note") or "").strip():
        raise ValueError(f"{annotation_id}: ambiguous labels require a note")
    return {
        "judgment": judgment,
        "direction": direction,
        "semantic_strength": JUDGMENT_STRENGTH[judgment],
        "evidence_span": str(annotation.get("evidence_span") or "").strip(),
        "directness": annotation.get("directness") if is_new else None,
        "evidence_feature": annotation.get("evidence_feature"),
        "reviewer_update_opinion": (
            True if annotation.get("should_update_this_turn") == "yes"
            else False if annotation.get("should_update_this_turn") == "no"
            else None
        ),
        "rationale": str(annotation["rationale"]).strip(),
        "confidence_1_to_5": confidence,
        "ambiguous": ambiguous == "yes",
        "ambiguity_note": str(annotation.get("ambiguity_note") or "").strip(),
        "reviewer_note": str(annotation.get("reviewer_note") or "").strip(),
    }


def build_confirmed_manifest(manifest_path: Path, packet_path: Path, export_path: Path):
    manifest = load(manifest_path)
    packet = load(packet_path)
    exported = load(export_path)

    calculated_packet_hash = packet_content_sha256(packet)
    if packet.get("packet_sha256") != calculated_packet_hash:
        raise ValueError("annotation packet content hash is invalid")
    if exported.get("format") != "socialflux_state_human_annotations_v1":
        raise ValueError("unsupported annotation export format")
    if exported.get("round_id") != packet.get("round_id"):
        raise ValueError("annotation export round_id does not match packet")
    if exported.get("packet_sha256") != packet.get("packet_sha256"):
        raise ValueError("annotation export packet hash does not match packet")
    reviewer = str(exported.get("reviewer") or "").strip()
    if not reviewer:
        raise ValueError("annotation export must identify the human reviewer")

    packet_ids = {
        target["annotation_id"]
        for record in packet["records"]
        for target in record["targets"]
    }
    manifest_ids = {case["case_id"] for case in manifest["cases"]}
    exported_annotations = exported.get("annotations") or {}
    export_ids = set(exported_annotations)
    if packet_ids != manifest_ids:
        raise ValueError("packet targets do not match preregistered cases")
    if export_ids != packet_ids:
        missing = sorted(packet_ids - export_ids)
        extra = sorted(export_ids - packet_ids)
        raise ValueError(f"annotation export target mismatch; missing={missing}, extra={extra}")

    target_context = {}
    allowed_features = set(packet["instructions"].get("features", []))
    for record in packet["records"]:
        turns = {turn["turn_id"]: turn for turn in record["turns"]}
        for target in record["targets"]:
            action = turns[target["turn_id"]]["policy_action"]
            target_context[target["annotation_id"]] = (
                action.get("text", "") if isinstance(action, dict) else str(action or "")
            )

    cases = []
    disagreements = []
    ambiguous_ids = []
    for original in manifest["cases"]:
        case = deepcopy(original)
        label = validate_annotation(
            case["case_id"], exported_annotations[case["case_id"]]
        )
        feature = label["evidence_feature"]
        if feature is not None and feature not in allowed_features:
            raise ValueError(f"{case['case_id']}: unsupported evidence feature {feature}")
        if (
            label["evidence_span"]
            and label["evidence_span"] not in target_context[case["case_id"]]
        ):
            raise ValueError(
                f"{case['case_id']}: evidence span is not verbatim in target action"
            )
        preregistered_label = {
            "judgment": case.get("expected_judgment"),
            "direction": case.get("expected_direction"),
            "semantic_strength": case.get("expected_semantic_strength"),
            "requires_nonzero_final_update": case.get(
                "requires_nonzero_final_update"
            ),
            "rationale": case.get("label_rationale"),
        }
        differing_fields = [
            name
            for name in (
                "judgment",
                "direction",
                "semantic_strength",
            )
            if preregistered_label[name] != label[name]
        ]
        case["preregistered_label"] = preregistered_label
        case["adjudicated_label"] = label
        case["human_confirmation"] = "complete"
        if differing_fields:
            disagreements.append({
                "case_id": case["case_id"],
                "differing_fields": differing_fields,
                "preregistered": preregistered_label,
                "adjudicated": label,
            })
        if label["ambiguous"]:
            ambiguous_ids.append(case["case_id"])
        cases.append(case)

    return {
        "format": "socialflux_human_confirmed_state_fixed_set_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "human_labels_complete",
        "source_manifest": relative(manifest_path),
        "source_manifest_sha256": file_sha256(manifest_path),
        "annotation_packet": relative(packet_path),
        "annotation_packet_file_sha256": file_sha256(packet_path),
        "annotation_packet_content_sha256": calculated_packet_hash,
        "annotation_export": relative(export_path),
        "annotation_export_sha256": file_sha256(export_path),
        "human_confirmation": {
            "status": "complete",
            "reviewer": reviewer,
            "exported_at_utc": exported.get("exported_at_utc"),
            "imported_at_utc": datetime.now(timezone.utc).isoformat(),
            "required_case_count": len(packet_ids),
            "confirmed_case_count": len(cases),
            "ambiguous_case_ids": ambiguous_ids,
        },
        "label_comparison": {
            "preregistered_labels_are_not_ground_truth": True,
            "disagreement_count": len(disagreements),
            "disagreements": disagreements,
        },
        "comparison": deepcopy(manifest.get("comparison", {})),
        "preplanned_boundary_retest_case_ids": deepcopy(
            manifest.get("preplanned_boundary_retest_case_ids", [])
        ),
        "cases": cases,
    }


def atomic_write(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("annotation_export", type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    result = build_confirmed_manifest(
        args.manifest.resolve(), args.packet.resolve(), args.annotation_export.resolve()
    )
    atomic_write(args.output, result)
    print(json.dumps({
        "output": str(args.output),
        "reviewer": result["human_confirmation"]["reviewer"],
        "confirmed_case_count": len(result["cases"]),
        "ambiguous_case_ids": result["human_confirmation"]["ambiguous_case_ids"],
        "preregistered_disagreement_count": result["label_comparison"]["disagreement_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
