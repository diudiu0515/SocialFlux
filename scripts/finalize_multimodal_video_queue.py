#!/usr/bin/env python3
"""Register generated video API outputs and refresh Gate 2 review evidence."""

from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess


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
        "-show_entries", "format=duration:stream=codec_type,width,height,r_frame_rate",
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
    rate = video.get("r_frame_rate", "0/1")
    return {
        "duration_seconds_actual": round(
            float(payload.get("format", {}).get("duration", 0)), 3
        ),
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": round(float(Fraction(rate)), 3) if rate != "0/0" else 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        help="defaults to <batch-root>/multimodal/manifest.json",
    )
    parser.add_argument("--minimum-review-videos", type=int, default=40)
    parser.add_argument("--skip-probe", action="store_true")
    args = parser.parse_args(argv)
    manifest_path = args.manifest or (
        args.batch_root / "multimodal" / "manifest.json"
    )
    manifest = load(manifest_path)
    records = manifest.get("requests") or []
    by_id = {}
    errors = []
    generated = 0
    for item in records:
        path = args.batch_root / item["video_file"]
        if not path.is_file():
            item["status"] = "request_ready"
            by_id[item["request_id"]] = item
            continue
        try:
            metadata = {} if args.skip_probe else probe(path)
            duration = metadata.get("duration_seconds_actual")
            if duration is not None and not 2.5 <= duration <= 15.5:
                raise ValueError(f"video duration outside allowed range: {duration}")
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
    manifest["provider_status"] = (
        "generated"
        if generated == len(records) and not errors
        else "partially_generated"
        if generated
        else "awaiting_video_api_configuration"
    )
    atomic(manifest_path, manifest)

    gate2_path = args.batch_root / "gate2" / "video_state_consistency.json"
    gate2 = load(gate2_path)
    review_items = gate2.get("review_items") or []
    review_generated = 0
    review_errors = 0
    for item in review_items:
        generated_item = by_id.get(item["request_id"], {})
        item["video_status"] = generated_item.get("status", "request_ready")
        item["video_sha256"] = generated_item.get("video_sha256")
        item["structural_metadata"] = generated_item.get("structural_metadata", {})
        if item["video_status"] == "generated_structural_pass":
            review_generated += 1
        elif item["video_status"] == "generated_structural_fail":
            review_errors += 1
    record = gate2["record"]
    record["generated_video_count"] = review_generated
    record["structural_failure_count"] = review_errors
    record["machine_screen_passed"] = (
        review_generated >= args.minimum_review_videos
        and review_errors == 0
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
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
