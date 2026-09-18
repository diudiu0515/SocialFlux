#!/usr/bin/env python3
"""Heuristic AV-sync screen for gross talking-head generation failures.

This is not a substitute for human lip-sync/realism review. It detects a face,
tracks lower-face frame differences, and compares that motion with speech energy
across short lags to flag frozen mouths or conspicuous temporal offsets.
"""

import json
from pathlib import Path
import sys
import wave

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "media" / "talking_head" / "manifest.json"
REPORT = ROOT / "media" / "talking_head" / "av_sync_screen.json"
def dump(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def audio_energy(path, fps):
    with wave.open(str(path), "rb") as stream:
        rate = stream.getframerate()
        width = stream.getsampwidth()
        channels = stream.getnchannels()
        raw = stream.readframes(stream.getnframes())
    if width != 2:
        raise ValueError(f"expected 16-bit PCM: {path}")
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    samples = samples.reshape(-1, channels).mean(axis=1)
    window = rate / fps
    values = []
    for index in range(round(len(samples) / window)):
        start = round(index * window)
        end = min(len(samples), round((index + 1) * window))
        frame = samples[start:end]
        values.append(float(np.sqrt(np.mean(frame * frame))) if len(frame) else 0.0)
    return np.asarray(values, dtype=np.float32)


def face_box_and_mouth_motion(path):
    detector = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    capture = cv2.VideoCapture(str(path))
    fps = float(capture.get(cv2.CAP_PROP_FPS)) or 25.0
    box = None
    for _ in range(round(fps)):
        ok, frame = capture.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
        if len(faces):
            box = max(faces, key=lambda item: item[2] * item[3])
            break
    capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
    if box is None:
        capture.release()
        return None, np.asarray([], dtype=np.float32), fps
    x, y, width, height = [int(value) for value in box]
    x1, x2 = x + round(width * 0.18), x + round(width * 0.82)
    y1, y2 = y + round(height * 0.55), y + round(height * 0.92)
    previous = None
    motion = []
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        mouth = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        mouth = cv2.resize(mouth, (96, 48))
        if previous is not None:
            motion.append(float(cv2.absdiff(mouth, previous).mean()))
        previous = mouth
    capture.release()
    return [x, y, width, height], np.asarray(motion, dtype=np.float32), fps


def correlation_at_lag(motion, energy, lag, fps):
    if lag < 0:
        left, right = motion[-lag:], energy[:lag]
    elif lag > 0:
        left, right = motion[:-lag], energy[lag:]
    else:
        left, right = motion, energy
    if len(left) < fps or np.std(left) == 0 or np.std(right) == 0:
        return -1.0
    return float(np.corrcoef(left, right)[0, 1])


def analyze(record):
    box, motion, fps = face_box_and_mouth_motion(ROOT / record["video_path"])
    energy = audio_energy(ROOT / record["audio_path"], fps)[1:]
    length = min(len(motion), len(energy))
    motion, energy = motion[:length], energy[:length]
    lag_limit = round(fps * 0.5)
    scores = {
        lag: correlation_at_lag(motion, energy, lag, fps)
        for lag in range(-lag_limit, lag_limit + 1)
    }
    best_lag = max(scores, key=scores.get)
    best_correlation = scores[best_lag]
    accepted_lag_limit = round(fps * 0.4)
    accepted_scores = {
        lag: score for lag, score in scores.items()
        if abs(lag) <= accepted_lag_limit
    }
    best_accepted_lag = max(accepted_scores, key=accepted_scores.get)
    best_accepted_correlation = accepted_scores[best_accepted_lag]
    accepted_to_global_ratio = (
        best_accepted_correlation / best_correlation
        if best_correlation > 0 else 0.0
    )
    p90 = float(np.percentile(motion, 90)) if len(motion) else 0.0
    gross_pass = (
        box is not None
        and len(motion) >= fps * 3
        and p90 >= 0.25
        and best_correlation >= 0.02
        and best_accepted_correlation >= 0.02
        and accepted_to_global_ratio >= 0.8
    )
    return {
        "asset_id": record["asset_id"],
        "status": "pass" if gross_pass else "review",
        "face_detected": box is not None,
        "face_box": box,
        "fps": round(fps, 3),
        "mouth_motion_p90": round(p90, 4),
        "best_audio_motion_correlation": round(best_correlation, 4),
        "best_lag_frames": int(best_lag),
        "best_lag_seconds": round(best_lag / fps, 3),
        "accepted_lag_limit_seconds": 0.4,
        "best_accepted_lag_frames": int(best_accepted_lag),
        "best_accepted_lag_seconds": round(best_accepted_lag / fps, 3),
        "best_accepted_correlation": round(best_accepted_correlation, 4),
        "accepted_to_global_correlation_ratio": round(accepted_to_global_ratio, 4),
    }


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    results = [analyze(record) for record in manifest["assets"]]
    by_id = {item["asset_id"]: item for item in results}
    for record in manifest["assets"]:
        result = by_id[record["asset_id"]]
        checks = record.setdefault("quality_checks", {})
        checks["av_motion_sync_screen"] = result["status"]
        checks["gate_2_audio_conditioned_lipsync"] = (
            "pass" if result["status"] == "pass" else "review"
        )
        record["av_motion_sync_metrics"] = {
            key: value for key, value in result.items()
            if key not in ("asset_id", "status", "face_box")
        }
    summary = {
        "format": "socialflux_talking_head_av_sync_screen_v3",
        "disclaimer": "Heuristic gross-failure screen; human lip-sync and realism review remains required.",
        "asset_count": len(results),
        "pass_count": sum(item["status"] == "pass" for item in results),
        "review_count": sum(item["status"] == "review" for item in results),
        "results": results,
    }
    dump(REPORT, summary)
    dump(MANIFEST, manifest)
    print(json.dumps({
        "assets": summary["asset_count"],
        "pass": summary["pass_count"],
        "review": summary["review_count"],
    }))
    return 0 if summary["review_count"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
