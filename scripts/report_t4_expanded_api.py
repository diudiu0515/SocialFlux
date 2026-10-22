#!/usr/bin/env python3
"""Read-only reports for the independently frozen, expanded AutoDL diagnostic."""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.t4_batch import describe, save
from scripts.audit_t4_multimodal_exposure import (
    Evidence, METRICS, NO_MEDIA_REASONS, cell, now, process_alive,
    read_episode, summarize_model, write_csv,
)

RUN_ID = "t4_expanded_api_20261020"
PREFIX = ROOT / "reports/experiments/2026-10-20_t4_expanded_api"


def snapshot():
    evidence = Evidence(ROOT)
    directory = ROOT / "build" / RUN_ID / "run"
    plan = evidence.read(directory / "plan.json")
    config = plan["config"]
    names = config["policy_models"]
    sids = config["scenario_ids"]
    alive = process_alive(directory)
    capabilities = {
        name: evidence.read(directory / "capabilities" / name / "result.json", {})
        for name in names
    }
    rows, calls, events, scenes, effects = [], [], [], [], {}
    for sid in sids:
        for name in names:
            pair = {}
            for condition in ("text_only", "text_video"):
                row, cs, es = read_episode(
                    evidence, RUN_ID, sid, name, condition, plan, capabilities[name], alive)
                pair[condition] = row
                rows.append(row)
                calls.extend(cs)
                events.extend(es)
            text, video = pair["text_only"], pair["text_video"]
            paired = video["scored_with_verified_media"] and text["status"] == "completed"
            text["valid_pair"] = video["valid_pair"] = bool(paired)
            first_text, first_video = text["first_policy_call"], video["first_policy_call"]
            scenes.append({
                "scenario_id": sid, "model_id": name, "model_name": video["model_name"],
                "text_status": text["status"], "video_status": video["status"],
                "video_display": cell(video), "transport": video["transport"],
                "trigger_turn_ids": video["trigger_turn_ids"],
                "video_deferred_turn_ids": video["media_completion_deferred_turn_ids"],
                "text_deferred_turn_ids": text["media_completion_deferred_turn_ids"],
                "successful_media_calls": video["successful_media_call_count"],
                "valid_pair": bool(paired),
                "core_four_delta": (video["scores"]["core_four_mean"] - text["scores"]["core_four_mean"])
                if paired else None,
                "first_messages_equal": first_text["messages_sha256"] == first_video["messages_sha256"]
                if first_text and first_video else None,
                "first_sampling_equal": first_text["sampling"] == first_video["sampling"]
                if first_text and first_video else None,
                "no_media_reason": NO_MEDIA_REASONS[video["no_media_reason"]],
                "failure_roles": video["terminal_failure_roles"],
                "error_category": video["error_category"], "error": video["error"],
            })
    lookup = {(r["scenario_id"], r["model_id"], r["condition"]): r for r in rows}
    for name in names:
        paired_video = [r for r in rows if r["model_id"] == name
                        and r["condition"] == "text_video" and r["valid_pair"]]
        effects[name] = {}
        for metric in METRICS:
            deltas = []
            for video in paired_video:
                text = lookup[(video["scenario_id"], name, "text_only")]
                a, b = video["scores"][metric], text["scores"][metric]
                if a is not None and b is not None:
                    deltas.append(a - b)
            effects[name][metric] = {
                **describe(deltas),
                "win": sum(d > 0 for d in deltas), "tie": sum(d == 0 for d in deltas),
                "loss": sum(d < 0 for d in deltas),
            }
    integrity = {
        "text_controls_with_media": sum(r["condition"] == "text_only" and r["media_call_count"] > 0 for r in rows),
        "policy_calls_with_seed": sum(c["role"] == "policy" and "seed" in c["sampling"] for c in calls),
        "initial_message_mismatches": sum(s["first_messages_equal"] is False for s in scenes),
        "initial_sampling_mismatches": sum(s["first_sampling_equal"] is False for s in scenes),
        "completed_video_without_verified_media": sum(
            r["condition"] == "text_video" and r["status"] == "completed"
            and not r["successful_media_call_count"] for r in rows),
    }
    # Record probe call failures separately: they need not imply lack of model capability.
    probe_calls = []
    for path in sorted((directory / "capabilities").glob("*/*/*/*.json")):
        value = evidence.read(path)
        probe_calls.append({
            "model_id": path.relative_to(directory / "capabilities").parts[0],
            "path": str(path.relative_to(ROOT)), "status": value.get("status"),
            "error": value.get("error"), "wall_seconds": value.get("wall_seconds"),
        })
    checkpoint_status = evidence.read(directory.parent / "checkpoint_diagnostic/launch_status.json", {})
    checkpoint_results = evidence.read(directory.parent / "checkpoint_diagnostic/results.json", {})
    if checkpoint_results:
        checkpoint_budget = evidence.read(
            directory.parent / "checkpoint_diagnostic/request_budget.json", {})
        checkpoint_status = {
            **checkpoint_status,
            **{k: checkpoint_results[k] for k in ("status", "finished", "planned", "updated_at")},
            "api_requests": checkpoint_budget.get("request_count", checkpoint_results["api_requests"]),
            "note": "用户已明确授权。两次文字重复及一次媒体回应来自相同公开节点，不计作完整 T4 轨迹或评分。",
        }
    return {
        "format": "t4_expanded_api_audit_v1", "updated_at": now(), "run_id": RUN_ID,
        "process_alive": alive, "status": evidence.read(directory / "status.json", {}),
        "request_budget": evidence.read(directory / "request_budget.json", {}),
        "scenario_ids": sids, "model_names": {n: plan["providers"][n]["model"] for n in names},
        "capabilities": capabilities, "probe_calls": probe_calls,
        "checkpoint_diagnostic_status": checkpoint_status,
        "model_summary": {n: summarize_model(rows, n) for n in names},
        "paired_effects": effects, "integrity_checks": integrity,
        "episodes": rows, "scenes": scenes, "calls": calls, "events": events,
        "source_sha256": evidence.sources,
    }


