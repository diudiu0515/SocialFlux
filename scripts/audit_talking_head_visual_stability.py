#!/usr/bin/env python3
"""Screen talking-head assets for identity and non-face visual stability."""

import json
from pathlib import Path
import sys

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "media" / "talking_head" / "manifest.json"
REPORT = ROOT / "media" / "talking_head" / "visual_stability_screen.json"
CONTACT_SHEET = ROOT / "build" / "talking_head" / "musetalk_contact_sheet.jpg"


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def largest_face(detector, image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
    if not len(faces):
        return None
    return max(faces, key=lambda item: item[2] * item[3])


def mean_absolute_difference(left, right):
    return float(np.abs(left.astype(np.float32) - right.astype(np.float32)).mean())


def analyze(record, detector):
    reference = cv2.imread(str(ROOT / record["reference_path"]))
    capture = cv2.VideoCapture(str(ROOT / record["video_path"]))
    frame_count = round(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    face = largest_face(detector, reference) if reference is not None else None
    if reference is None or face is None or frame_count < 2:
        capture.release()
        return {
            "asset_id": record["asset_id"],
            "status": "review",
            "reason": "reference_or_face_missing",
        }, None

    x, y, width, height = [int(value) for value in face]
    height_px, width_px = reference.shape[:2]
    outer_mask = np.ones((height_px, width_px), dtype=bool)
    margin = round(max(width, height) * 0.08)
    outer_mask[
        max(0, y - margin):min(height_px, y + height + margin),
        max(0, x - margin):min(width_px, x + width + margin),
    ] = False
    upper_slice = (
        slice(y, min(height_px, y + round(height * 0.55))),
        slice(x, min(width_px, x + width)),
    )
    sampled = sorted({
        0,
        round((frame_count - 1) * 0.25),
        round((frame_count - 1) * 0.5),
        round((frame_count - 1) * 0.75),
        frame_count - 1,
    })
    outer_scores = []
    upper_scores = []
    detected_frames = 0
    middle_frame = None
    for frame_index in sampled:
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
        if not ok or frame.shape != reference.shape:
            continue
        if largest_face(detector, frame) is not None:
            detected_frames += 1
        outer_scores.append(mean_absolute_difference(frame[outer_mask], reference[outer_mask]))
        upper_scores.append(mean_absolute_difference(frame[upper_slice], reference[upper_slice]))
        if frame_index == sampled[len(sampled) // 2]:
            middle_frame = frame
    capture.release()
    status = (
        "pass"
        if len(outer_scores) == len(sampled)
        and detected_frames == len(sampled)
        and max(outer_scores) <= 5.0
        and max(upper_scores) <= 8.0
        else "review"
    )
    return {
        "asset_id": record["asset_id"],
        "status": status,
        "sampled_frame_count": len(sampled),
        "face_detected_frame_count": detected_frames,
        "max_non_face_pixel_mad": round(max(outer_scores), 4) if outer_scores else None,
        "max_upper_face_pixel_mad": round(max(upper_scores), 4) if upper_scores else None,
    }, middle_frame


def make_contact_sheet(records, frames):
    cells = []
    for record, frame in zip(records, frames):
        if frame is None:
            cell = np.zeros((180, 180, 3), dtype=np.uint8)
        else:
            cell = cv2.resize(frame, (180, 180), interpolation=cv2.INTER_AREA)
        cv2.rectangle(cell, (0, 154), (180, 180), (0, 0, 0), -1)
        cv2.putText(
            cell,
            record["asset_id"].replace("IA_PIPE_", "")[:24],
            (4, 171),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.34,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        cells.append(cell)
    rows = []
    for start in range(0, len(cells), 10):
        row = cells[start:start + 10]
        row.extend(
            np.zeros_like(cells[0]) for _ in range(10 - len(row))
        )
        rows.append(np.hstack(row))
    cv2.imwrite(str(CONTACT_SHEET), np.vstack(rows))


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    detector = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    analyzed = [analyze(record, detector) for record in manifest["assets"]]
    results = [item[0] for item in analyzed]
    frames = [item[1] for item in analyzed]
    by_id = {item["asset_id"]: item for item in results}
    for record in manifest["assets"]:
        result = by_id[record["asset_id"]]
        record.setdefault("quality_checks", {})[
            "gate_3_identity_and_visual_stability"
        ] = result["status"]
        record["visual_stability_metrics"] = {
            key: value for key, value in result.items()
            if key not in ("asset_id", "status")
        }
    summary = {
        "format": "socialflux_talking_head_visual_stability_screen_v1",
        "asset_count": len(results),
        "pass_count": sum(item["status"] == "pass" for item in results),
        "review_count": sum(item["status"] == "review" for item in results),
        "thresholds": {
            "max_non_face_pixel_mad": 5.0,
            "max_upper_face_pixel_mad": 8.0,
            "face_required_in_all_sampled_frames": True,
        },
        "results": results,
    }
    dump(REPORT, summary)
    dump(MANIFEST, manifest)
    make_contact_sheet(manifest["assets"], frames)
    print(json.dumps({
        "assets": summary["asset_count"],
        "pass": summary["pass_count"],
        "review": summary["review_count"],
        "contact_sheet": str(CONTACT_SHEET.relative_to(ROOT)),
    }))
    return 0 if summary["review_count"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
