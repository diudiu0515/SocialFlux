#!/usr/bin/env python3
"""Complete a frozen online-video inventory with bounded, resumable jobs."""

import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from copy import deepcopy
from datetime import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import sys
import time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.t4_asset_coverage import audit_asset_coverage
from scripts.run_multimodal_video_queue import ensure_state, state_path, file_sha256
from scripts.run_autodl_seedance_video import run as generate, provider_reference_url
from scripts.finalize_online_multimodal_assets import probe
from evaluation.t4_batch import save


def now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


def prepare(config, out):
    base = Path(config["batch_root"])
    path = Path(config["manifest"])
    document = json.loads(path.read_text())
    freeze = out / "preregistration.json"
    if freeze.exists():
        saved = json.loads(freeze.read_text())
        if saved["config"] != config:
            raise ValueError("generation configuration changed; choose a new run")
        return document
    save(out / "original_manifest.json", document)
    for record in document["requests"]:
        if record["scenario_id"] not in config["replacement_scenarios"]:
            continue
        old_path = base / record["request_file"]
        request = json.loads(old_path.read_text())
        # This is a declared renderer comparison after two prior failures;
        # the fictional identity, cue semantics, and prompt are unchanged.
        if record["dependency_phase"] == 0:
            if (base / record["video_file"]).exists():
                raise ValueError("refusing to replace an existing successful anchor")
            record.setdefault("replacement_history", []).append({
                "request_file": record["request_file"], "video_file": record["video_file"],
                "status": record["status"], "provider_task_id": record.get("provider_task_id"),
                "provider_error": record.get("provider_error"),
                "reason": "User-requested complete batch; single renderer comparison with identical prompt."})
            new_path = old_path.with_name(record["scenario_id"].lower() + "--activated_tension-renderer-fast.json")
            video = base / Path(record["video_file"]).parent / (new_path.stem + ".mp4")
            record.update(request_file=str(new_path.relative_to(base)), video_file=str(video.relative_to(base)), status="request_ready")
        else:
            new_path = old_path.with_name(old_path.stem + "-reference-repair.json")
            anchor = base / Path(record["video_file"]).parent / (record["scenario_id"].lower() + "--activated_tension-renderer-fast.mp4")
            request["reference_video_file"] = str(anchor.relative_to(base))
            record["request_file"] = str(new_path.relative_to(base))
        request["completion_provenance"] = {"source_request": str(old_path), "prepared_at": now(),
                                            "prompt_unchanged": True, "renderer_model": config["replacement_model"]}
        save(new_path, request)
        record["generation_model"] = config["replacement_model"]
    save(path, document)
    requests = {r["request_file"]: file_sha256(base / r["request_file"]) for r in document["requests"]}
    save(freeze, {"config": config, "prepared_at": now(), "request_sha256": requests,
                  "planned_missing": sum(not (base / r["video_file"]).is_file() for r in document["requests"]),
                  "human_review_status": "pending; exploratory evaluation only until separately attested"})
    return document


def check_video(path):
    metadata = probe(path)
    if not 3.5 <= metadata["duration_seconds_actual"] <= 5.5 or metadata["height"] < 720 or metadata["fps"] < 24 or metadata["audio_stream_count"] != 1:
        raise ValueError("generated video fails duration/resolution/fps/audio contract")
    return metadata


