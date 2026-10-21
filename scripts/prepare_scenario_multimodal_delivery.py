#!/usr/bin/env python3
"""Assemble auditable per-scenario multimodal delivery packages."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from environment.video_requests import (  # noqa: E402
    DELIVERY_TALKING_HEAD_PROMPT_IDS,
    TALKING_HEAD_PROMPT_ID,
)

from environment.online_multimodal import build_online_multimodal_profile  # noqa: E402
from schemas.validate import validate_scenario  # noqa: E402
from scripts.audit_formal_rollout_pool import load_records  # noqa: E402
from scripts.prepare_multimodal_video_queue import (  # noqa: E402
    importance,
    observable_behavior,
    select_important_turns,
)
from scenario_design.catalog import discover_scenario_paths
from shared.artifacts import atomic_json as atomic


DEFAULT_CONFIG = ROOT / "configs" / "multimodal_delivery.json"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical_sha256(value):
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe_media(path):
    raw = subprocess.check_output([
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,width,height,r_frame_rate",
        "-of",
        "json",
        str(path),
    ], text=True)
    payload = json.loads(raw)
    video = next(
        stream for stream in payload.get("streams", [])
        if stream.get("codec_type") == "video"
    )
    return {
        "width": video.get("width"),
        "height": video.get("height"),
        "audio_stream_count": sum(
            stream.get("codec_type") == "audio"
            for stream in payload.get("streams", [])
        ),
        "duration_seconds": round(
            float(payload.get("format", {}).get("duration", 0)), 3
        ),
    }


def target_height(render_target):
    resolution = str(render_target.get("resolution", "")).lower()
    if resolution.endswith("p") and resolution[:-1].isdigit():
        return int(resolution[:-1])
    raise ValueError(f"unsupported delivery resolution: {resolution}")


def semantic_online_request(request):
    keys = (
        "prompt_id",
        "prompt",
        "duration_seconds",
        "generate_audio",
        "ratio",
        "scenario_id",
        "event_family",
        "identity",
        "audio",
        "safety_check",
    )
    return {key: request.get(key) for key in keys}


def record_index(manifest):
    result = {}
    for record in manifest.get("requests") or []:
        key = (record.get("scenario_id"), record.get("event_family"))
        if not all(key) or key in result:
            raise ValueError(f"invalid or duplicate online request key: {key}")
        result[key] = record
    return result


def reusable_online_assets(
    batch_root, current_manifest, reuse_manifest_path, render_target
):
    if reuse_manifest_path is None:
        return {}
    source_manifest = load(reuse_manifest_path)
    source_index = record_index(source_manifest)
    reusable = {}
    for current in current_manifest.get("requests") or []:
        key = (current["scenario_id"], current["event_family"])
        source = source_index.get(key)
        if source is None:
            continue
        current_request = load(batch_root / current["request_file"])
        source_request = load(batch_root / source["request_file"])
        current_fingerprint = canonical_sha256(
            semantic_online_request(current_request)
        )
        source_fingerprint = canonical_sha256(
            semantic_online_request(source_request)
        )
        source_video = batch_root / source["video_file"]
        if current_fingerprint != source_fingerprint or not source_video.is_file():
            continue
        metadata = probe_media(source_video)
        delivery_resolution = (
            int(metadata.get("height") or 0) >= target_height(render_target)
        )
        reusable[key] = {
            "source_manifest": str(Path(reuse_manifest_path)),
            "source_request_id": source["request_id"],
            "source_video_file": source["video_file"],
            "source_video_sha256": file_sha256(source_video),
            "semantic_request_sha256": current_fingerprint,
            "technical_metadata": metadata,
            "meets_delivery_resolution": delivery_resolution,
            "status": (
                "candidate_pending_human_review"
                if delivery_resolution
                else "reference_only_below_delivery_resolution"
            ),
        }
    return reusable


def talking_records(batch_root, path):
    records = defaultdict(list)
    if path is None:
        return records, None
    manifest = load(path)
    for record in manifest.get("requests") or []:
        item = dict(record)
        item.setdefault("prompt_id", manifest.get("prompt_id"))
        video_file = item.get("video_file")
        item["video_exists"] = bool(
            video_file and (batch_root / video_file).is_file()
        )
        if item.get("prompt_id") in DELIVERY_TALKING_HEAD_PROMPT_IDS:
            item["delivery_status"] = (
                "generated_pending_human_review"
                if item["video_exists"]
                else "v3_request_ready"
            )
        else:
            item["delivery_status"] = (
                "legacy_candidate_requires_current_regeneration"
            )
        records[item["scenario_id"]].append(item)
    for values in records.values():
        values.sort(
            key=lambda value: (
                -float(value.get("importance_score", 0)),
                str(value.get("turn_id", "")),
                str(value.get("request_id", "")),
            )
        )
    return records, manifest


def merge_accepted_and_rendered_sources(accepted, rendered):
    merged = defaultdict(list)
    scenario_ids = set(accepted) | set(rendered)
    for scenario_id in scenario_ids:
        rendered_index = {}
        for record in rendered[scenario_id]:
            key = (record.get("trajectory_id"), record.get("turn_id"))
            if key in rendered_index:
                raise ValueError(
                    f"duplicate talking-head trajectory turn: {scenario_id} {key}"
                )
            rendered_index[key] = record
        for source in accepted[scenario_id]:
            key = (source.get("trajectory_id"), source.get("turn_id"))
            request = rendered_index.get(key)
            if request is None:
                merged[scenario_id].append(source)
                continue
            item = dict(source)
            item.update(request)
            item["source_public_response"] = source["source_public_response"]
            item["source_pool"] = "accepted_rollout_v3_request"
            merged[scenario_id].append(item)
        accepted_keys = {
            (item.get("trajectory_id"), item.get("turn_id"))
            for item in accepted[scenario_id]
        }
        extra = sorted(set(rendered_index) - accepted_keys)
        if extra:
            raise ValueError(
                f"talking-head requests are outside accepted sources: "
                f"{scenario_id} {extra}"
            )
    return merged


def accepted_talking_sources(rollout_root, slot_count, scenarios):
    records = defaultdict(list)
    if rollout_root is None:
        return records, None
    trajectories = load_records(rollout_root)
    for trajectory in trajectories:
        scenario_id = trajectory["scenario_id"]
        if scenario_id not in scenarios:
            raise ValueError(
                f"accepted rollout has no matching scenario: {scenario_id}"
            )
        selected = select_important_turns(trajectory, slot_count, 2)
        for score, _, turn in selected:
            _, reasons = importance(turn, len(trajectory["turns"]))
            records[trajectory["scenario_id"]].append({
                "request_id": None,
                "scenario_id": trajectory["scenario_id"],
                "trajectory_id": trajectory["trajectory_id"],
                "turn_id": turn["turn_id"],
                "importance_score": score,
                "importance_reasons": reasons,
                "source_public_response": str(
                    turn.get("environment_response", "")
                ).strip(),
                "public_response": None,
                "observable_expression": observable_behavior(
                    scenarios[scenario_id], turn
                ),
                "video_file": None,
                "video_exists": False,
                "delivery_status": "pending_public_rendering_adaptation",
                "source_pool": "accepted_rollout",
            })
    return records, trajectories


def event_designs(batch_root, scenario, online_records, reusable):
    profile = build_online_multimodal_profile(scenario)
    triggers = defaultdict(list)
    for trigger in profile["triggers"]:
        triggers[trigger["event_family"]].append({
            "trigger_id": trigger["trigger_id"],
            "source_state_family": trigger["source_state_family"],
            "source_state_variable": trigger["source_state_variable"],
            "source_direction": trigger["source_direction"],
            "conditions": trigger["conditions"],
            "change_conditions": trigger["change_conditions"],
            "cue_template": trigger["cue_template"],
            "text_fallback": trigger["observable_expression"],
        })
    result = []
    for record in sorted(
        online_records, key=lambda value: (
            value.get("dependency_phase", 9), value["event_family"]
        )
    ):
        key = (scenario["scenario_id"], record["event_family"])
        video_path = batch_root / record["video_file"]
        result.append({
            "request_id": record["request_id"],
            "event_family": record["event_family"],
            "identity_anchor": record.get("dependency_phase") == 0,
            "request_file": record["request_file"],
            "planned_video_file": record["video_file"],
            "video_exists": video_path.is_file(),
            "video_sha256": (
                record.get("video_sha256")
                or (file_sha256(video_path) if video_path.is_file() else None)
            ),
            "structural_metadata": record.get("structural_metadata"),
            "reuse_candidate": reusable.get(key),
            "activation_rules": triggers[record["event_family"]],
            "spoken_content": False,
            "audio_mode": "synchronized_response_neutral_nonverbal",
            "human_review": "pending",
        })
    return result, profile


def talking_design(records, slot_count):
    selected = records[:slot_count]
    slots = []
    for index in range(slot_count):
        if index < len(selected):
            source = selected[index]
            request_ready = bool(source.get("request_id"))
            video_exists = bool(source.get("video_exists"))
            is_legacy = source.get("source_pool", "legacy_manifest") == (
                "legacy_manifest"
            )
            slots.append({
                "slot": index + 1,
                "status": (
                    "generated_pending_human_review"
                    if video_exists
                    else "v3_request_ready"
                    if request_ready
                    else "source_node_ready_v3_request_pending"
                ),
                "source_request_id": source.get("request_id"),
                "trajectory_id": source.get("trajectory_id"),
                "turn_id": source.get("turn_id"),
                "importance_score": source.get("importance_score"),
                "source_public_response": source.get(
                    "source_public_response", source.get("public_response")
                ),
                "adapted_public_response": source.get("public_response"),
                "observable_expression": source.get("observable_expression"),
                "prompt_id": source.get("prompt_id"),
                "request_file": source.get("request_file"),
                "planned_video_file": source.get("video_file"),
                "video_exists": video_exists,
                "delivery_status": source["delivery_status"],
                "legacy_video_file": (
                    source.get("video_file") if is_legacy else None
                ),
                "legacy_video_exists": video_exists if is_legacy else False,
                "legacy_delivery_status": (
                    source["delivery_status"] if is_legacy else None
                ),
                "source_pool": source.get("source_pool", "legacy_manifest"),
                "required_prompt_id": TALKING_HEAD_PROMPT_ID,
                "required_audio_mode": "exact_public_response_with_lip_sync",
                "human_review": "pending",
            })
        else:
            slots.append({
                "slot": index + 1,
                "status": "pending_accepted_trajectory",
                "required_prompt_id": TALKING_HEAD_PROMPT_ID,
                "required_audio_mode": "exact_public_response_with_lip_sync",
                "human_review": "pending",
            })
    return slots


def prepare(args):
    config = load(args.config)
    if config.get("format") != "socialflux_multimodal_delivery_config_v1":
        raise ValueError("invalid multimodal delivery config")
    online_manifest = load(args.online_manifest)
    identity_manifest = load(args.identity_manifest)
    online_by_scenario = defaultdict(list)
    for record in online_manifest.get("requests") or []:
        online_by_scenario[record["scenario_id"]].append(record)
    reusable = reusable_online_assets(
        args.batch_root,
        online_manifest,
        args.reuse_online_manifest,
        config["render_target"],
    )
    legacy_talking_by_scenario, talking_manifest = talking_records(
        args.batch_root, args.talking_manifest
    )
    scenario_paths = discover_scenario_paths(args.scenario_root)
    scenarios = [load(path) for path in scenario_paths]
    if args.expected_count is not None and len(scenarios) != args.expected_count:
        raise ValueError(
            f"expected {args.expected_count} scenarios, found {len(scenarios)}"
        )
    for scenario in scenarios:
        validate_scenario(scenario)
    scenario_ids = {scenario["scenario_id"] for scenario in scenarios}
    if set(online_by_scenario) != scenario_ids:
        raise ValueError("online manifest does not cover the exact scenario set")

    output = args.output
    packages_root = output / "packages"
    slot_count = int(
        config["response_conditioned_talking_head"][
            "important_nodes_per_trajectory"
        ]
    )
    accepted_by_scenario, accepted_trajectories = accepted_talking_sources(
        args.accepted_rollout_root,
        slot_count,
        {scenario["scenario_id"]: scenario for scenario in scenarios},
    )
    talking_by_scenario = (
        merge_accepted_and_rendered_sources(
            accepted_by_scenario, legacy_talking_by_scenario
        )
        if args.accepted_rollout_root is not None and args.talking_manifest
        else accepted_by_scenario
        if args.accepted_rollout_root is not None
        else legacy_talking_by_scenario
    )
    summaries = []
    online_total = 0
    source_slots = 0
    v3_request_slots = 0
    legacy_generated = 0
    online_generated = 0
    for scenario in sorted(scenarios, key=lambda value: value["scenario_id"]):
        scenario_id = scenario["scenario_id"]
        identity = identity_manifest["identities"].get(scenario_id)
        if identity is None:
            raise ValueError(f"identity missing for scenario: {scenario_id}")
        events, profile = event_designs(
            args.batch_root,
            scenario,
            online_by_scenario[scenario_id],
            reusable,
        )
        slots = talking_design(talking_by_scenario[scenario_id], slot_count)
        online_total += len(events)
        online_generated += sum(event["video_exists"] for event in events)
        ready_source_count = sum(
            slot["status"] != "pending_accepted_trajectory"
            for slot in slots
        )
        v3_request_ready_count = sum(
            bool(slot.get("source_request_id")) for slot in slots
        )
        source_slots += ready_source_count
        v3_request_slots += v3_request_ready_count
        legacy_generated += sum(
            bool(slot.get("legacy_video_exists")) for slot in slots
        )
        anchor = next(event for event in events if event["identity_anchor"])
        realized_identity = dict(identity)
        realized_identity["realized_anchor"] = {
            "request_id": anchor["request_id"],
            "video_file": anchor["planned_video_file"],
            "video_sha256": anchor["video_sha256"],
            "status": (
                "generated_pending_human_review"
                if anchor["video_exists"]
                else "generation_pending"
            ),
        }
        package = {
            "format": "socialflux_scenario_multimodal_delivery_v1",
            "created_at_utc": utc_now(),
            "delivery_version": config["delivery_version"],
            "scenario_id": scenario_id,
            "scenario_sha256": profile["scenario_sha256"],
            "identity": realized_identity,
            "render_target": config["render_target"],
            "online_response_neutral": {
                "status": "design_complete_generation_pending",
                "purpose": config["online_response_neutral"]["purpose"],
                "event_count": len(events),
                "trigger_count": profile["trigger_count"],
                "state_family_trigger_counts": profile[
                    "state_family_trigger_counts"
                ],
                "events": events,
            },
            "response_conditioned_talking_head": {
                "status": (
                    "v3_requests_ready"
                    if v3_request_ready_count == ready_source_count == slot_count
                    else "source_nodes_partially_ready"
                    if ready_source_count
                    else "pending_accepted_trajectory"
                ),
                "purpose": config["response_conditioned_talking_head"][
                    "purpose"
                ],
                "required_slot_count": slot_count,
                "source_node_ready_count": ready_source_count,
                "v3_request_ready_count": v3_request_ready_count,
                "identity_reference_request_id": events[0]["request_id"],
                "identity_reference_video_file": anchor[
                    "planned_video_file"
                ],
                "identity_reference_video_sha256": anchor["video_sha256"],
                "slots": slots,
            },
            "review": {
                "online_checks": config["human_review"]["online_checks"],
                "talking_head_checks": config["human_review"][
                    "talking_head_checks"
                ],
                "human_status": "pending",
            },
            "release": {
                "runtime_ready": False,
                "status": "pending_generation_validation_human_review_and_hosting",
                "requirements": config["release"],
            },
        }
        package_path = packages_root / f"{scenario_id}.json"
        atomic(package_path, package)
        summaries.append({
            "scenario_id": scenario_id,
            "package_file": str(package_path.relative_to(args.batch_root)),
            "online_event_count": len(events),
            "online_reuse_candidate_count": sum(
                event["reuse_candidate"] is not None for event in events
            ),
            "talking_head_slot_count": slot_count,
            "talking_head_source_node_ready_count": ready_source_count,
            "talking_head_v3_request_ready_count": v3_request_ready_count,
            "runtime_ready": False,
        })

    manifest = {
        "format": "socialflux_multimodal_delivery_manifest_v1",
        "created_at_utc": utc_now(),
        "delivery_version": config["delivery_version"],
        "batch_root": str(args.batch_root.resolve()),
        "config_file": str(Path(args.config)),
        "config_sha256": canonical_sha256(config),
        "online_manifest": str(Path(args.online_manifest)),
        "online_manifest_sha256": canonical_sha256(online_manifest),
        "talking_manifest": (
            str(Path(args.talking_manifest)) if args.talking_manifest else None
        ),
        "talking_manifest_sha256": (
            canonical_sha256(talking_manifest) if talking_manifest else None
        ),
        "accepted_rollout_root": (
            str(Path(args.accepted_rollout_root))
            if args.accepted_rollout_root
            else None
        ),
        "accepted_trajectory_count": (
            len(accepted_trajectories) if accepted_trajectories is not None else 0
        ),
        "scenario_count": len(summaries),
        "online_video_design_count": online_total,
        "online_generated_count": online_generated,
        "online_reuse_candidate_count": len(reusable),
        "online_delivery_resolution_candidate_count": sum(
            item["meets_delivery_resolution"] for item in reusable.values()
        ),
        "talking_head_design_count": len(summaries) * slot_count,
        "talking_head_source_node_ready_count": source_slots,
        "talking_head_v3_request_ready_count": v3_request_slots,
        "legacy_generated_talking_head_count": legacy_generated,
        "runtime_ready_scenario_count": 0,
        "human_review_status": "pending",
        "network_requests_performed": 0,
        "scenarios": summaries,
    }
    atomic(output / "manifest.json", manifest)
    print(json.dumps({
        "scenario_count": manifest["scenario_count"],
        "online_video_design_count": manifest["online_video_design_count"],
        "online_generated_count": manifest["online_generated_count"],
        "online_reuse_candidate_count": manifest[
            "online_reuse_candidate_count"
        ],
        "online_delivery_resolution_candidate_count": manifest[
            "online_delivery_resolution_candidate_count"
        ],
        "talking_head_design_count": manifest["talking_head_design_count"],
        "talking_head_source_node_ready_count": manifest[
            "talking_head_source_node_ready_count"
        ],
        "talking_head_v3_request_ready_count": manifest[
            "talking_head_v3_request_ready_count"
        ],
        "runtime_ready_scenario_count": 0,
        "network_requests_performed": 0,
        "output": str(output),
    }, ensure_ascii=False, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument("--scenario-root", type=Path, required=True)
    parser.add_argument("--online-manifest", type=Path, required=True)
    parser.add_argument("--identity-manifest", type=Path, required=True)
    parser.add_argument("--reuse-online-manifest", type=Path)
    parser.add_argument("--talking-manifest", type=Path)
    parser.add_argument("--accepted-rollout-root", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-count", type=int)
    args = parser.parse_args(argv)
    try:
        args.output.resolve().relative_to(args.batch_root.resolve())
    except ValueError as exc:
        raise ValueError("delivery output must be inside batch_root") from exc
    prepare(args)


if __name__ == "__main__":
    main()
