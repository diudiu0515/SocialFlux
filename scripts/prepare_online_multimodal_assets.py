#!/usr/bin/env python3
"""Prepare scenario-specific online multimodal video assets without network calls."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from environment.online_multimodal import (  # noqa: E402
    ONLINE_MULTIMODAL_PROFILE,
    build_online_multimodal_profile,
)
from environment.online_video_assets import (  # noqa: E402
    ONLINE_NONVERBAL_PROMPT_ID,
    build_online_asset_request,
    online_identity_spec,
)
from prompts.loader import prompt_manifest  # noqa: E402
from schemas.validate import validate_scenario  # noqa: E402
from scenario_design.catalog import discover_scenario_paths
from shared.artifacts import atomic_json as atomic


DEFAULT_CONFIG = ROOT / "configs" / "online_multimodal_assets.json"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical_sha256(value):
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def safe_name(scenario_id, event_family):
    value = f"{scenario_id}--{event_family}".lower()
    return re.sub(r"[^a-z0-9_-]+", "_", value).strip("_")


def relative_to_batch(path, batch_root):
    try:
        return str(Path(path).resolve().relative_to(Path(batch_root).resolve()))
    except ValueError as exc:
        raise ValueError("online asset output must be inside batch_root") from exc


def ordered_families(families, anchor):
    values = sorted(set(families))
    if anchor not in values:
        raise ValueError(f"anchor event family is unavailable: {anchor}")
    return [anchor] + [value for value in values if value != anchor]


def prepare(args):
    config = load(args.config)
    if config.get("format") != "socialflux_online_multimodal_assets_v1":
        raise ValueError("invalid online multimodal asset config format")
    if config.get("profile") != ONLINE_MULTIMODAL_PROFILE:
        raise ValueError("online multimodal profile mismatch")
    if config.get("prompt_id") != ONLINE_NONVERBAL_PROMPT_ID:
        raise ValueError("online multimodal prompt_id mismatch")

    scenario_paths = discover_scenario_paths(args.scenario_root)
    scenarios = [load(path) for path in scenario_paths]
    if args.expected_count is not None and len(scenarios) != args.expected_count:
        raise ValueError(
            f"expected {args.expected_count} scenarios, found {len(scenarios)}"
        )
    if not scenarios:
        raise ValueError("no scenarios discovered")
    for scenario in scenarios:
        validate_scenario(scenario)

    output = args.output or args.batch_root / "online_multimodal"
    relative_to_batch(output, args.batch_root)
    requests_root = output / "requests"
    assets_root = output / "assets"
    anchor_family = config["anchor_event_family"]
    duration = float(config["duration_seconds"])
    asset_version = config["asset_version"]

    specs = []
    identities = {}
    for scenario in sorted(scenarios, key=lambda value: value["scenario_id"]):
        profile = build_online_multimodal_profile(scenario)
        families = ordered_families(profile["event_families"], anchor_family)
        identity = online_identity_spec(scenario)
        identity_id = identity["identity_id"]
        if identity_id in identities:
            raise ValueError(f"duplicate online identity_id: {identity_id}")
        identities[identity_id] = scenario["scenario_id"]
        specs.append((scenario, profile, families, identity))

    anchor_paths = {
        scenario["scenario_id"]: assets_root
        / f"{safe_name(scenario['scenario_id'], anchor_family)}.mp4"
        for scenario, _, _, _ in specs
    }
    records = []
    pending_assets = {}
    for phase in (0, 1):
        for scenario, profile, families, identity in specs:
            scenario_id = scenario["scenario_id"]
            for event_family in families:
                is_anchor = event_family == anchor_family
                if (phase == 0) != is_anchor:
                    continue
                stem = safe_name(scenario_id, event_family)
                request_path = requests_root / f"{stem}.json"
                video_path = assets_root / f"{stem}.mp4"
                reference_file = (
                    None
                    if is_anchor
                    else relative_to_batch(anchor_paths[scenario_id], args.batch_root)
                )
                request = build_online_asset_request(
                    scenario,
                    event_family,
                    duration_seconds=duration,
                    reference_video_file=reference_file,
                )
                if not request["prompt"].isascii():
                    raise ValueError(
                        f"online asset prompt must be English: {scenario_id}"
                    )
                if any(request["safety_check"].values()):
                    raise ValueError(
                        f"unsafe online asset request: {scenario_id} {event_family}"
                    )
                atomic(request_path, request)
                request_id = (
                    f"{scenario_id}--{asset_version}--{event_family}"
                )
                media_asset_id = (
                    f"{scenario_id}:{asset_version}:{event_family}"
                )
                record = {
                    "request_id": request_id,
                    "scenario_id": scenario_id,
                    "event_family": event_family,
                    "media_asset_id": media_asset_id,
                    "identity_id": identity["identity_id"],
                    "dependency_phase": phase,
                    "reference_request_id": (
                        None
                        if is_anchor
                        else f"{scenario_id}--{asset_version}--{anchor_family}"
                    ),
                    "request_file": relative_to_batch(
                        request_path, args.batch_root
                    ),
                    "video_file": relative_to_batch(video_path, args.batch_root),
                    "status": "request_ready",
                    "response_neutral": True,
                    "spoken_content": False,
                    "audio_mode": "synchronized_response_neutral_nonverbal",
                    "duration_seconds": duration,
                    "scenario_profile_sha256": profile["scenario_sha256"],
                }
                records.append(record)
                pending_assets.setdefault(scenario_id, {})[event_family] = {
                    "media_asset_id": media_asset_id,
                    "duration_seconds": duration,
                    "status": "request_ready",
                    "expected_asset_path": record["video_file"],
                    "request_id": request_id,
                }

    family_counts = {}
    for record in records:
        family = record["event_family"]
        family_counts[family] = family_counts.get(family, 0) + 1
    manifest = {
        "format": "socialflux_online_multimodal_asset_queue_v1",
        "created_at_utc": utc_now(),
        "batch_root": str(args.batch_root.resolve()),
        "mode": "online_response_neutral",
        "profile": ONLINE_MULTIMODAL_PROFILE,
        "prompt_id": ONLINE_NONVERBAL_PROMPT_ID,
        "prompt_sha256": prompt_manifest()["prompts"][
            ONLINE_NONVERBAL_PROMPT_ID
        ]["sha256"],
        "asset_version": asset_version,
        "config_file": str(Path(args.config)),
        "config_sha256": canonical_sha256(config),
        "provider": config["provider"],
        "network_requests_performed": 0,
        "provider_status": "request_ready",
        "scenario_count": len(scenarios),
        "request_count": len(records),
        "anchor_request_count": sum(
            item["dependency_phase"] == 0 for item in records
        ),
        "dependent_request_count": sum(
            item["dependency_phase"] == 1 for item in records
        ),
        "event_family_counts": dict(sorted(family_counts.items())),
        "generation_order": [
            "anchors: one activated_tension asset per scenario",
            "dependents: remaining families use the scenario anchor as reference_video",
        ],
        "requests": records,
    }
    review = {
        "format": "socialflux_online_multimodal_asset_review_v1",
        "created_at_utc": utc_now(),
        "requirements": config["review"],
        "reviewed_count": 0,
        "passed_count": 0,
        "items": [
            {
                "request_id": item["request_id"],
                "scenario_id": item["scenario_id"],
                "event_family": item["event_family"],
                "media_asset_id": item["media_asset_id"],
                "video_file": item["video_file"],
                "anchor_video_file": (
                    item["video_file"]
                    if item["dependency_phase"] == 0
                    else relative_to_batch(
                        anchor_paths[item["scenario_id"]], args.batch_root
                    )
                ),
                "human_status": "pending",
                "reviewer": "",
                "reviewed_at_utc": "",
                "checks": {
                    "identity_matches_anchor": None,
                    "family_cue_alignment": None,
                    "audio_track_present": None,
                    "family_audio_cue_alignment": None,
                    "no_speech_or_mouthing": None,
                    "no_visible_text_or_branding": None,
                    "subtle_natural_motion": None,
                    "natural_synchronized_audio": None,
                },
                "notes": "",
            }
            for item in records
        ],
    }
    identity_manifest = {
        "format": "socialflux_online_multimodal_identity_manifest_v1",
        "created_at_utc": utc_now(),
        "cross_scenario_identity_reuse": False,
        "identities": {
            scenario["scenario_id"]: identity
            for scenario, _, _, identity in specs
        },
    }
    pending = {
        "format": "socialflux_online_multimodal_event_assets_pending_v1",
        "created_at_utc": utc_now(),
        "profile": ONLINE_MULTIMODAL_PROFILE,
        "runtime_ready": False,
        "note": (
            "expected_asset_path is planning metadata only; do not load this file "
            "into T4 until generation, review, hosting, and asset_url finalization."
        ),
        "event_assets": pending_assets,
    }
    atomic(output / "manifest.json", manifest)
    atomic(output / "asset_review.json", review)
    atomic(output / "identity_manifest.json", identity_manifest)
    atomic(output / "event_assets.pending.json", pending)
    print(json.dumps({
        "scenario_count": len(scenarios),
        "request_count": len(records),
        "anchor_request_count": manifest["anchor_request_count"],
        "dependent_request_count": manifest["dependent_request_count"],
        "network_requests_performed": 0,
        "output": str(output),
    }, ensure_ascii=False, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument("--scenario-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expected-count", type=int)
    args = parser.parse_args(argv)
    prepare(args)


if __name__ == "__main__":
    main()
