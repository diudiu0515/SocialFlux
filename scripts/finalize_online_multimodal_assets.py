#!/usr/bin/env python3
"""Validate online cue videos and emit reviewed runtime asset mappings."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import quote


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


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe(path):
    raw = subprocess.check_output([
        "ffprobe", "-v", "error",
        "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
        "-of", "json", str(path),
    ], text=True)
    payload = json.loads(raw)
    streams = payload.get("streams", [])
    video = next(
        (item for item in streams if item.get("codec_type") == "video"),
        None,
    )
    if video is None:
        raise ValueError("generated asset has no video stream")
    audio = [
        item for item in streams if item.get("codec_type") == "audio"
    ]
    rate = video.get("r_frame_rate", "0/1")
    return {
        "duration_seconds_actual": round(
            float(payload.get("format", {}).get("duration", 0)), 3
        ),
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": round(float(Fraction(rate)), 3) if rate != "0/0" else 0,
        "audio_stream_count": len(audio),
        "audio_codec": audio[0].get("codec_name") if audio else None,
        "audio_sample_rate": audio[0].get("sample_rate") if audio else None,
        "audio_channels": audio[0].get("channels") if audio else None,
    }


def public_url(base_url, video_file):
    return f"{base_url.rstrip('/')}/{quote(Path(video_file).name)}"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--asset-base-url")
    parser.add_argument("--skip-probe", action="store_true")
    parser.add_argument("--minimum-height", type=int, default=0)
    args = parser.parse_args(argv)
    if args.skip_probe and args.asset_base_url:
        parser.error("--skip-probe cannot be used when emitting hosted runtime assets")

    default_queue_root = args.batch_root / "online_multimodal"
    manifest_path = args.manifest or default_queue_root / "manifest.json"
    queue_root = manifest_path.parent
    review_path = args.review or queue_root / "asset_review.json"
    manifest = load(manifest_path)
    review = load(review_path)
    review_by_id = {
        item["request_id"]: item for item in review.get("items", [])
    }
    records = manifest.get("requests") or []
    errors = []
    provider_failures = []
    generated = 0
    structurally_passed = 0
    reviewed = 0
    passed = 0
    runtime_assets = {}

    for item in records:
        video_path = args.batch_root / item["video_file"]
        review_item = review_by_id.get(item["request_id"])
        if review_item is None:
            raise ValueError(
                f"review item missing for request: {item['request_id']}"
            )
        if not video_path.is_file():
            state_path = (
                queue_root
                / "provider_states"
                / f"{Path(item['request_file']).stem}.json"
            )
            state = load(state_path) if state_path.is_file() else {}
            if state.get("status") in {"failed", "expired", "cancelled"}:
                provider_error = (
                    (state.get("latest_query_response") or {}).get("error")
                    or state.get("last_queue_error")
                    or {}
                )
                item.update({
                    "status": "provider_failed",
                    "provider_task_id": state.get("task_id"),
                    "provider_error": provider_error,
                })
                provider_failures.append({
                    "request_id": item["request_id"],
                    "provider_task_id": state.get("task_id"),
                    "error": provider_error,
                })
            else:
                item["status"] = "request_ready"
            continue
        generated += 1
        request = load(args.batch_root / item["request_file"])
        expects_audio = request.get("generate_audio") is True
        try:
            metadata = {} if args.skip_probe else probe(video_path)
            duration = metadata.get("duration_seconds_actual")
            if duration is not None and not 3.5 <= duration <= 5.5:
                raise ValueError(
                    f"online cue duration outside 4-second tolerance: {duration}"
                )
            height = metadata.get("height")
            if (
                args.minimum_height
                and (height is None or int(height) < args.minimum_height)
            ):
                raise ValueError(
                    "online cue is below minimum delivery height: "
                    f"{height} < {args.minimum_height}"
                )
            audio_count = metadata.get("audio_stream_count", 0)
            if expects_audio and audio_count != 1:
                raise ValueError("audiovisual online cue must contain one audio stream")
            if not expects_audio and audio_count:
                raise ValueError("silent online cue must not contain an audio stream")
            item.update({
                "status": "generated_structural_pass",
                "audio_required": expects_audio,
                "video_sha256": sha256(video_path),
                "video_bytes": video_path.stat().st_size,
                "structural_metadata": metadata,
            })
            structurally_passed += 1
        except Exception as exc:
            item.update({
                "status": "generated_structural_fail",
                "validation_error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            })
            errors.append({
                "request_id": item["request_id"],
                **item["validation_error"],
            })
            continue

        human_status = review_item.get("human_status")
        if human_status != "pending":
            reviewed += 1
        checks = review_item.get("checks") or {}
        human_pass = (
            human_status == "passed"
            and checks
            and all(value is True for value in checks.values())
        )
        if not human_pass:
            continue
        passed += 1
        if not args.asset_base_url:
            continue
        runtime_assets.setdefault(item["scenario_id"], {})[
            item["event_family"]
        ] = {
            "media_asset_id": item["media_asset_id"],
            "asset_path": item["video_file"],
            "asset_url": public_url(args.asset_base_url, item["video_file"]),
            "duration_seconds": item["duration_seconds"],
            "video_sha256": item["video_sha256"],
            "review_status": "passed",
        }

    review["reviewed_count"] = reviewed
    review["passed_count"] = passed
    review["updated_at_utc"] = utc_now()
    manifest.update({
        "generated_count": generated,
        "structurally_passed_count": structurally_passed,
        "human_review_passed_count": passed,
        "validation_errors": errors,
        "provider_failure_count": len(provider_failures),
        "provider_failures": provider_failures,
        "provider_status": (
            "reviewed"
            if passed == len(records)
            else "pending_human_review"
            if structurally_passed == len(records)
            else "partially_generated"
            if generated
            else "provider_failed"
            if provider_failures
            else "request_ready"
        ),
    })
    runtime_ready = (
        len(records) > 0
        and passed == len(records)
        and len(runtime_assets) == manifest["scenario_count"]
        and args.asset_base_url is not None
    )
    finalized = {
        "format": "socialflux_online_multimodal_event_assets_v1",
        "created_at_utc": utc_now(),
        "profile": manifest["profile"],
        "asset_version": manifest["asset_version"],
        "runtime_ready": runtime_ready,
        "scenario_count": len(runtime_assets),
        "asset_count": sum(len(value) for value in runtime_assets.values()),
        "required_asset_count": len(records),
        "event_assets": runtime_assets,
    }
    atomic(manifest_path, manifest)
    atomic(review_path, review)
    atomic(queue_root / "event_assets.reviewed.json", finalized)
    print(json.dumps({
        "request_count": len(records),
        "generated_count": generated,
        "structurally_passed_count": structurally_passed,
        "human_review_passed_count": passed,
        "runtime_asset_count": finalized["asset_count"],
        "runtime_ready": runtime_ready,
        "validation_error_count": len(errors),
        "provider_failure_count": len(provider_failures),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