def render(data):
    budget, status = data["request_budget"], data["status"]
    lines = [
        "# T4 扩展模型 API 补测",
        "",
        f"更新：{data['updated_at']}（北京时间）。独立补测进程"
        f"{'运行中' if data['process_alive'] else '已结束'}，状态 `{status.get('status', 'unknown')}`；"
        f"已记录 {status.get('finished', 0)}/96 个候选结果，"
        f"累计 API 请求 {budget.get('request_count', 0)}/{budget.get('limit', 2200)}。",
        "",
        "本轮通过 AutoDL 实测 8 个候选模型，在 002、014、019、024、026、031 六个既有问题场景上进行文字／多模态配对。"
        "这是针对结束时机缺陷的诊断样本，不能代表完整 GPT50 的总体能力。",
        "",
        "[逐模型场景 CSV](2026-10-20_t4_expanded_api_scenes.csv) · "
        "[逐条件 CSV](2026-10-20_t4_expanded_api_episodes.csv) · "
        "[调用 CSV](2026-10-20_t4_expanded_api_calls.csv) · "
        "[完整审计 JSON](2026-10-20_t4_expanded_api.json)",
        "",
        "**模型与实际媒体接收**",
        "",
        "| 模型 | 本次时序探测 | 媒体成功场景 / 6 | 视频评分完成 | 有效配对 | 视频条件失败 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for name, full in data["model_names"].items():
        c, s = data["capabilities"][name], data["model_summary"][name]
        transport = {"native_video": "原生视频 2/2", "video_frames": "视频抽帧 2/2"}.get(c.get("selected_transport"))
        label = transport or ("未通过" if c.get("probe_complete") else "探测中")
        lines.append(f"| {full} | {label} | {s['successful_media_call_scenarios']} | "
                     f"{s['scored_with_verified_media']} | {s['valid_pairs']} | "
                     f"{s['status_counts'].get('failed', 0)} |")
    lines += [
        "",
        "时序探测要求正确回答两组不同颜色顺序。媒体成功只表示含实际图片／视频块的请求返回非空输出，"
        "不等于理解情绪线索。视频抽帧条件没有音频；原生视频也尚未单独验证音频理解。",
        "",
    ]
    for name, capability in data["capabilities"].items():
        for transport in ("native_video", "video_frames"):
            for control in capability.get(transport, []):
                if not control["passed"]:
                    detail = control.get("error") or (
                        f"返回 {control.get('response')}，预期 {control.get('expected')}")
                    lines.append(f"- {data['model_names'][name]} 的 {transport} 未通过："
                                 f"{str(detail)[:450]}。")
    video_guarded = [r for r in data["episodes"] if r["condition"] == "text_video"
                     and r["media_completion_deferred_turn_ids"]]
    guard_delivered = [r for r in video_guarded if r["successful_media_call_count"]]
    lines += [
        "",
        f"首次媒体结束规则已在 {len(video_guarded)} 条视频轨迹中实际延后自然结束，"
        f"其中 {len(guard_delivered)} 条随后已有成功媒体调用。"
        "这验证回应机会是否被保留，不代表后续环境调用或评分一定成功。",
        "",
        "**多模态效果**",
        "",
        "仅计算同一批次、同一模型、同一场景的两条完整轨迹，且视频侧必须有成功媒体调用。"
        "下表为多模态减文字的核心四维均分差；缺失或失败不填零。恢复维度不适用时保持空值，完整五维统计见 JSON。",
        "",
        "| 模型 | 配对数 | 核心四维平均差 | 视频胜 / 平 / 负 |",
        "|---|---:|---:|---|",
    ]
    for name, full in data["model_names"].items():
        e = data["paired_effects"][name]["core_four_mean"]
        value = f"{e['mean']:+.4f}" if e["mean"] is not None else "暂无有效配对"
        lines.append(f"| {full} | {e['n']} | {value} | {e['win']} / {e['tie']} / {e['loss']} |")
    lines += [
        "",
        "单次随机轨迹可能在首次媒体出现前就分叉，因此这里衡量整条条件路径的效果。"
        "样本小且只使用 Claude 自动裁判，尚不能据此认定模型排名或稳定的多模态收益；"
        "当 Claude 本身为被测模型时也存在同模型裁判偏差。人工复核材料由每条完成轨迹自动导出。",
        "",
        "**六场景投递状态**",
        "",
        "| 场景 | " + " | ".join(data["model_names"]) + " |",
        "|---|" + "---|" * len(data["model_names"]),
    ]
    lookup = {(s["scenario_id"], s["model_id"]): s for s in data["scenes"]}
    for sid in data["scenario_ids"]:
        lines.append("| " + sid + " | " + " | ".join(
            lookup[(sid, n)]["video_display"] for n in data["model_names"]) + " |")
    lines += ["", "**未成功接收媒体的原因**", ""]
    reasons = Counter(r["no_media_reason"] for r in data["episodes"]
                      if r["condition"] == "text_video" and not r["successful_media_call_count"])
    for reason, count in reasons.items():
        lines.append(f"- {NO_MEDIA_REASONS[reason]}：{count}。")
    failed_probes = [p for p in data["probe_calls"] if p.get("error")]
    if failed_probes:
        lines += ["", "探针原始错误类别（包括之后成功回退的传输）：", ""]
        for p in failed_probes:
            relative = Path(p["path"]).relative_to("build")
            lines.append(f"- {p['model_id']}：`{str(p['error'])[:450].replace('`', '')}`"
                         f"；[调用记录](../../build/{relative})。")
    lines += [
        "",
        "**冻结设置与验证**",
        "",
        "- `first_event_response_v1`：首次真实媒体事件后若原本自然结束，则保留一次回应机会；"
        "两条件同规则，保持原状态、阈值和硬停止条件。",
        "- policy 请求统一省略 seed，temperature=0.6、top_p=0.9；"
        "环境和裁判采样沿用原设置。此项显式记录在配置中，旧结果不与本轮合并。",
        "- 环境状态及交互评估为 GPT-6 Astra，环境回应和终局裁判为 Claude Fable 5；"
        "被测模型仅负责 policy。最多 20 轮，4 并发，2200 次请求硬预算；"
        "每场景生成健康报告，诊断批次保留失败并继续，不按得分重抽轨迹。",
        "- [配置](../../configs/gpt50_experiment/t4_multimodal_experiment.expanded_api_20261020.json) · "
        "[计划](../../build/t4_expanded_api_20261020/run/plan.json) · "
        "[代码冻结清单](../../build/t4_expanded_api_20261020/runtime_manifest.json) · "
        "[模型目录快照](../../build/t4_expanded_api_20261020/model_catalog.json)",
        "",
        f"审计异常计数：`{json.dumps(data['integrity_checks'], ensure_ascii=False)}`。"
        "各项应为 0，非零需要先排查再解释成绩。",
        "",
        "本地刷新：`python scripts/report_t4_expanded_api.py`。后台报告进程每 30 秒刷新，实验退出后保存最终快照。",
        "",
    ]
    checkpoint = data["checkpoint_diagnostic_status"]
    if checkpoint:
        lines += [
            "**额外固定节点对照**", "",
            f"状态：`{checkpoint.get('status')}`；API 请求数 "
            f"{checkpoint.get('api_requests', '见独立请求记录')}，不计入上面 96 个候选结果。",
            checkpoint.get("note", ""),
            "[固定节点回应原文](2026-10-20_t4_checkpoint_media.md)。", "",
        ]
        if (PREFIX.parent / "2026-10-20_t4_checkpoint_findings.md").exists():
            lines += ["[固定节点最终核验与语义复核发现](2026-10-20_t4_checkpoint_findings.md)。", ""]
    return "\n".join(lines)


def publish():
    data = snapshot()
    PREFIX.parent.mkdir(parents=True, exist_ok=True)
    for key in ("scenes", "episodes", "calls", "events"):
        write_csv(PREFIX.with_name(PREFIX.name + "_" + key + ".csv"), data[key])
    save(PREFIX.with_suffix(".json"), data)
    text_path = PREFIX.with_suffix(".md")
    temp = text_path.with_suffix(".md.tmp")
    temp.write_text(render(data))
    temp.replace(text_path)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    while True:
        data = publish()
        print(json.dumps({k: data[k] for k in ("updated_at", "process_alive", "request_budget", "integrity_checks")},
                         ensure_ascii=False), flush=True)
        if not args.watch or not data["process_alive"]:
            break
        time.sleep(30)


if __name__ == "__main__":
    main()
