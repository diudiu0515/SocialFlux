#!/usr/bin/env python3
"""Run the authorized recovery and full available cohort, publishing progress."""
import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from time import sleep
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.t4_batch import save

SOURCE = ROOT / "build/t4_expanded_api_20261020/run"
RECOVERY = ROOT / "build/t4_transport_recovery_20261021/run"
FULL = ROOT / "build/t4_reliable41_20261021/run"
REPORT = ROOT / "reports/experiments/2026-10-21_t4_continuation"


def now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


def load(path):
    return json.loads(path.read_text()) if path.exists() else {}


def report():
    runs = {key: {"status": load(path / "status.json"), "summary": load(path / "summary.json"),
                  "budget": load(path / "request_budget.json")}
            for key, path in (("original_diagnostic", SOURCE), ("transport_recovery", RECOVERY), ("full41", FULL))}
    data = {"updated_at": now(), "runs": runs,
            "interpretation": "Recovery inherits original completed episodes, not new independent samples. Full41 is a separate revised-protocol cohort; do not pool with historical33. All machine scores are exploratory; Gate and human validation remain pending."}
    save(REPORT.with_suffix(".json"), data)
    recovery, full = runs["transport_recovery"], runs["full41"]
    rs, fs = recovery["status"], full["status"]
    lines = ["# T4 实验续跑与覆盖", "", f"更新：{data['updated_at']}（北京时间）。", "",
        "旧 33 场景批次 GPT 39/66 条失败、Claude 30/66 条失败，因此仅形成 6/8 个完整对照。"
        "最新六场景诊断共 96 个槽位：48 条完成、36 条失败、12 条视觉不支持。"
        "失败中 25 条为可重试传输故障，另外 4 条格式校验失败、4 条截断、3 条采样参数不兼容。", "",
        "## 传输故障恢复", "",
        f"状态：`{rs.get('status', 'queued')}`；已处理 {rs.get('finished', 0)}/25 条；"
        f"新增 API 请求 {recovery['budget'].get('request_count', 0)}/1500，原批次 1197 次请求另计。", "",
        "25/25 条已通过无网络的请求逐字匹配及原有对话状态重放检查。"
        "成功回答和原始失败全部保留；仅在没有有效返回的传输故障处继续，每个新请求最多尝试 3 次。"
        "格式、截断和参数错误不通过反复抽样变成成功。恢复结果继承原来完整轨迹，不能算新独立样本。", "",
        "| 模型 | 恢复前完整配对 | 恢复后完整配对 | 当前完成轨迹 | 当前失败 |",
        "|---|---:|---:|---:|---:|"]
    for name, original in runs["original_diagnostic"]["summary"].items():
        current = recovery["summary"].get(name, original)
        counts = current.get("status_counts", {})
        lines.append(f"| {name} | {original.get('matched_scenarios', 0)} | {current.get('matched_scenarios', 0)} | {counts.get('completed', 0)} | {counts.get('failed', 0)} |")
    outcomes = Counter(v.get("status") for v in rs.get("outcomes", {}).values())
    lines += ["", f"本次恢复结果：`{dict(outcomes)}`。", "", "## 41 场景新批次", "",
        f"状态：`{fs.get('status', 'queued_after_recovery')}`；已记录 {fs.get('finished', 0)}/164 条；"
        f"API 请求 {full['budget'].get('request_count', 0)}/10000。", "",
        "覆盖所有视频素材齐全的 41 个场景，GPT、Claude 两个模型，每场景各有文字和视频条件。"
        "两条件均采用首次视频事件后的回应机会规则，保持原状态、触发阈值、评分和 20 轮上限。"
        "默认并发 2；传输错误最多尝试 3 次，完整记录每次请求。先跑两个场景，"
        "要求失败比例不超过 20% 且每个支持视频的模型至少形成一个完整配对；之后每两个场景检查可靠性。", "",
        "| 模型 | 已记录槽位 | 完成轨迹 | 失败 | 完整配对 / 41 | 目标达成配对差及 95% 区间 |",
        "|---|---:|---:|---:|---:|---|"]
    for name, summary in full["summary"].items():
        counts = summary.get("status_counts", {})
        score = summary.get("paired_text_video_minus_text", {}).get("goal_achievement", {})
        lines.append(f"| {name} | {sum(counts.values())} | {counts.get('completed', 0)} | {counts.get('failed', 0)} | {summary.get('matched_scenarios', 0)} | {score.get('mean')} / {score.get('bootstrap_ci95')} |")
    lines += ["", "新批次与旧 33 场景及六场景诊断分开分析。9 个素材不完整的场景尚未纳入。"
        "执行完成不代表四 Gate 通过；人工校准仍待完成。恢复维度无机会时保持 N/A，不填零。", "",
        "[续跑配置](../../configs/gpt50_experiment/t4_multimodal_experiment.reliable41_20261021.json) · "
        "[恢复来源与选择记录](../../build/t4_transport_recovery_20261021/run/recovery_manifest.json) · "
        "[新批次状态](../../build/t4_reliable41_20261021/run/status.json)"]
    REPORT.with_suffix(".md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()
    if args.report_only:
        report()
        return
    stages = [
        (RECOVERY, ROOT / "build/t4_expanded_api_20261020/runtime",
         [sys.executable, "-u", str(ROOT / "scripts/resume_t4_transport.py"), "--source", str(SOURCE),
          "--output", str(RECOVERY), "--workers", "2", "--request-budget", "1500"]),
        (FULL, FULL.parent / "runtime",
         [sys.executable, "-u", "scripts/run_t4_multimodal_experiment.py", "--config",
          "configs/gpt50_experiment/t4_multimodal_experiment.reliable41_20261021.json", "--output", str(FULL)]),
    ]
    for directory, runtime, command in stages:
        env = dict(os.environ)
        if directory == RECOVERY:
            env["T4_FROZEN_RUNTIME"] = str(runtime)
        with (directory.parent / "run.log").open("a") as log:
            process = subprocess.Popen(command, cwd=runtime, env=env, stdout=log, stderr=subprocess.STDOUT)
        save(directory / "process.json", {"pid": process.pid, "command": command, "cwd": str(runtime), "started_at": now()})
        while process.poll() is None:
            report()
            sleep(30)
        if process.returncode:
            save(directory / "launcher_exit.json", {"exit_code": process.returncode, "finished_at": now()})
        report()
    save(FULL.parent / "continuation_complete.json", {"at": now(), "status": load(FULL / "status.json").get("status")})


if __name__ == "__main__":
    main()
