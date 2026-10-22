#!/usr/bin/env python3
"""Register generated video API outputs and refresh Gate 2 review evidence."""

from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.artifacts import atomic_json as atomic


TERMINAL_PROVIDER_FAILURES = {"failed", "expired", "cancelled"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


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
        (
            "format=duration:stream=codec_type,codec_name,width,height,"
            "r_frame_rate,sample_rate,channels"
        ),
        "-of", "json", str(path),
    ], text=True)
    payload = json.loads(raw)
    video = next(
        (
            item for item in payload.get("streams", [])
            if item.get("codec_type") == "video"
        ),
        None,
    )
    if video is None:
        raise ValueError("generated asset has no video stream")
    audio = [
        item for item in payload.get("streams", [])
        if item.get("codec_type") == "audio"
    ]
    rate = video.get("r_frame_rate", "0/1")
    return {
        "duration_seconds_actual": round(
            float(payload.get("format", {}).get("duration", 0)), 3
        ),
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": round(float(Fraction(rate)), 3) if rate != "0/0" else 0,
        "video_codec": video.get("codec_name"),
        "audio_stream_count": len(audio),
        "audio_codecs": [item.get("codec_name") for item in audio],
        "audio_sample_rates": [item.get("sample_rate") for item in audio],
        "audio_channels": [item.get("channels") for item in audio],
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        help="defaults to <batch-root>/multimodal/manifest.json",
    )
    parser.add_argument(
        "--gate2-evidence",
        type=Path,
        help="defaults to the manifest-declared evidence file or legacy Gate 2 path",
    )
    parser.add_argument("--minimum-review-videos", type=int, default=40)
    parser.add_argument("--minimum-height", type=int)
    parser.add_argument("--skip-probe", action="store_true")
    args = parser.parse_args(argv)
    manifest_path = args.manifest or (
        args.batch_root / "multimodal" / "manifest.json"
    )
    manifest = load(manifest_path)
    records = manifest.get("requests") or []
    resolution = str((manifest.get("provider") or {}).get("resolution", ""))
    configured_height = (
        int(resolution[:-1])
        if resolution.endswith("p") and resolution[:-1].isdigit()
        else 0
    )
    minimum_height = (
        args.minimum_height
        if args.minimum_height is not None else configured_height
    )
    provider_states_root = manifest_path.parent / "provider_states"
    by_id = {}
    errors = []
    provider_failures = []
    generated = 0
    for item in records:
        path = args.batch_root / item["video_file"]
        if not path.is_file():
            request_file = item.get("request_file")
            state_stem = (
                Path(request_file).stem if request_file else Path(item["video_file"]).stem
            )
            state_path = provider_states_root / f"{state_stem}.json"
            state = load(state_path) if state_path.is_file() else {}
            if state.get("status") in TERMINAL_PROVIDER_FAILURES:
                provider_error = (
                    (state.get("latest_query_response") or {}).get("error")
                    or state.get("last_queue_error")
                    or {}
                )
                item.update({
                    "status": "provider_failed",
                    "provider_terminal_status": state.get("status"),
                    "provider_task_id": state.get("task_id"),
                    "provider_terminal_status": state.get("status"),
                    "provider_error": provider_error,
                })
                provider_failures.append({
                    "request_id": item["request_id"],
                    "provider_task_id": state.get("task_id"),
                    "error": provider_error,
                })
            else:
                item["status"] = "request_ready"
            by_id[item["request_id"]] = item
            continue
        try:
            metadata = {} if args.skip_probe else probe(path)
            if not args.skip_probe:
                duration = metadata.get("duration_seconds_actual")
                if duration is not None and not 2.5 <= duration <= 15.5:
                    raise ValueError(
                        f"video duration outside allowed range: {duration}"
                    )
                if metadata.get("audio_stream_count", 0) < 1:
                    raise ValueError("generated asset has no audio stream")
                if int(metadata.get("height") or 0) < minimum_height:
                    raise ValueError(
                        "video height below delivery minimum: "
                        f"{metadata.get('height')}"
                    )
            item.update({
                "status": "generated_structural_pass",
                "video_sha256": sha256(path),
                "video_bytes": path.stat().st_size,
                "structural_metadata": metadata,
            })
            generated += 1
        except Exception as exc:
            item["status"] = "generated_structural_fail"
            item["validation_error"] = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            errors.append({
                "request_id": item["request_id"],
                **item["validation_error"],
            })
        by_id[item["request_id"]] = item

    manifest["generated_count"] = generated
    manifest["validation_errors"] = errors
    manifest["provider_failure_count"] = len(provider_failures)
    manifest["provider_failures"] = provider_failures
    manifest["provider_status"] = (
        "generated"
        if generated == len(records) and not errors and not provider_failures
        else "partially_generated"
        if generated
        else "provider_failed"
        if provider_failures
        else "awaiting_video_api_configuration"
    )
    atomic(manifest_path, manifest)

    gate2_path = args.gate2_evidence or Path(
        manifest.get("gate2_evidence_file")
        or args.batch_root / "gate2" / "video_state_consistency.json"
    )
    gate2 = load(gate2_path)
    review_items = gate2.get("review_items") or []
    review_generated = 0
    review_errors = 0
    review_provider_failures = 0
    for item in review_items:
        generated_item = by_id.get(item["request_id"], {})
        item["video_status"] = generated_item.get("status", "request_ready")
        item["video_sha256"] = generated_item.get("video_sha256")
        item["structural_metadata"] = generated_item.get("structural_metadata", {})
        if item["video_status"] == "generated_structural_pass":
            review_generated += 1
        elif item["video_status"] == "generated_structural_fail":
            review_errors += 1
        elif item["video_status"] == "provider_failed":
            review_provider_failures += 1
    record = gate2["record"]
    record["generated_video_count"] = review_generated
    record["structural_failure_count"] = review_errors
    record["provider_failure_count"] = review_provider_failures
    record["machine_screen_passed"] = (
        review_generated >= args.minimum_review_videos
        and review_errors == 0
        and review_provider_failures == 0
        and record.get("request_safety_passed") is True
    )
    record["review_status"] = (
        "pending_human"
        if record["machine_screen_passed"]
        else "pending_video_api_and_review"
    )
    atomic(gate2_path, gate2)
    print(json.dumps({
        "queue_request_count": len(records),
        "queue_generated_count": generated,
        "gate2_review_generated_count": review_generated,
        "gate2_machine_screen_passed": record["machine_screen_passed"],
        "validation_error_count": len(errors),
        "provider_failure_count": len(provider_failures),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
