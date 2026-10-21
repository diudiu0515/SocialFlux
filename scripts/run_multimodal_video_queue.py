#!/usr/bin/env python3
"""Prepare, submit, resume, and download a bounded multimodal video queue."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_autodl_seedance_video import (  # noqa: E402
    ALLOWED_MODELS,
    run as run_seedance,
    validate_payload,
)
from shared.artifacts import atomic_json as atomic


DEFAULT_MODEL = "doubao-seedance-2-0-260128"
DEFAULT_KEY_FILE = Path("/root/.config/socialflux/autodl_video_api_key")
TERMINAL_FAILURES = {"failed", "expired", "cancelled"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical_sha256(value):
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _local_reference_path(reference_root, value):
    if reference_root is None:
        raise ValueError("reference_root is required for local reference video")
    root = Path(reference_root).resolve()
    candidate = (root / str(value)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("reference video must stay inside batch_root") from exc
    if not candidate.is_file():
        raise ValueError(f"reference video is missing: {candidate}")
    return candidate


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def seedance_payload(
    request,
    *,
    model=DEFAULT_MODEL,
    resolution="480p",
    reference_root=None,
):
    """Convert one provider-neutral request into a validated Seedance payload."""
    prompt = str(request.get("prompt", "")).strip()
    duration = max(
        4,
        min(15, math.ceil(float(request.get("duration_seconds", 0)))),
    )
    generate_audio = request.get("generate_audio", True)
    if not isinstance(generate_audio, bool):
        raise ValueError("provider-neutral generate_audio must be boolean")
    payload = {
        "model": model,
        "content": [{"type": "text", "text": prompt}],
        "generate_audio": generate_audio,
        "ratio": request.get("ratio", "16:9"),
        "duration": duration,
        "resolution": resolution,
        "watermark": False,
    }
    reference = request.get("reference_video_file")
    if reference:
        payload["local_reference_video"] = str(
            _local_reference_path(reference_root, reference)
        )
    return validate_payload(payload)


def select_records(batch_root, manifest, selection):
    records = manifest.get("requests") or []
    by_id = {item["request_id"]: item for item in records}
    if len(by_id) != len(records):
        raise ValueError("multimodal manifest contains duplicate request IDs")
    if selection == "all":
        return records
    if selection in {"anchors", "dependents"}:
        phase = 0 if selection == "anchors" else 1
        selected = [
            item for item in records if item.get("dependency_phase") == phase
        ]
        if not selected:
            raise ValueError(f"multimodal {selection} selection is empty")
        return selected
    evidence_path = batch_root / "gate2" / "video_state_consistency.json"
    evidence = load(evidence_path)
    selected = []
    for item in evidence.get("review_items") or []:
        request_id = item["request_id"]
        if request_id not in by_id:
            raise ValueError(f"Gate 2 request is absent from manifest: {request_id}")
        selected.append(by_id[request_id])
    if not selected:
        raise ValueError("Gate 2 video review selection is empty")
    return selected


def state_path(batch_root, record):
    request_file = Path(record["request_file"])
    stem = request_file.stem
    queue_root = request_file.parent.parent
    return batch_root / queue_root / "provider_states" / f"{stem}.json"


def ensure_state(batch_root, record, *, model, resolution):
    request_path = batch_root / record["request_file"]
    request = load(request_path)
    fingerprint_source = {"provider_neutral_request": request}
    reference = request.get("reference_video_file")
    if reference:
        reference_path = _local_reference_path(batch_root, reference)
        fingerprint_source["reference_video_sha256"] = file_sha256(reference_path)
    fingerprint = canonical_sha256(fingerprint_source)
    path = state_path(batch_root, record)
    if path.exists():
        state = load(path)
        if state.get("provider_neutral_request_sha256") != fingerprint:
            raise ValueError(
                "provider request changed after state creation: "
                f"{record['request_id']}"
            )
        state_request = state.get("request") or {}
        if state_request.get("model") != model:
            raise ValueError(
                "provider model changed after state creation: "
                f"{record['request_id']}"
            )
        if state_request.get("resolution") != resolution:
            raise ValueError(
                "provider resolution changed after state creation: "
                f"{record['request_id']}"
            )
        return path, state
    state = {
        "format": "socialflux_seedance_queue_state_v1",
        "created_at_utc": utc_now(),
        "request_id": record["request_id"],
        "provider_neutral_request_file": record["request_file"],
        "provider_neutral_request_sha256": fingerprint,
        "request": seedance_payload(
            request,
            model=model,
            resolution=resolution,
            reference_root=batch_root,
        ),
        "reference_video_sha256": fingerprint_source.get(
            "reference_video_sha256"
        ),
        "status": "prepared",
    }
    atomic(path, state)
    return path, state


def is_complete(batch_root, record, state):
    output = batch_root / record["video_file"]
    return output.is_file() and state.get("status") == "downloaded"


def run_record(
    batch_root,
    record,
    *,
    key_file,
    model,
    resolution,
    submit_new,
    poll_seconds,
    max_wait_seconds,
):
    path, state = ensure_state(
        batch_root, record, model=model, resolution=resolution
    )
    if is_complete(batch_root, record, state):
        return {"request_id": record["request_id"], "status": "downloaded"}
    if state.get("status") in TERMINAL_FAILURES:
        return {
            "request_id": record["request_id"],
            "status": state["status"],
            "skipped": "terminal_failure_requires_explicit_new_state",
        }
    if not state.get("task_id") and not submit_new:
        return {"request_id": record["request_id"], "status": "prepared"}
    args = SimpleNamespace(
        state=path,
        output=batch_root / record["video_file"],
        key_file=key_file,
        submit_new=bool(submit_new and not state.get("task_id")),
        poll_seconds=poll_seconds,
        max_wait_seconds=max_wait_seconds,
    )
    try:
        run_seedance(args)
    except Exception as exc:
        latest = load(path)
        latest["last_queue_error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "recorded_at_utc": utc_now(),
        }
        atomic(path, latest)
        return {
            "request_id": record["request_id"],
            "status": "error",
            "error": latest["last_queue_error"],
        }
    return {"request_id": record["request_id"], "status": "downloaded"}


def filter_records_by_scenario(records, scenario_ids=None, scenario_limit=None):
    available = sorted({
        item.get("scenario_id") for item in records if item.get("scenario_id")
    })
    if scenario_ids:
        requested = set(scenario_ids)
        unknown = sorted(requested - set(available))
        if unknown:
            raise ValueError(f"unknown scenario IDs in queue selection: {unknown}")
        return [item for item in records if item.get("scenario_id") in requested]
    if scenario_limit is not None:
        selected = set(available[:scenario_limit])
        return [item for item in records if item.get("scenario_id") in selected]
    return records


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--selection",
        choices=("gate2", "all", "anchors", "dependents"),
        default="gate2",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--scenario-id", action="append", dest="scenario_ids")
    parser.add_argument("--scenario-limit", type=int)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--model", choices=sorted(ALLOWED_MODELS), default=DEFAULT_MODEL
    )
    parser.add_argument(
        "--resolution", choices=("480p", "720p", "1080p")
    )
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument("--submit-new", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--max-wait-seconds", type=int, default=1800)
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.scenario_limit is not None and args.scenario_limit < 1:
        parser.error("--scenario-limit must be positive")
    if args.scenario_ids and args.scenario_limit is not None:
        parser.error("--scenario-id and --scenario-limit are mutually exclusive")
    if not 1 <= args.workers <= 4:
        parser.error("--workers must be in 1..4")

    manifest_path = args.manifest or (
        args.batch_root / "multimodal" / "manifest.json"
    )
    manifest = load(manifest_path)
    resolution = (
        args.resolution
        or (manifest.get("provider") or {}).get("resolution")
        or "480p"
    )
    records = select_records(args.batch_root, manifest, args.selection)
    records = filter_records_by_scenario(
        records, args.scenario_ids, args.scenario_limit
    )
    if args.limit is not None:
        records = records[: args.limit]

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                run_record,
                args.batch_root,
                record,
                key_file=args.key_file,
                model=args.model,
                resolution=resolution,
                submit_new=args.submit_new,
                poll_seconds=args.poll_seconds,
                max_wait_seconds=args.max_wait_seconds,
            ): record["request_id"]
            for record in records
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)

    counts = {}
    for item in results:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    summary = {
        "selection": args.selection,
        "selected_count": len(records),
        "resolution": resolution,
        "submit_new": args.submit_new,
        "status_counts": dict(sorted(counts.items())),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if counts.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
