#!/usr/bin/env python3
"""Wait for generation work, then run machine Gate 2 and Gate 3 in order."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def project_path(path):
    path = Path(path).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def process_alive(pid):
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    stat = Path(f"/proc/{pid}/stat")
    if not stat.exists():
        return False
    try:
        return stat.read_text(encoding="utf-8").split()[2] != "Z"
    except (OSError, IndexError):
        return False


def wait_for_processes(pids, poll_seconds):
    pending = set(pids)
    while pending:
        pending = {pid for pid in pending if process_alive(pid)}
        if not pending:
            break
        print(json.dumps({
            "status": "waiting_for_upstream",
            "pids": sorted(pending),
            "checked_at_utc": now(),
        }), flush=True)
        time.sleep(poll_seconds)


def run_stage(name, command, batch, manifest, retries, cooldown):
    log_path = batch / "logs" / f"post_gates_{name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    attempt = 0
    while True:
        attempt += 1
        manifest["current_stage"] = name
        manifest["status"] = "running"
        manifest["stages"][name] = {
            "status": "running",
            "attempt": attempt,
            "command": command,
            "log": str(log_path),
            "started_at_utc": now(),
        }
        atomic(batch / "post_generation_gates.json", manifest)
        print(json.dumps({"stage": name, "status": "starting", "attempt": attempt}), flush=True)
        with log_path.open("a", encoding="utf-8") as log:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in process.stdout:
                log.write(line)
                log.flush()
                print(f"[{name}] {line}", end="", flush=True)
            returncode = process.wait()
        record = manifest["stages"][name]
        record["returncode"] = returncode
        record["finished_at_utc"] = now()
        record["status"] = "completed" if returncode == 0 else "failed"
        atomic(batch / "post_generation_gates.json", manifest)
        if returncode == 0:
            return
        if attempt > retries:
            manifest["status"] = "failed"
            manifest["current_stage"] = name
            atomic(batch / "post_generation_gates.json", manifest)
            raise SystemExit(returncode)
        print(json.dumps({
            "stage": name,
            "status": "retry_wait",
            "attempt": attempt,
            "cooldown_seconds": cooldown,
        }), flush=True)
        time.sleep(cooldown)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-pid", type=int, action="append", default=[])
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument("--scenario-root", type=Path, required=True)
    parser.add_argument("--rollout-root", type=Path, required=True)
    parser.add_argument("--rollout-config", type=Path, required=True)
    parser.add_argument("--model-routes", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--request-budget", type=int)
    parser.add_argument("--stage-retries", type=int, default=2)
    parser.add_argument("--retry-cooldown", type=int, default=90)
    parser.add_argument("--poll-seconds", type=int, default=30)
    args = parser.parse_args(argv)
    if args.expected_count < 1 or args.workers < 1:
        parser.error("expected-count and workers must be positive")
    if args.stage_retries < 0 or args.retry_cooldown < 1 or args.poll_seconds < 1:
        parser.error("retry and polling values are invalid")

    batch = project_path(args.batch_root)
    scenario_root = project_path(args.scenario_root)
    rollout_root = project_path(args.rollout_root)
    rollout_config = project_path(args.rollout_config)
    model_routes = project_path(args.model_routes)
    audit_root = batch / "gate2" / "audit_inputs"
    request_budget = args.request_budget or (
        args.expected_count * args.max_attempts
    )
    manifest = {
        "format": "socialflux_post_generation_gates_v1",
        "batch_root": str(batch),
        "expected_count": args.expected_count,
        "human_stages": "skipped",
        "status": "waiting_for_upstream" if args.wait_pid else "running",
        "current_stage": None,
        "created_at_utc": now(),
        "stages": {},
    }
    atomic(batch / "post_generation_gates.json", manifest)
    wait_for_processes(args.wait_pid, args.poll_seconds)

    commands = {
        "gate2_inputs": [
            sys.executable, "scripts/prepare_gate2_audit_inputs.py",
            "--scenario-root", str(scenario_root),
            "--rollout-root", str(rollout_root),
            "--output-root", str(audit_root),
            "--expected-count", str(args.expected_count),
        ],
        "gate2": [
            sys.executable, "scripts/prepare_batch_gate2.py",
            "--batch-root", str(batch),
            "--scenario-root", str(scenario_root),
            "--rollout-root", str(audit_root),
            "--rollout-config", str(rollout_config),
            "--all-scenarios",
            "--allow-pending-video",
        ],
        "gate3_inputs": [
            sys.executable, "scripts/prepare_gate3_audit_inputs.py",
            "--batch-root", str(batch),
            "--scenario-root", str(scenario_root),
            "--rollout-root", str(rollout_root),
            "--expected-count", str(args.expected_count),
        ],
        "gate3": [
            sys.executable, "scripts/review_active_rollouts.py",
            "--batch-root", str(batch),
            "--model-routes", str(model_routes),
            "--count", str(args.expected_count),
            "--workers", str(args.workers),
            "--max-attempts", str(args.max_attempts),
            "--request-budget", str(request_budget),
            "--resume",
            "--require-complete",
        ],
    }
    for name, command in commands.items():
        retries = args.stage_retries if name in {"gate2", "gate3"} else 0
        run_stage(
            name, command, batch, manifest,
            retries=retries, cooldown=args.retry_cooldown,
        )
    manifest["status"] = "completed"
    manifest["current_stage"] = None
    manifest["finished_at_utc"] = now()
    atomic(batch / "post_generation_gates.json", manifest)
    print(json.dumps({
        "status": "completed",
        "batch_root": str(batch),
        "gate2_manifest": str(batch / "gate2" / "manifest.json"),
        "gate3_reviews": str(batch / "gate3" / "model_reviews.json"),
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
