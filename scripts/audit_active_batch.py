#!/usr/bin/env python3
"""Offline audit and progress report for an active SocialFlux batch.

This command never constructs a provider and never performs a network request.
It validates materialized artifacts, records exact missing/invalid ordinals, and
writes a stable status document that supervisors and review UIs can consume.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas.validate import STATE_CONTRACT_VERSION, validate_scenario, validate_trajectory
from shared.artifacts import atomic_json as atomic


ROOT = Path(__file__).resolve().parents[1]
TASK_NAMES = ("T1", "T2", "T3", "T4")


def now():
    return datetime.now(timezone.utc).isoformat()


def load(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def scenario_id(prefix, ordinal):
    return f"{prefix}{ordinal:03d}"


def ordinal_from_id(value):
    match = re.search(r"(\d{3})$", str(value or ""))
    return int(match.group(1)) if match else None


def _artifact_error(path, exc):
    return {
        "path": str(path),
        "error_type": type(exc).__name__,
        "error": str(exc),
    }


def audit_scenarios(batch, expected, prefix):
    valid = []
    invalid = []
    source_counts = {}
    for ordinal in range(1, expected + 1):
        name = f"scenario_{ordinal:03d}"
        path = batch / "scenarios" / name / f"{name}.json"
        if not path.exists():
            continue
        try:
            value = load(path)
            validate_scenario(value)
            if value.get("state_contract_version") != STATE_CONTRACT_VERSION:
                raise ValueError(
                    f"active scenario must use {STATE_CONTRACT_VERSION}, "
                    f"got {value.get('state_contract_version')!r}"
                )
            expected_id = scenario_id(prefix, ordinal)
            if value.get("scenario_id") != expected_id:
                raise ValueError(
                    f"scenario_id {value.get('scenario_id')!r} != {expected_id!r}"
                )
            valid.append(ordinal)
            source = (
                (value.get("source") or {}).get("type")
                or value.get("source_type")
                or "unknown"
            )
            source_counts[source] = source_counts.get(source, 0) + 1
        except Exception as exc:
            invalid.append({"ordinal": ordinal, **_artifact_error(path, exc)})
    missing = sorted(set(range(1, expected + 1)) - set(valid) - {
        item["ordinal"] for item in invalid
    })
    ratio_expected = None
    ratio_complete = True
    if prefix == "CF150_" and expected == 150:
        ratio_expected = {
            "narrative-derived": 45,
            "synthetic-script": 105,
        }
        ratio_complete = all(
            source_counts.get(name, 0) == count
            for name, count in ratio_expected.items()
        )
    return {
        "expected": expected,
        "valid": len(valid),
        "missing_ordinals": missing,
        "invalid": invalid,
        "source_counts": source_counts,
        "source_ratio_expected": ratio_expected,
        "source_ratio_complete": ratio_complete,
        "complete": len(valid) == expected and not invalid and ratio_complete,
    }


def audit_rollouts(batch, expected, prefix):
    root = batch / "rollouts"
    progress_path = root / "progress.json"
    progress = load(progress_path, {}) or {}
    completed = progress.get("completed_slots") or {}
    seen = {}
    invalid = []
    duplicates = []
    for slot_id, record in completed.items():
        sid = record.get("scenario_id")
        ordinal = ordinal_from_id(sid)
        if ordinal is None or not 1 <= ordinal <= expected:
            invalid.append({
                "slot_id": slot_id,
                "error": f"invalid scenario_id: {sid!r}",
            })
            continue
        if sid != scenario_id(prefix, ordinal):
            invalid.append({
                "slot_id": slot_id,
                "ordinal": ordinal,
                "error": f"unexpected scenario_id: {sid!r}",
            })
            continue
        if ordinal in seen:
            duplicates.append({
                "ordinal": ordinal,
                "slot_ids": [seen[ordinal]["slot_id"], slot_id],
            })
            continue
        trajectory_file = record.get("trajectory_file")
        path = root / f"scenario_{ordinal:03d}" / str(trajectory_file or "")
        try:
            value = load(path)
            if value is None:
                raise FileNotFoundError(path)
            validate_trajectory(value)
            if value.get("scenario_id") != sid:
                raise ValueError("trajectory scenario_id does not match progress")
            seen[ordinal] = {
                "slot_id": slot_id,
                "trajectory_id": value.get("trajectory_id"),
                "turn_count": len(value.get("turns", [])),
                "path": str(path),
            }
        except Exception as exc:
            invalid.append({
                "slot_id": slot_id,
                "ordinal": ordinal,
                **_artifact_error(path, exc),
            })
    missing = sorted(set(range(1, expected + 1)) - set(seen))
    return {
        "expected": expected,
        "valid": len(seen),
        "progress_status": progress.get("status", "not_started"),
        "progress_updated_at_utc": progress.get("updated_at_utc"),
        "missing_ordinals": missing,
        "invalid": invalid,
        "duplicates": duplicates,
        "turn_count_distribution": sorted(
            item["turn_count"] for item in seen.values()
        ),
        "complete": len(seen) == expected and not invalid and not duplicates,
    }


def audit_multimodal_plan(batch, expected):
    manifest_path = batch / "multimodal" / "manifest.json"
    manifest = load(manifest_path, {}) or {}
    records = manifest.get("requests") or []
    invalid = []
    covered = set()
    for item in records:
        try:
            covered.add(item["scenario_id"])
            request_path = batch / item["request_file"]
            request = load(request_path)
            if request is None:
                raise FileNotFoundError(request_path)
            safety = request.get("safety_check") or {}
            if not safety or any(value is not False for value in safety.values()):
                raise ValueError("video request safety contract failed")
            if not str(request.get("prompt", "")).strip():
                raise ValueError("video request prompt is empty")
        except Exception as exc:
            invalid.append({
                "request_id": item.get("request_id"),
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
    complete = (
        manifest.get("network_requests_performed") == 0
        and manifest.get("trajectory_count") == expected
        and len(covered) == expected
        and len(records) == int(manifest.get("request_count", -1))
        and bool(records)
        and not invalid
    )
    return {
        "expected_trajectories": expected,
        "trajectory_count": manifest.get("trajectory_count", 0),
        "covered_scenarios": len(covered),
        "request_count": len(records),
        "network_requests_performed": manifest.get("network_requests_performed"),
        "provider_status": manifest.get("provider_status"),
        "invalid": invalid,
        "complete": complete,
    }


def audit_sources(batch, expected):
    valid = []
    invalid = []
    for ordinal in range(1, expected + 1):
        path = (
            batch / "source_packages" / "shard1"
            / f"scenario_{ordinal:03d}.json"
        )
        if not path.exists():
            continue
        try:
            value = load(path)
            required = (
                "scenario_id", "source_trajectory_id", "source_artifact",
                "ordinal",
            )
            missing_fields = [key for key in required if value.get(key) in (None, "")]
            if missing_fields:
                raise ValueError(f"missing fields: {missing_fields}")
            if int(value["ordinal"]) != ordinal:
                raise ValueError("ordinal mismatch")
            artifact = ROOT / value["source_artifact"]
            if not artifact.is_file():
                raise FileNotFoundError(artifact)
            valid.append(ordinal)
        except Exception as exc:
            invalid.append({"ordinal": ordinal, **_artifact_error(path, exc)})
    missing = sorted(set(range(1, expected + 1)) - set(valid) - {
        item["ordinal"] for item in invalid
    })
    return {
        "expected": expected,
        "valid": len(valid),
        "missing_ordinals": missing,
        "invalid": invalid,
        "complete": len(valid) == expected and not invalid,
    }


def audit_t2_specs(batch, expected):
    records = {}
    invalid = []
    for path in sorted((batch / "t2_specs" / "records").glob("scenario_*.json")):
        try:
            value = load(path)
            ordinal = int(value["ordinal"])
            if ordinal in records:
                raise ValueError(f"duplicate ordinal {ordinal}")
            records[ordinal] = value
        except Exception as exc:
            invalid.append(_artifact_error(path, exc))
    authored = sorted(
        ordinal for ordinal, value in records.items()
        if value.get("status") == "authored_pending_pair_construction_and_human_review"
        and isinstance(value.get("spec"), dict)
    )
    missing = sorted(set(range(1, expected + 1)) - set(records))
    incomplete = sorted(set(records) - set(authored))
    return {
        "expected": expected,
        "record_count": len(records),
        "authored": len(authored),
        "missing_ordinals": missing,
        "incomplete_ordinals": incomplete,
        "invalid": invalid,
        "complete": len(authored) == expected and not invalid,
    }


def audit_t2_pairs(batch, expected):
    summary = load(batch / "t2_runs" / "primary" / "summary.json", {}) or {}
    rows = summary.get("results") or []
    completed = sorted(
        int(item["ordinal"]) for item in rows
        if item.get("status") == "completed" and item.get("ordinal") is not None
    )
    incomplete = sorted(
        int(item["ordinal"]) for item in rows
        if item.get("status") != "completed" and item.get("ordinal") is not None
    )
    missing = sorted(set(range(1, expected + 1)) - set(completed) - set(incomplete))
    return {
        "expected": expected,
        "result_count": int(summary.get("result_count", 0) or 0),
        "completed": len(completed),
        "missing_ordinals": missing,
        "incomplete_ordinals": incomplete,
        "status_counts": summary.get("status_counts", {}),
        "complete": len(completed) == expected,
    }


def task_complete(task):
    return (
        isinstance(task, dict)
        and isinstance(task.get("instance"), dict)
        and task.get("llm_answer") is not None
        and bool(task.get("answer_status"))
    )


def package_complete(package):
    tasks = package.get("tasks") or {}
    return set(tasks) == set(TASK_NAMES) and all(
        task_complete(tasks[name]) for name in TASK_NAMES
    )


def audit_tasks(batch, expected):
    complete = []
    missing = []
    incomplete = []
    task_counts = {name: 0 for name in TASK_NAMES}
    for ordinal in range(1, expected + 1):
        path = batch / "tasks" / f"scenario_{ordinal:03d}.json"
        if not path.exists():
            missing.append(ordinal)
            continue
        try:
            package = load(path)
            for name in TASK_NAMES:
                if task_complete((package.get("tasks") or {}).get(name)):
                    task_counts[name] += 1
            if package_complete(package):
                complete.append(ordinal)
            else:
                incomplete.append({
                    "ordinal": ordinal,
                    "missing_tasks": sorted(
                        set(TASK_NAMES) - set(package.get("tasks") or {})
                    ),
                    "task_errors": package.get("task_errors", {}),
                    "task_gaps": package.get("task_gaps", {}),
                })
        except Exception as exc:
            incomplete.append({"ordinal": ordinal, **_artifact_error(path, exc)})
    return {
        "expected": expected,
        "package_count": expected - len(missing),
        "complete_packages": len(complete),
        "task_answer_counts": task_counts,
        "missing_ordinals": missing,
        "incomplete": incomplete,
        "complete": len(complete) == expected,
    }


def audit_gate3_model(batch, expected):
    path = batch / "gate3" / "model_reviews.json"
    payload = load(path, {}) or {}
    records = payload.get("records") or []
    failures = payload.get("failures") or []
    decisions = {item.get("decision") for item in records}
    complete = (
        payload.get("model_count") == 1
        and len(records) == expected
        and not failures
        and decisions <= {"approve", "reject"}
        and bool(payload.get("complete"))
    )
    return {
        "expected": expected,
        "model_count": payload.get("model_count", 0),
        "model": payload.get("model"),
        "reviewed_count": len(records),
        "failure_count": len(failures),
        "decision_counts": payload.get("decision_counts", {}),
        "complete": complete,
    }


def audit_review_files(batch, expected):
    files = {
        "gate1": batch / "human_review" / "gate1_scenarios.json",
        "gate3": batch / "human_review" / "gate3_rollouts.json",
        "gate4": batch / "human_review" / "gate4_tasks.json",
        "index": batch / "human_review" / "index.json",
    }
    result = {}
    for name, path in files.items():
        value = load(path, {}) or {}
        result[name] = {
            "present": path.is_file(),
            "population_count": value.get("population_count"),
            "record_count": len(value.get("records") or []),
        }
    result["complete"] = (
        result["gate1"]["record_count"] == expected
        and result["gate3"]["record_count"] == expected
        and result["gate4"]["record_count"] == expected * len(TASK_NAMES)
        and result["index"]["present"]
    )
    return result


def audit_gate2(batch):
    manifest = load(batch / "gate2" / "manifest.json", {}) or {}
    e1 = int(manifest.get("e1_review_items", 0) or 0)
    e2 = int(manifest.get("e2_review_items", 0) or 0)
    e9 = int(manifest.get("e9_review_items", 0) or 0)
    return {
        "manifest_present": bool(manifest),
        "mode": manifest.get("mode"),
        "e1_review_items": e1,
        "e2_review_items": e2,
        "e9_review_items": e9,
        "packets_ready": e1 > 0 and e2 > 0 and e9 >= 10,
        "machine_evidence_ready": bool(manifest.get("machine_evidence_ready")),
        "non_video_machine_evidence_ready": bool(
            manifest.get("non_video_machine_evidence_ready")
        ),
        "experiments_ready": bool(
            manifest.get("non_video_machine_evidence_ready")
        ),
        "execution_status": manifest.get("execution_status"),
        "human_review_required": manifest.get("human_review_required", True),
    }


def audit_batch(batch, expected=150, prefix="CF150_"):
    batch = Path(batch).resolve()
    scenario_batch = batch
    nested_scenario_root = batch / "scenario" / "scenarios"
    if not (batch / "scenarios").exists() and nested_scenario_root.exists():
        scenario_batch = batch / "scenario"
    stages = {
        "scenarios": audit_scenarios(scenario_batch, expected, prefix),
        "rollouts": audit_rollouts(batch, expected, prefix),
        "gate2_packet": audit_gate2(batch),
        "multimodal_plan": audit_multimodal_plan(batch, expected),
        "gate2_experiments": audit_gate2(batch),
        "sources": audit_sources(batch, expected),
        "t2_specs": audit_t2_specs(batch, expected),
        "t2_pairs": audit_t2_pairs(batch, expected),
        "tasks": audit_tasks(batch, expected),
        "gate3_review": audit_gate3_model(batch, expected),
        "human_review": audit_review_files(batch, expected),
    }
    blockers = []
    for name, report in stages.items():
        complete = (
            report.get("packets_ready") if name == "gate2_packet"
            else report.get("experiments_ready") if name == "gate2_experiments"
            else report.get("complete")
        )
        if not complete:
            blockers.append(name)
    return {
        "format": "socialflux_active_batch_status_v1",
        "generated_at_utc": now(),
        "batch_root": str(batch),
        "expected_count": expected,
        "scenario_id_prefix": prefix,
        "network_requests_performed": 0,
        "policy": "generate_all_then_human_postfilter",
        "stages": stages,
        "blockers": blockers,
        "artifact_pipeline_complete": not blockers,
    }


def stage_complete(report, stage):
    value = report["stages"][stage]
    if stage == "gate2_packet":
        return bool(value.get("packets_ready"))
    if stage == "gate2_experiments":
        return bool(value.get("experiments_ready"))
    return bool(value.get("complete"))


def failure_report(report):
    failures = {}
    for name, value in report["stages"].items():
        if stage_complete(report, name):
            continue
        failures[name] = {
            key: item for key, item in value.items()
            if key in {
                "missing_ordinals", "incomplete_ordinals", "invalid",
                "duplicates", "incomplete", "status_counts",
                "e1_review_items", "e2_review_items", "e9_review_items",
                "packets_ready",
                "machine_evidence_ready", "record_count", "authored",
                "non_video_machine_evidence_ready", "experiments_ready",
                "execution_status",
                "completed", "complete_packages", "task_answer_counts",
                "trajectory_count", "covered_scenarios", "request_count",
                "provider_status", "model_count", "model",
                "reviewed_count", "failure_count", "decision_counts",
            }
        }
    return {
        "format": "socialflux_active_batch_failures_v1",
        "generated_at_utc": report["generated_at_utc"],
        "batch_root": report["batch_root"],
        "blockers": report["blockers"],
        "failures": failures,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, default=150)
    parser.add_argument("--scenario-id-prefix", default="CF150_")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    report = audit_batch(
        args.batch_root,
        expected=args.expected_count,
        prefix=args.scenario_id_prefix,
    )
    if not args.no_write:
        batch = args.batch_root.resolve()
        atomic(batch / "pipeline_status.json", report)
        atomic(batch / "pipeline_failures.json", failure_report(report))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.strict and not report["artifact_pipeline_complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
