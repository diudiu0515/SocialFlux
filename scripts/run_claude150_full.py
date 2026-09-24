#!/usr/bin/env python3
"""Run the isolated fresh Claude150 candidate pipeline end to end."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_active_batch import audit_batch, failure_report, stage_complete


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BATCH = ROOT / "data" / "claude150_v1"
STAGES = (
    "scenarios",
    "rollouts",
    "sources",
    "t2_specs",
    "t2_pairs",
    "tasks",
    "gate3_review",
    "gate4_review",
    "gate2_packet",
    "multimodal_plan",
    "gate2_experiments",
    "review_index",
)


def now():
    return datetime.now(timezone.utc).isoformat()


def load(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def validate_stage_output(name, batch, expected_count):
    """Validate materialized output without constructing a provider."""
    report = audit_batch(batch, expected=expected_count, prefix="CF150_")
    atomic(batch / "pipeline_status.json", report)
    atomic(batch / "pipeline_failures.json", failure_report(report))
    if name == "gate4_review":
        gate4 = load(batch / "gate4" / "model_reviews.json", {})
        if gate4.get("complete") is not True:
            raise ValueError("Gate4 model review is incomplete")
        return report
    audit_stage = "human_review" if name == "review_index" else name
    if not stage_complete(report, audit_stage):
        detail = report["stages"][audit_stage]
        raise ValueError(
            f"stage {name} returned success but offline validation failed: "
            f"{json.dumps(detail, ensure_ascii=False)}"
        )
    return report


def run_stage_once(name, command, batch, manifest, expected_count):
    logs = batch / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log_path = logs / f"{name}.log"
    manifest["stages"][name] = {
        "status": "running",
        "started_at_utc": now(),
        "command": command,
        "log": str(log_path.relative_to(ROOT)),
    }
    manifest["status"] = "running"
    manifest["current_stage"] = name
    manifest["updated_at_utc"] = now()
    atomic(batch / "pipeline_manifest.json", manifest)
    print(json.dumps({
        "stage": name,
        "status": "starting",
        "log": str(log_path),
    }, ensure_ascii=False), flush=True)
    with log_path.open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        for line in process.stdout:
            log.write(line)
            log.flush()
            print(f"[{name}] {line}", end="", flush=True)
        returncode = process.wait()
    validation_error = None
    if returncode == 0:
        try:
            validate_stage_output(name, batch, expected_count)
        except Exception as exc:
            validation_error = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            returncode = 3
    stage = manifest["stages"][name]
    stage["finished_at_utc"] = now()
    stage["returncode"] = returncode
    stage["status"] = "completed" if returncode == 0 else "failed"
    if validation_error is not None:
        stage["offline_validation_error"] = validation_error
    manifest["updated_at_utc"] = now()
    atomic(batch / "pipeline_manifest.json", manifest)
    if returncode:
        manifest["status"] = "failed"
        manifest["current_stage"] = name
        atomic(batch / "pipeline_manifest.json", manifest)
        raise SystemExit(returncode)


def run_stage(
    name, command, batch, manifest, *, expected_count,
    retry_limit=0, retry_cooldown=60,
):
    """Retry a resumable stage without discarding already materialized work."""
    retries = 0
    while True:
        try:
            return run_stage_once(
                name, command, batch, manifest, expected_count
            )
        except SystemExit:
            if retries >= retry_limit:
                raise
            retries += 1
            stage = manifest["stages"][name]
            stage["status"] = "retry_wait"
            stage["retry_number"] = retries
            stage["retry_limit"] = retry_limit
            stage["retry_cooldown_seconds"] = retry_cooldown
            manifest["status"] = "retry_wait"
            manifest["updated_at_utc"] = now()
            atomic(batch / "pipeline_manifest.json", manifest)
            print(json.dumps({
                "stage": name,
                "status": "retry_wait",
                "retry": retries,
                "retry_limit": retry_limit,
                "cooldown_seconds": retry_cooldown,
            }, ensure_ascii=False), flush=True)
            time.sleep(retry_cooldown)


def review_index(batch):
    gate1 = load(batch / "human_review" / "gate1_scenarios.json", {})
    gate3 = load(batch / "human_review" / "gate3_rollouts.json", {})
    gate4 = load(batch / "human_review" / "gate4_tasks.json", {})
    task_summary = load(batch / "tasks" / "summary.json", {})
    t2_summary = load(batch / "t2_runs" / "primary" / "summary.json", {})
    gate2 = load(batch / "gate2" / "manifest.json", {})
    gate3_model = load(batch / "gate3" / "model_reviews.json", {})
    gate4_model = load(batch / "gate4" / "model_reviews.json", {})
    multimodal = load(batch / "multimodal" / "manifest.json", {})
    payload = {
        "format": "socialflux_claude150_human_review_index_v1",
        "created_at_utc": now(),
        "batch": "claude150_v1",
        "model": "claude-fable-5",
        "parent_catalog": None,
        "qwen_inputs": [],
        "review_policy": "full_population_after_generation",
        "warning": (
            "All machine screens, answers, and model reviews are proposals only. "
            "No record is human-accepted until a real reviewer attests it."
        ),
        "counts": {
            "gate1_scenarios": gate1.get("population_count", 0),
            "gate3_rollouts": gate3.get("population_count", 0),
            "gate4_tasks": gate4.get("population_count", 0),
            "task_packages": task_summary.get("package_count", 0),
            "t2_results": t2_summary.get("result_count", 0),
            "gate2_e1_items": gate2.get("e1_review_items", 0),
            "gate2_e2_items": gate2.get("e2_review_items", 0),
            "gate3_model_reviews": gate3_model.get("reviewed_count", 0),
            "gate4_model_reviews": gate4_model.get("reviewed_count", 0),
            "multimodal_requests": multimodal.get("request_count", 0),
        },
        "gate2_machine_ready": gate2.get("machine_evidence_ready", False),
        "gate2_non_video_machine_ready": gate2.get(
            "non_video_machine_evidence_ready", False
        ),
        "files": {
            "gate1_scenarios": "human_review/gate1_scenarios.json",
            "gate3_rollouts": "human_review/gate3_rollouts.json",
            "gate4_tasks": "human_review/gate4_tasks.json",
            "scenario_manifest": "scenarios/manifest.json",
            "rollout_progress": "rollouts/progress.json",
            "task_summary": "tasks/summary.json",
            "t2_summary": "t2_runs/primary/summary.json",
            "gate2_manifest": "gate2/manifest.json",
            "gate2_persona_intervention": "gate2/persona_intervention.json",
            "gate2_video_state_consistency": "gate2/video_state_consistency.json",
            "gate3_model_reviews": "gate3/model_reviews.json",
            "gate4_model_reviews": "gate4/model_reviews.json",
            "multimodal_manifest": "multimodal/manifest.json",
        },
    }
    atomic(batch / "human_review" / "index.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def command_for(stage, args, batch):
    python = sys.executable
    common = ["--count", str(args.count)]
    if stage == "scenarios":
        return [
            python, "scripts/generate_claude150_scenarios.py",
            "--output", str(batch),
            "--model-routes", str(args.model_routes),
            "--workers", str(args.scenario_workers),
            "--max-attempts", str(args.max_attempts),
            "--resume",
            *(
                ["--allow-route-migration"] if args.allow_route_migration else []
            ),
            *common,
        ]
    if stage == "rollouts":
        return [
            python, "scripts/generate_long_rollout_pool.py",
            "--rollout-config", str(args.rollout_config),
            "--scenarios", str(batch / "scenarios"),
            "--output", str(batch / "rollouts"),
            "--retry-limit", "1",
            "--workers", str(args.rollout_workers),
            "--request-budget", str(args.count * 20 * 18),
            "--allow-unreviewed",
            "--resume",
            *(
                ["--allow-route-migration"] if args.allow_route_migration else []
            ),
        ]
    if stage == "gate2_packet":
        return [
            python, "scripts/prepare_batch_gate2.py",
            "--batch-root", str(batch),
            "--scenario-root", str(batch / "scenarios"),
            "--rollout-root", str(batch / "rollouts"),
            "--rollout-config", str(args.rollout_config),
            "--scenario-limit", "10",
            "--prepare-only",
        ]
    if stage == "multimodal_plan":
        return [
            python, "scripts/prepare_multimodal_video_queue.py",
            "--batch-root", str(batch),
            "--scenario-root", str(batch / "scenarios"),
            "--rollout-root", str(batch / "rollouts"),
            "--config", "configs/multimodal_generation.json",
            "--expected-count", str(args.count),
        ]
    if stage == "gate2_experiments":
        return [
            python, "scripts/prepare_batch_gate2.py",
            "--batch-root", str(batch),
            "--scenario-root", str(batch / "scenarios"),
            "--rollout-root", str(batch / "rollouts"),
            "--rollout-config", str(args.rollout_config),
            "--scenario-limit", "10",
            "--gpt-routes", "configs/gpt50_experiment/model_routes.astra.json",
            "--claude-routes", str(args.model_routes),
            "--allow-pending-video",
        ]
    if stage == "sources":
        return [
            python, "scripts/prepare_claude150_sources.py",
            "--batch-root", str(batch), *common,
        ]
    if stage == "t2_specs":
        return [
            python, "scripts/author_claude150_t2_specs.py",
            "--batch-root", str(batch),
            "--model-routes", str(args.model_routes),
            "--workers", str(args.task_workers),
            "--request-budget", str(args.count * 2),
            "--resume",
            "--require-complete",
            *common,
        ]
    if stage == "t2_pairs":
        return [
            python, "scripts/build_t2_source_adapted_pairs.py",
            "--config", str(batch / "t2_specs" / "runtime_config.json"),
            "--audit", str(batch / "automatic_gate_audit.json"),
            "--output", str(batch / "t2_runs"),
            "--run-id", "primary",
            "--all",
            "--resume-incomplete",
            "--require-complete",
            "--workers", str(args.task_workers),
            "--request-budget", str(args.count * 40),
        ]
    if stage == "tasks":
        return [
            python, "scripts/build_claude150_tasks.py",
            "--batch-root", str(batch),
            "--model-routes", str(args.model_routes),
            "--t2-run-dir", str(batch / "t2_runs" / "primary"),
            "--workers", str(args.task_workers),
            "--request-budget", str(args.count * 14),
            "--resume",
            "--require-complete",
            *common,
        ]
    if stage == "gate3_review":
        return [
            python, "scripts/review_active_rollouts.py",
            "--batch-root", str(batch),
            "--model-routes", str(args.model_routes),
            "--count", str(args.count),
            "--workers", str(args.task_workers),
            "--max-attempts", str(args.max_attempts),
            "--request-budget", str(args.count * args.max_attempts),
            "--resume",
            "--require-complete",
        ]
    if stage == "gate4_review":
        return [
            python, "scripts/review_active_tasks.py",
            "--batch-root", str(batch),
            "--model-routes", str(args.model_routes),
            "--workers", str(args.task_workers),
            "--max-attempts", str(args.max_attempts),
            "--request-budget", str(args.count * 3 * args.max_attempts),
            "--resume",
            "--require-complete",
        ]
    raise ValueError(f"unsupported command stage: {stage}")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-root", type=Path, default=DEFAULT_BATCH)
    parser.add_argument(
        "--model-routes",
        type=Path,
        default=ROOT / "configs" / "claude150_v1" / "model_routes.chat.pool2.json",
    )
    parser.add_argument(
        "--rollout-config",
        type=Path,
        default=ROOT / "configs" / "claude150_v1" / "rollout.json",
    )
    parser.add_argument("--count", type=int, default=150)
    parser.add_argument("--scenario-workers", type=int, default=1)
    parser.add_argument("--rollout-workers", type=int, default=1)
    parser.add_argument("--task-workers", type=int, default=1)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--allow-route-migration", action="store_true")
    parser.add_argument(
        "--stage-retries", type=int, default=0,
        help="number of resumable stage retries after the first failed run",
    )
    parser.add_argument("--stage-retry-cooldown", type=int, default=60)
    parser.add_argument("--from-stage", choices=STAGES, default=STAGES[0])
    parser.add_argument("--through-stage", choices=STAGES, default=STAGES[-1])
    args = parser.parse_args(argv)
    start = STAGES.index(args.from_stage)
    end = STAGES.index(args.through_stage)
    if start > end:
        parser.error("from-stage must not follow through-stage")
    if args.stage_retries < 0:
        parser.error("stage-retries must be non-negative")
    if args.stage_retry_cooldown < 1:
        parser.error("stage-retry-cooldown must be positive")
    batch = args.batch_root.resolve()
    batch.mkdir(parents=True, exist_ok=True)
    manifest_path = batch / "pipeline_manifest.json"
    manifest = load(manifest_path, {}) or {}
    manifest.update({
        "format": "socialflux_claude150_pipeline_manifest_v1",
        "batch_root": str(batch),
        "expected_count": args.count,
        "model": "claude-fable-5",
        "parent_catalog": None,
        "qwen_inputs": [],
        "gate_policy": "generate_all_then_human_postfilter",
        "stages": manifest.get("stages", {}),
        "created_at_utc": manifest.get("created_at_utc", now()),
        "status": "running",
        "updated_at_utc": now(),
    })
    atomic(manifest_path, manifest)
    for stage in STAGES[start:end + 1]:
        if stage == "review_index":
            review_index(batch)
            validate_stage_output(stage, batch, args.count)
            manifest["stages"][stage] = {
                "status": "completed",
                "finished_at_utc": now(),
            }
            atomic(manifest_path, manifest)
        else:
            run_stage(
                stage,
                command_for(stage, args, batch),
                batch,
                manifest,
                expected_count=args.count,
                retry_limit=args.stage_retries,
                retry_cooldown=args.stage_retry_cooldown,
            )
    manifest["status"] = "completed"
    manifest["current_stage"] = None
    manifest["finished_at_utc"] = now()
    manifest["updated_at_utc"] = now()
    atomic(manifest_path, manifest)
    print(json.dumps({
        "status": "completed",
        "batch_root": str(batch),
        "review_index": str(batch / "human_review" / "index.json"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
