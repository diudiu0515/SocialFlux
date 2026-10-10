#!/usr/bin/env python3
"""Revise queued online video prompts without overwriting generated evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from environment.online_video_assets import (  # noqa: E402
    ONLINE_NONVERBAL_PROMPT_ID,
    build_online_asset_request,
)
from prompts.loader import prompt_manifest  # noqa: E402
from scripts.prepare_online_multimodal_assets import safe_name  # noqa: E402
from scripts.scenario_docs import discover_scenario_paths  # noqa: E402


LEGACY_PROMPT_ID = "online_nonverbal_event_v1"
AUDIO_REVIEW_CHECKS = (
    "identity_matches_anchor",
    "family_cue_alignment",
    "audio_track_present",
    "family_audio_cue_alignment",
    "no_speech_or_mouthing",
    "no_visible_text_or_branding",
    "subtle_natural_motion",
    "natural_synchronized_audio",
)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def relative(path, root):
    return str(Path(path).resolve().relative_to(Path(root).resolve()))


def state_file_for(batch_root, request_file):
    request_path = Path(request_file)
    return (
        Path(batch_root)
        / request_path.parent.parent
        / "provider_states"
        / f"{request_path.stem}.json"
    )


def _previous_evidence(batch_root, record):
    state_path = state_file_for(batch_root, record["request_file"])
    state = load(state_path) if state_path.is_file() else {}
    return {
        "request_file": record["request_file"],
        "provider_state_file": (
            relative(state_path, batch_root) if state_path.is_file() else None
        ),
        "provider_task_id": state.get("task_id"),
        "status": record.get("status"),
        "video_file": record.get("video_file"),
        "video_sha256": record.get("video_sha256"),
    }


def revise(args):
    batch_root = Path(args.batch_root)
    default_queue_root = batch_root / "online_multimodal"
    manifest_path = args.manifest or default_queue_root / "manifest.json"
    queue_root = manifest_path.parent
    review_path = args.review or queue_root / "asset_review.json"
    manifest = load(manifest_path)
    review = load(review_path)
    config = load(ROOT / "configs" / "online_multimodal_assets.json")
    review["requirements"] = config["review"]

    scenarios = {
        value["scenario_id"]: value
        for path in discover_scenario_paths(args.scenario_root)
        for value in [load(path)]
    }
    requested = set(args.replacement_scenario or [])
    requested_families = set(args.replacement_family or [])
    missing = requested - set(scenarios)
    if missing:
        raise ValueError(f"replacement scenarios are missing: {sorted(missing)}")
    prompt_entry = prompt_manifest()["prompts"][ONLINE_NONVERBAL_PROMPT_ID]
    review_by_id = {
        item["request_id"]: item for item in review.get("items", [])
    }
    anchor_family = args.anchor_event_family
    replacement_count = 0
    upgraded_pending_count = 0

    for record in manifest.get("requests", []):
        scenario_id = record["scenario_id"]
        family = record["event_family"]
        previous_request = load(batch_root / record["request_file"])
        prior = _previous_evidence(batch_root, record)
        record.setdefault(
            "prompt_id", previous_request.get("prompt_id", LEGACY_PROMPT_ID)
        )
        is_replacement = (
            scenario_id in requested
            and (not requested_families or family in requested_families)
        )
        is_pending_upgrade = (
            args.upgrade_request_ready
            and not is_replacement
            and record.get("status") == "request_ready"
        )
        if not is_replacement and not is_pending_upgrade:
            continue

        is_anchor = family == anchor_family
        stem = safe_name(scenario_id, family)
        suffix = args.replacement_suffix if is_replacement else "v3"
        request_path = queue_root / "requests" / f"{stem}-{suffix}.json"
        video_path = (
            queue_root / "assets" / f"{stem}-{suffix}.mp4"
            if is_replacement
            else batch_root / record["video_file"]
        )
        anchor_suffix = (
            args.reference_anchor_suffix or args.replacement_suffix
        )
        anchor_path = (
            queue_root
            / "assets"
            / f"{safe_name(scenario_id, anchor_family)}-{anchor_suffix}.mp4"
            if is_replacement
            else queue_root
            / "assets"
            / f"{safe_name(scenario_id, anchor_family)}.mp4"
        )
        if is_replacement and args.reference_mode == "previous_video":
            previous_video = batch_root / prior["video_file"]
            if not previous_video.is_file():
                raise ValueError(
                    f"previous reference video is missing: {previous_video}"
                )
            reference = prior["video_file"]
        else:
            reference = None if is_anchor else relative(anchor_path, batch_root)
        request = build_online_asset_request(
            scenarios[scenario_id],
            family,
            duration_seconds=record["duration_seconds"],
            reference_video_file=reference,
            preserve_reference_motion=(args.reference_mode == "previous_video"),
        )
        request["revision"] = {
            "supersedes_request_file": record["request_file"],
            "reason": args.reason,
            "reference_mode": args.reference_mode,
            "created_at_utc": utc_now(),
        }
        atomic(request_path, request)

        history = record.setdefault("replacement_history", [])
        if not any(
            item.get("request_file") == prior["request_file"]
            for item in history
        ):
            history.append({**prior, "reason": args.reason})
        record["request_file"] = relative(request_path, batch_root)
        record["audio_mode"] = "synchronized_response_neutral_nonverbal"
        record["prompt_id"] = ONLINE_NONVERBAL_PROMPT_ID
        record["prompt_sha256"] = prompt_entry["sha256"]

        if is_replacement:
            record["video_file"] = relative(video_path, batch_root)
            record["status"] = "request_ready"
            for key in (
                "video_sha256",
                "video_bytes",
                "structural_metadata",
                "validation_error",
            ):
                record.pop(key, None)
            review_item = review_by_id[record["request_id"]]
            review_item.update({
                "video_file": record["video_file"],
                "anchor_video_file": relative(anchor_path, batch_root),
                "human_status": "pending",
                "reviewer": "",
                "reviewed_at_utc": "",
                "notes": (
                    "Audiovisual replacement pending review: verify distinct "
                    "motion, synchronized nonverbal sound, and no speech."
                ),
            })
            review_item["checks"] = {
                key: None for key in AUDIO_REVIEW_CHECKS
            }
            replacement_count += 1
        else:
            review_item = review_by_id[record["request_id"]]
            review_item.update({
                "human_status": "pending",
                "reviewer": "",
                "reviewed_at_utc": "",
                "notes": "Pending v3 audiovisual generation and human review.",
            })
            review_item["checks"] = {
                key: None for key in AUDIO_REVIEW_CHECKS
            }
            upgraded_pending_count += 1

    revision = {
        "created_at_utc": utc_now(),
        "from_prompt_id": LEGACY_PROMPT_ID,
        "to_prompt_id": ONLINE_NONVERBAL_PROMPT_ID,
        "to_prompt_sha256": prompt_entry["sha256"],
        "replacement_scenarios": sorted(requested),
        "replacement_families": sorted(requested_families),
        "replacement_suffix": args.replacement_suffix,
        "reference_mode": args.reference_mode,
        "replacement_asset_count": replacement_count,
        "upgraded_request_ready_count": upgraded_pending_count,
        "reason": args.reason,
    }
    history = manifest.setdefault("prompt_revision_history", [])
    if not any(
        item.get("to_prompt_sha256") == revision["to_prompt_sha256"]
        and item.get("replacement_scenarios") == revision["replacement_scenarios"]
        and item.get("replacement_suffix") == revision["replacement_suffix"]
        and item.get("reference_mode") == revision["reference_mode"]
        and item.get("replacement_families") == revision["replacement_families"]
        for item in history
    ):
        history.append(revision)
    manifest.update({
        "active_prompt_id": ONLINE_NONVERBAL_PROMPT_ID,
        "active_prompt_sha256": prompt_entry["sha256"],
        "provider_status": "partially_generated",
    })
    review["reviewed_count"] = sum(
        item.get("human_status") != "pending" for item in review["items"]
    )
    review["passed_count"] = sum(
        item.get("human_status") == "passed" for item in review["items"]
    )
    review["updated_at_utc"] = utc_now()
    atomic(manifest_path, manifest)
    atomic(review_path, review)
    print(json.dumps({
        "prompt_id": ONLINE_NONVERBAL_PROMPT_ID,
        "replacement_scenario_count": len(requested),
        "replacement_asset_count": replacement_count,
        "upgraded_request_ready_count": upgraded_pending_count,
        "network_requests_performed": 0,
    }, ensure_ascii=False, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--batch-root",
        type=Path,
        default=ROOT / "data" / "gpt50" / "experiment",
    )
    parser.add_argument(
        "--scenario-root",
        type=Path,
        default=(
            ROOT / "data" / "gpt50" / "experiment" / "scenario" / "scenarios"
        ),
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--reference-mode",
        choices=("anchor", "previous_video"),
        default="anchor",
    )
    parser.add_argument("--review", type=Path)
    parser.add_argument(
        "--replacement-scenario", action="append"
    )
    parser.add_argument("--replacement-family", action="append")
    parser.add_argument("--replacement-suffix", default="r2")
    parser.add_argument("--reference-anchor-suffix")
    parser.add_argument(
        "--anchor-event-family", default="activated_tension"
    )
    parser.add_argument("--upgrade-request-ready", action="store_true")
    parser.add_argument(
        "--reason",
        default=(
            "Upgrade online cues to prompt v3 with distinct visible motion and "
            "synchronized response-neutral nonverbal audio."
        ),
    )
    args = parser.parse_args(argv)
    if not args.replacement_scenario and not args.upgrade_request_ready:
        parser.error(
            "select --replacement-scenario and/or --upgrade-request-ready"
        )
    revise(args)


if __name__ == "__main__":
    main()