def publish_complete_scenarios(document, base, destination, identity_manifest=None, asset_directory=None):
    """Publish whole identity-consistent scene bundles, retaining older bundles until complete."""
    destination = Path(destination)
    current = json.loads(destination.read_text())
    groups = {}
    for record in document["requests"]:
        groups.setdefault(record["scenario_id"], []).append(record)
    ready = {sid for sid, records in groups.items()
             if all((base / r["video_file"]).is_file() and r.get("status") == "generated_structural_pass"
                    and r.get("video_sha256") == file_sha256(base / r["video_file"]) for r in records)}
    replacements = {r["request_id"]: deepcopy(r) for sid in ready for r in groups[sid]}
    if asset_directory:
        asset_root = Path(asset_directory).resolve()
        if not asset_root.is_relative_to(base.resolve()):
            raise ValueError("publication assets must stay within the video batch")
        asset_root.mkdir(parents=True, exist_ok=True)
        for record in replacements.values():
            source = (base / record["video_file"]).resolve()
            if source.parent == asset_root:
                continue
            target = asset_root / (record["scenario_id"].lower() + "--" + record["event_family"] + "--" + record["video_sha256"][:12] + ".mp4")
            if not target.exists():
                temporary = target.with_suffix(".mp4.tmp")
                shutil.copyfile(source, temporary)
                temporary.replace(target)
            if file_sha256(target) != record["video_sha256"]:
                raise ValueError("publication copy checksum mismatch")
            record["generation_video_file"] = record["video_file"]
            record["video_file"] = str(target.relative_to(base.resolve()))
    merged = [deepcopy(replacements.get(r["request_id"], r)) for r in current["requests"]]
    if merged != current["requests"]:
        current["requests"] = merged
        current["generated_count"] = sum((base / r["video_file"]).is_file() for r in merged)
        current["structurally_passed_count"] = sum(r.get("status") == "generated_structural_pass" for r in merged)
        if identity_manifest:
            identity_path = Path(identity_manifest)
            identities = json.loads(identity_path.read_text())
            for sid in ready:
                identity = json.loads((base / groups[sid][0]["request_file"]).read_text())["identity"]
                previous = identities["identities"].get(sid)
                if previous != identity:
                    identities.setdefault("revision_history", []).append({"scenario_id": sid, "previous": previous,
                        "replacement": identity, "published_at": now(), "reason": "User-authorized original appearance replacement"})
                    identities["identities"][sid] = identity
            save(identity_path, identities)
        save(destination, current)
    return sorted(ready)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    with (out / ".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        document = prepare(config, out)
        if args.prepare_only:
            print("Prepared video inventory", flush=True)
            return
        base, manifest = Path(config["batch_root"]), Path(config["manifest"])
        frozen = json.loads((out / "preregistration.json").read_text())
        for file, expected in frozen["request_sha256"].items():
            if file_sha256(base / file) != expected:
                raise ValueError("frozen generation request changed: " + file)
        result_path = out / "results.json"
        results = json.loads(result_path.read_text()) if result_path.exists() else {}
        # A process can stop after download and before the coordinator merges its
        # result. Recover those completed bytes without submitting a second task.
        for record in document["requests"]:
            video = base / record["video_file"]
            provider_state = state_path(base, record)
            if video.is_file() and record.get("status") != "generated_structural_pass" and provider_state.is_file():
                state = json.loads(provider_state.read_text())
                checksum = file_sha256(video)
                if state.get("status") == "downloaded" and state.get("video_sha256") == checksum:
                    metadata = check_video(video)
                    record.update(status="generated_structural_pass", video_sha256=checksum,
                                  structural_metadata=metadata, video_bytes=video.stat().st_size)
                    results[record["request_id"]] = {"status": "generated_structural_pass", "sha256": checksum,
                        "metadata": metadata, "recovered_after_download": True, "finished_at": now()}
        save(manifest, document)
        save(result_path, results)
        attempted = {rid for rid, result in results.items() if result.get("status") != "running"}
        started = time.monotonic()

        def execute(record, reference_url):
            path, state = ensure_state(base, record, model=record.get("generation_model", config["model"]), resolution="720p")
            if state.get("status") in {"failed", "expired", "cancelled"}:
                return {"status": "provider_failed", "error": "terminal task retained without resubmission"}
            if reference_url:
                state["request"].update(local_reference_transport="provided_url", local_reference_url=reference_url)
            state["attempt_started_at"] = now()
            save(path, state)
            try:
                generate(SimpleNamespace(state=path, output=base / record["video_file"],
                        key_file=Path(config["key_file"]), submit_new=not bool(state.get("task_id")),
                        poll_seconds=15, max_wait_seconds=1800))
                metadata = check_video(base / record["video_file"])
                return {"status": "generated_structural_pass", "metadata": metadata,
                        "sha256": file_sha256(base / record["video_file"]), "finished_at": now()}
            except Exception as exc:
                return {"status": "generation_failed", "error": str(exc), "finished_at": now()}

        with ThreadPoolExecutor(max_workers=config["workers"]) as pool:
            pending = {}
            while True:
                references = json.loads(Path(config["reference_urls"]).read_text()) if Path(config["reference_urls"]).exists() else {}
                blocked = []
                pilots = set(config.get("pilot_scenarios", []))
                pilot_complete = not pilots or any(
                    all((base / r["video_file"]).is_file() and r.get("status") == "generated_structural_pass"
                        for r in document["requests"] if r["scenario_id"] == sid) for sid in pilots)
                for record in document["requests"]:
                    if not pilot_complete and record["scenario_id"] not in pilots:
                        continue
                    rid = record["request_id"]
                    if (base / record["video_file"]).is_file() or rid in attempted:
                        continue
                    if len(pending) >= config["workers"]:
                        break
                    request = json.loads((base / record["request_file"]).read_text())
                    reference = request.get("reference_video_file")
                    url = None
                    if reference:
                        reference_path = base / reference
                        if not reference_path.is_file():
                            blocked.append({"request_id": rid, "reason": "anchor_not_generated"})
                            continue
                        entry = references.get(reference)
                        if entry and entry.get("sha256") == file_sha256(reference_path):
                            url = entry["url"]
                        elif config.get("reference_policy") == "fresh_provider" or record["scenario_id"] in config["replacement_scenarios"]:
                            # Newly generated anchors have fresh provider URLs.
                            url = provider_reference_url(reference_path)
                        else:
                            blocked.append({"request_id": rid, "reason": "awaiting_accessible_reference_url"})
                            continue
                    if len(attempted) >= config["max_generation_attempts"]:
                        blocked.append({"request_id": rid, "reason": "generation_budget_exhausted"})
                        continue
                    attempted.add(rid)
                    results[rid] = {"status": "running", "started_at": now()}
                    save(result_path, results)
                    pending[pool.submit(execute, deepcopy(record), url)] = record
                done, _ = wait(pending, timeout=20, return_when=FIRST_COMPLETED) if pending else (set(), set())
                for future in done:
                    record = pending.pop(future)
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = {"status": "generation_failed", "error": str(exc), "finished_at": now()}
                    results[record["request_id"]] = result
                    record["status"] = result["status"]
                    if result["status"] == "generated_structural_pass":
                        record.update(video_sha256=result["sha256"], structural_metadata=result["metadata"],
                                      video_bytes=(base / record["video_file"]).stat().st_size)
                    save(result_path, results)
                    document["generated_count"] = sum((base / r["video_file"]).is_file() for r in document["requests"])
                    document["structurally_passed_count"] = sum(r.get("status") == "generated_structural_pass" for r in document["requests"])
                    save(manifest, document)
                published = publish_complete_scenarios(document, base, config["publication_manifest"], config.get("publication_identity_manifest"), config.get("publication_asset_root")) if config.get("publication_manifest") else []
                pilot_complete = not pilots or any(
                    all((base / r["video_file"]).is_file() and r.get("status") == "generated_structural_pass"
                        for r in document["requests"] if r["scenario_id"] == sid) for sid in pilots)
                report = audit_asset_coverage(document, base)
                save(out / "coverage.json", report)
                state = "generating" if pending else "waiting_for_reference_urls" if blocked else "generation_incomplete"
                if report["generation_complete"]:
                    state = "videos_complete"
                save(out / "status.json", {"status": state, "updated_at": now(),
                     "generated": report["generated_assets"], "required": report["required_assets"],
                     "fully_covered_scenarios": report["scenarios_with_all_required_videos"],
                     "active_jobs": len(pending), "attempted": len(attempted), "blocked": blocked,
                     "human_review_status": "pending", "experiment_started": False,
                     "pilot_complete": pilot_complete, "published_complete_scenarios": published})
                if report["generation_complete"]:
                    command = config.get("after_complete_command")
                    if command:
                        save(out / "experiment_handoff.json", {"command": command, "started_at": now()})
                        save(out / "status.json", {"status": "experiment_running", "updated_at": now(),
                             "generated": report["generated_assets"], "required": report["required_assets"],
                             "fully_covered_scenarios": report["scenarios_with_all_required_videos"], "experiment_started": True})
                        exit_code = subprocess.call(command, cwd=ROOT)
                        save(out / "experiment_handoff.json", {"command": command, "exit_code": exit_code, "finished_at": now()})
                        save(out / "status.json", {"status": "experiment_process_finished", "updated_at": now(),
                             "generated": report["generated_assets"], "required": report["required_assets"],
                             "fully_covered_scenarios": report["scenarios_with_all_required_videos"],
                             "experiment_started": True, "experiment_exit_code": exit_code})
                    break
                if done:
                    # Finished anchors can unblock dependents; always rescan before
                    # treating the pre-completion blocked list as terminal.
                    continue
                if not pending and config.get("reference_policy") == "fresh_provider":
                    # No external URLs are awaited in this mode. Preserve failed anchors
                    # and stop rather than poll unsatisfiable dependencies for 24 hours.
                    if not pilot_complete or blocked:
                        save(out / "status.json", {"status": "generation_blocked_by_recorded_failures", "updated_at": now(),
                             "generated": report["generated_assets"], "required": report["required_assets"],
                             "fully_covered_scenarios": report["scenarios_with_all_required_videos"],
                             "active_jobs": 0, "attempted": len(attempted), "blocked": blocked,
                             "experiment_started": False, "pilot_complete": pilot_complete,
                             "published_complete_scenarios": published})
                        break
                if not pending and (not blocked or time.monotonic() - started >= config["maximum_wait_hours"] * 3600):
                    break
                if not pending:
                    time.sleep(20)


if __name__ == "__main__":
    main()
