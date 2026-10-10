#!/usr/bin/env python3
"""Run several terminal text judges in the background; retain each model's results."""

import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from copy import deepcopy
from datetime import datetime
import fcntl
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.t4_batch import run_saved_batch, save, digest
from evaluation.t4_configuration import load_t4_config
from evaluation.t4_evaluation import T4_DIMENSIONS
from providers.factory import public_provider_config
from providers.model_routes import ModelRoutes


def now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / ".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        config = json.loads(args.config.read_text())
        base = load_t4_config(config["base_t4_config"])
        plans = []
        for model in config["judges"]:
            provider = ModelRoutes.load(model["model_routes"]).provider_config("t4_judge")
            provider.update(model.get("overrides", {}))
            plans.append((model, provider))
        frozen = {"configuration": config, "providers": {m["id"]: public_provider_config(p) for m, p in plans},
                  "input_manifest_sha256": digest(json.loads(Path(config["input_manifest"]).read_text())),
                  "experiment_type": "same_saved_policy_trajectories_multiple_terminal_judges",
                  "policy_condition": "text_only", "judge_condition": "text_only",
                  "not_a_policy_model_comparison": True}
        path = args.output / "preregistration.json"
        if path.exists() and json.loads(path.read_text()) != frozen:
            raise ValueError("comparison config changed; use a new output directory")
        save(path, frozen)
        status = {"status": "running", "started_at": now(), "updated_at": now(), "models": {}}
        def execute(model, provider):
            if model.get("reuse_run"):
                source = Path(model["reuse_run"])
                original = json.loads((source / "manifest.json").read_text())
                if original["identity"]["source_manifest_sha256"] != frozen["input_manifest_sha256"]:
                    raise ValueError("reused scores have different input inventory")
                if original["identity"]["judge"]["provider"]["model"] != provider["model"]:
                    raise ValueError("reused judge model mismatch")
                summary = json.loads((source / "summary.json").read_text())
                return {"status": "reused", "run": str(source), "summary": summary, "new_api_requests": 0}
            runtime = deepcopy(base)
            runtime["judge"]["provider"] = provider
            target = args.output / model["id"]
            summary = run_saved_batch(config["input_manifest"], target, runtime, workers=1,
                                      max_attempts=2, resume=(target / "manifest.json").exists())
            return {"status": "completed", "run": str(target), "summary": summary,
                    "new_api_requests": summary["api_request_count"]}
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = {pool.submit(execute, model, provider): model for model, provider in plans}
            while pending:
                done, _ = wait(pending, timeout=30, return_when=FIRST_COMPLETED)
                for future in done:
                    model = pending.pop(future)
                    try:
                        status["models"][model["id"]] = future.result()
                    except Exception as exc:
                        status["models"][model["id"]] = {"status": "failed", "error": str(exc)}
                for model in pending.values():
                    progress = args.output / model["id"] / "progress.json"
                    status["models"][model["id"]] = {"status": "running", "run": str(progress.parent),
                        "progress": json.loads(progress.read_text()) if progress.exists() else {}}
                status["updated_at"] = now()
                save(args.output / "status.json", status)
        status["status"] = "finished_with_failures" if any(v["status"] == "failed" or
            v.get("summary", {}).get("status_counts", {}).get("judge_failed", 0) or
            v.get("summary", {}).get("status_counts", {}).get("runner_failed", 0)
            for v in status["models"].values()) else "completed"
        status["finished_at"] = now()
        save(args.output / "status.json", status)
        lines = ["GPT50 T4 多模型终局裁判对照", f"更新时间：{now()}",
                 "使用同一批已保存的 text_only 策略轨迹；这是裁判对照，不是被测策略模型之间的能力比较。",
                 "text+video 需单独完成资产覆盖和实际媒体输入检验。本结果不估计模态收益。", ""]
        for name, result in status["models"].items():
            lines.append(f"{name}: {result['status']}; new API requests={result.get('new_api_requests')}")
            for dimension in T4_DIMENSIONS:
                stats = result.get("summary", {}).get("conditions", {}).get("text_only", {}).get("metrics", {}).get(dimension, {})
                lines.append(f"  {dimension}: mean={stats.get('mean')}, n={stats.get('n')}, CI95={stats.get('bootstrap_ci95')}")
        lines.append("所有结果为机器评价，尚未人工校准。各模型失败记录保留在各自目录，不替换为零分。")
        (args.output / "report.txt").write_text("\n".join(lines) + "\n")
        print(json.dumps({"status": status["status"], "finished_at": status["finished_at"]}), flush=True)


if __name__ == "__main__":
    main()
