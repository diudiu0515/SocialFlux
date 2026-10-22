#!/usr/bin/env python3
"""Audit saved T4 media exposure without executing policies or changing runs."""

import argparse
from collections import Counter
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
RUN_IDS = (
    "t4_gpt41_paired_20261020",
    "t4_gpt39_continuation_20261020",
    "t4_gpt33_parallel_20261020",
    "t4_qwen4_autodl_20261020",
)
MODELS = ("gpt", "claude", "deepseek", "qwen")
METRICS = (
    "goal_achievement", "state_adaptation", "risk_management",
    "recovery", "relationship_outcome", "core_four_mean",
)
NO_MEDIA_REASONS = {
    "media_call_completed": "已成功调用媒体输入",
    "capability_probe_failed": "视觉能力探测未通过，未运行视频轨迹",
    "not_started": "尚未启动",
    "terminal_event_without_followup": "自然结束轮才触发，缺少后续模型调用",
    "media_call_failed": "已触发，但媒体请求失败",
    "media_call_pending": "媒体请求尚未完成",
    "prepared_without_call": "已组装媒体，未见对应请求",
    "triggered_without_call": "已保存触发，未见媒体调用",
    "failed_before_first_completed_turn": "第一轮完成前调用失败，未到触发环节",
    "unchanged_state_in_saved_turns": "已保存轮的状态未变化，未达到触发条件",
    "state_change_without_recorded_event": "存在状态变化但无事件，需核对阈值和冷却",
    "awaiting_first_completed_turn": "尚无完整轮，不能判定不触发",
    "not_selected": "未纳入本次实验",
}


def now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


class Evidence:
    def __init__(self, root):
        self.root = root
        self.sources = {}

    def read(self, path, default=None):
        path = Path(path)
        key = str(path.relative_to(self.root))
        if not path.exists():
            return default
        # Some live files are written in place. A malformed read must not become
        # a false zero in the report; fail the export if it remains unreadable.
        for _ in range(3):
            raw = path.read_bytes()
            try:
                value = json.loads(raw)
                break
            except json.JSONDecodeError:
                pass
        else:
            raise ValueError(f"Cannot read live JSON safely: {key}")
        self.sources[key] = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "mtime_ns": path.stat().st_mtime_ns,
        }
        return value


def media_blocks(messages):
    return [
        block
        for message in messages
        if isinstance(message.get("content"), list)
        for block in message["content"]
        if isinstance(block, dict)
        and block.get("type") in ("image_url", "image", "video_url", "video")
    ]


def error_category(error):
    value = error.lower()
    if not value:
        return ""
    if "unknown parameter" in value and "seed" in value:
        return "unsupported_seed_parameter"
    if "json/schema" in value:
        return "judge_schema" if "judgment" in value else "environment_schema"
    if "timed out" in value or "timeout" in value:
        return "timeout"
    if "stream error" in value:
        return "upstream_stream_error"
    if "truncated" in value:
        return "truncated_response"
    if "http 502" in value:
        return "http_502"
    if "unterminated" in value or "expecting" in value:
        return "json_parse"
    if "lacks assistant content" in value:
        return "empty_response"
    if "unsupported consequential claim" in value:
        return "unsupported_claim"
    return "other"


def no_media_reason(row):
    if row["successful_media_call_count"]:
        return "media_call_completed"
    if row["status"] == "unsupported_video_input":
        return "capability_probe_failed"
    if row["status"] == "not_started":
        return "not_started"
    if row["media_call_count"]:
        return "media_call_pending" if row["pending_media_call_count"] else "media_call_failed"
    if row["prepared_media_count"]:
        return "prepared_without_call"
    if row["recorded_trigger_count"]:
        return ("terminal_event_without_followup" if row["status"] == "completed_without_video_exposure"
                and row["ending_reason"] == "natural_completion" else "triggered_without_call")
    if row["completed_turns"] == 0:
        return "failed_before_first_completed_turn" if row["status"] == "failed" else "awaiting_first_completed_turn"
    return ("state_change_without_recorded_event" if row["state_changed_turn_ids"]
            else "unchanged_state_in_saved_turns")


def process_alive(directory):
    for path in (directory / "process.json", directory.parent / "process.json"):
        if not path.exists():
            continue
        pid = json.loads(path.read_text()).get("pid")
        if not isinstance(pid, int):
            continue
        try:
            command = Path(f"/proc/{pid}/cmdline").read_bytes()
            state = Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1].split()[0]
            return directory.parent.name.encode() in command and state != "Z"
        except (OSError, IndexError):
            pass
    return False


def read_episode(evidence, run_id, sid, model, condition, plan, capability, alive):
    directory = evidence.root / "build" / run_id / "run" / "episodes" / sid / model / condition
    result = evidence.read(directory / "result.json", {})
    calls = []
    for path in sorted((directory / "calls").glob("*/*.json")):
        value = evidence.read(path)
        blocks = media_blocks(value.get("messages", []))
        calls.append({
            "run_id": run_id, "scenario_id": sid, "model_id": model,
            "condition": condition, "role": path.parent.name,
            "call_index": int(path.stem), "status": value.get("status", "unknown"),
            "has_media": bool(blocks), "media_block_count": len(blocks),
            "media_types": sorted({block["type"] for block in blocks}),
            "messages_sha256": hashlib.sha256(json.dumps(
                value.get("messages", []), sort_keys=True, ensure_ascii=False
            ).encode()).hexdigest(),
            "sampling": value.get("sampling", {}),
            "nonempty_output": bool(str(value.get("raw_output", "")).strip()),
            "wall_seconds": value.get("wall_seconds"),
            "error_category": error_category(value.get("error", "")),
            "error": value.get("error", "")[:800],
            "source_path": str(path.relative_to(evidence.root)),
        })
    deliveries = evidence.read(directory / "video_deliveries.json", [])
    trajectory = {}
    trajectory_path = ""
    for filename in ("trajectory.json", "partial_trajectory.json", "checkpoint.json"):
        path = directory / filename
        if path.exists():
            trajectory = evidence.read(path)
            trajectory_path = str(path.relative_to(evidence.root))
            break
    turns = trajectory.get("turns", [])
    events = []
    for turn in turns:
        for event in turn.get("trigger_events", []):
            if event.get("media_type") != "video":
                continue
            events.append({
                "run_id": run_id, "scenario_id": sid, "model_id": model,
                "condition": condition, "turn_id": turn["turn_id"],
                **{key: event.get(key) for key in (
                    "media_event_id", "trigger_id", "event_family",
                    "source_state_family", "source_state_variable", "source_direction",
                    "media_asset_id", "video_api_status", "duration_seconds",
                )},
                "source_path": trajectory_path,
            })
    policy_calls = [call for call in calls if call["role"] == "policy"]
    media_calls = [call for call in policy_calls if call["has_media"]]
    successful_media = [
        call for call in media_calls
        if call["status"] == "completed" and call["nonempty_output"]
    ]
    if result:
        status = result.get("status", "unknown")
    elif calls or trajectory:
        status = "running" if alive else "interrupted_no_result"
    else:
        status = "not_started"
    error = result.get("error", "")
    failed_calls = [call for call in calls if call["status"] == "failed"]
    terminal_roles = sorted({
        call["role"] for call in failed_calls
        if error and call["error"] == error[:800]
    })
    if not terminal_roles:
        if "judgment" in error:
            terminal_roles = ["judge"]
        elif "structured environment response" in error or "unsupported consequential claim" in error:
            terminal_roles = ["response"]
    active_roles = sorted({call["role"] for call in calls if call["status"] == "started"})
    if not policy_calls:
        exposure = "no_policy_call"
    elif successful_media:
        exposure = "media_call_completed"
    elif media_calls:
        exposure = "media_call_without_success"
    elif deliveries:
        exposure = "media_prepared_without_audited_call"
    elif events:
        exposure = "triggered_without_media_call"
    else:
        exposure = "no_recorded_trigger_or_media_call"
    if condition == "text_only":
        exposure = "text_control" if not media_calls else "unexpected_media_in_text_control"
    row = {
        "run_id": run_id, "scenario_id": sid, "model_id": model,
        "model_name": plan["providers"][model]["model"], "condition": condition,
        "status": status, "transport": capability.get("selected_transport") if condition == "text_video" else None,
        "policy_started": bool(policy_calls), "trajectory_file": trajectory_path,
        "completed_turns": len(turns), "ending_reason": (trajectory.get("ending") or {}).get("reason"),
        "state_changed_turn_ids": [
            turn["turn_id"] for turn in turns if turn.get("state_before") != turn.get("state_after")
        ],
        "media_completion_deferred_turn_ids": [
            turn["turn_id"] for turn in turns
            if turn.get("media_completion_guard", {}).get("natural_completion_deferred")
        ],
        "environment_models": {
            key: trajectory.get("environment_provenance", {}).get(key, {}).get("model")
            for key in ("state_appraisal_provider", "interaction_appraisal_provider", "response_provider")
        },
        "environment_route_slots": result.get("environment_route_slots", {}),
        "recorded_trigger_count": len(events),
        "trigger_turn_ids": [event["turn_id"] for event in events],
        "event_families": sorted({event["event_family"] for event in events if event["event_family"]}),
        "prepared_media_count": len(deliveries),
        "prepared_asset_ids": [delivery["asset_id"] for delivery in deliveries],
        "result_video_delivery_count": result.get("video_delivery_count"),
        "policy_call_count": len(policy_calls), "media_call_count": len(media_calls),
        "successful_media_call_count": len(successful_media),
        "failed_media_call_count": sum(call["status"] == "failed" for call in media_calls),
        "pending_media_call_count": sum(call["status"] == "started" for call in media_calls),
        "first_media_call_index": media_calls[0]["call_index"] if media_calls else None,
        "first_successful_media_call_index": successful_media[0]["call_index"] if successful_media else None,
        "completed_turns_with_input_media": [
            turn["turn_id"] for turn in turns if turn.get("observation", {}).get("media")
        ],
        "exposure_status": exposure,
        "scored_with_verified_media": condition == "text_video" and status == "completed" and bool(successful_media),
        "api_calls": len(calls),
        "api_status_counts": dict(Counter(call["status"] for call in calls)),
        "api_role_counts": dict(Counter(call["role"] for call in calls)),
        "failed_call_role_counts": dict(Counter(call["role"] for call in failed_calls)),
        "active_roles": active_roles, "terminal_failure_roles": terminal_roles,
        "error_category": error_category(error), "error": error[:800],
        "scores": {key: result.get("scores", {}).get(key) for key in METRICS},
        "result_path": str((directory / "result.json").relative_to(evidence.root)) if result else "",
        "valid_pair": False,
        "first_policy_call": {
            key: policy_calls[0][key] for key in ("call_index", "messages_sha256", "sampling", "has_media")
        } if policy_calls else None,
    }
    row["no_media_reason"] = no_media_reason(row) if condition == "text_video" else "text_control"
    return row, calls, events


def summarize_model(rows, model):
    video = [row for row in rows if row["model_id"] == model and row["condition"] == "text_video"]
    return {
        "selected_scenarios": len(video),
        "policy_started": sum(row["policy_started"] for row in video),
        "recorded_trigger_scenarios": sum(row["recorded_trigger_count"] > 0 for row in video),
        "prepared_media_scenarios": sum(row["prepared_media_count"] > 0 for row in video),
        "media_call_scenarios": sum(row["media_call_count"] > 0 for row in video),
        "successful_media_call_scenarios": sum(row["successful_media_call_count"] > 0 for row in video),
        "scored_with_verified_media": sum(row["scored_with_verified_media"] for row in video),
        "valid_pairs": sum(row["valid_pair"] for row in video),
        "status_counts": dict(Counter(row["status"] for row in video)),
        "failed_after_successful_media_call": sum(
            row["status"] == "failed" and row["successful_media_call_count"] > 0 for row in video
        ),
        "completed_without_media_call": [
            row["scenario_id"] for row in video if row["status"] == "completed_without_video_exposure"
        ],
    }


def cell(row):
    if row is None:
        return "未纳入"
    if row["status"] == "unsupported_video_input":
        return "探测未过"
    if row["status"] == "not_started":
        return "待启动"
    n = row["successful_media_call_count"]
    if row["scored_with_verified_media"]:
        return f"评分✓ 媒{n}" + (" 配对✓" if row["valid_pair"] else "")
    if row["status"] == "completed_without_video_exposure":
        return "完成无媒体"
    prefix = {"failed": "失败", "running": "运行", "interrupted_no_result": "中断"}.get(row["status"], row["status"])
    if n:
        return f"{prefix} 媒{n}"
    if row["media_call_count"]:
        return f"{prefix} 媒请求未成功"
    if row["recorded_trigger_count"]:
        return f"{prefix} 触发未投递"
    return f"{prefix} 未见触发"


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
                for key, value in row.items()
            })


def report_text(data, prefix):
    rows, summaries = data["episodes"], data["model_summary"]
    lookup = {(r["scenario_id"], r["model_id"], r["condition"]): r for r in rows}
    lines = [
        "# T4 逐场景多模态触发与投递核验",
        "",
        "并非每个模型、每个场景都实际接收到多模态输入。文字条件本来就不发送媒体；视频条件还可能在探测、触发、请求或后续环境调用阶段中断。",
        f"本次读取窗口为 {data['scan_started_at']} 至 {data['scan_finished_at']}（北京时间）；主批次仍可能继续变化。下列统计是保存下来的检查快照。",
        "",
        f"[逐场景模型表]({prefix.name}_scenes.csv) · [逐条件明细]({prefix.name}_episodes.csv) · "
        f"[调用状态]({prefix.name}_calls.csv) · [触发事件]({prefix.name}_events.csv) · "
        f"[完整汇总及来源哈希]({prefix.name}.json)",
        "",
        "统计范围为今天三个连续主批次去重后的 41 场景，以及 Qwen 的 001–004 四场景补测。"
        "全表列出 GPT50 的 50 个场景；未纳入实验的场景明确标出。"
        "旧 run 的 198 条移交记录不计为实验测量；两条件必须在同一 run、同一模型、同一场景内成功，才构成配对。",
        "",
        "**实验设置**",
        "",
        "冻结 policy prompt 为 `task_t4_action_v21`；最多 20 轮，允许第 1 轮自然结束。"
        "各场景沿用原 source_index 决定 seed（8600 + source_index），policy temperature=0.6、top_p=0.9；"
        "逐次实际 sampling 保存在调用表。相同 seed 不能保证供应商返回确定性的输出。",
        "保存轨迹中的状态及交互评估模型为 GPT-6 Astra，环境回应模型及原终局裁判为 Claude Fable 5；"
        "这些角色与被测 policy 模型分开记录。新旧批次的凭据槽位和并发安排有差异，成绩按批次列出。",
        "",
        "**触发与成功的定义**",
        "",
        "- 触发：已保存的完整轮中出现视频 `trigger_events`。这只证明环境产生了事件，未落盘的失败轮不据此判定没有触发。",
        "- 准备媒体：`video_deliveries.json` 已写入媒体资产。该文件在调用前写入，不能单独证明请求成功。",
        "- 媒体调用成功：policy 调用审计中确实有图片或视频块，状态为 `completed`，并返回非空文本。它证明带媒体请求完成，不证明模型理解或使用了视频。",
        "- 视频轨迹评分完成：整条轨迹及终局评分完成，且至少一次媒体调用成功。",
        "- 有效配对：上述视频条件和对应文字条件均完成；失败不填零，未投递媒体的完成轨迹不算多模态成功。",
        "",
        "**视频条件覆盖**",
        "",
        "| 模型 | 纳入场景 | policy已开始 | 保存了触发 | 媒体调用成功 | 视频评分完成 | 有效配对 | 收到媒体后失败 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model in MODELS:
        value = summaries[model]
        lines.append("| " + " | ".join(str(x) for x in [data["model_names"][model]] + [
            value[k] for k in ("selected_scenarios", "policy_started", "recorded_trigger_scenarios",
                              "successful_media_call_scenarios", "scored_with_verified_media",
                              "valid_pairs", "failed_after_successful_media_call")
        ]) + " |")
    lines += ["", "以上各列是不同阶段的计数；触发与投递在失败轨迹上也可能已经发生，不能只统计成功 result。", "",
              "| 模型 | 视频条件状态分布 |", "|---|---|"]
    for model in MODELS:
        lines.append(f"| {model} | {json.dumps(summaries[model]['status_counts'], ensure_ascii=False)} |")
    missing = [row for row in rows if row["condition"] == "text_video"
               and not row["successful_media_call_count"]]
    lines += ["", "**未获得成功媒体输入的原因**", "",
              "| 原因 | 条件数 |", "|---|---:|"]
    for reason, count in Counter(row["no_media_reason"] for row in missing).items():
        lines.append(f"| {NO_MEDIA_REASONS[reason]} | {count} |")
    lines += ["", "各场景的具体原因、错误角色和错误文本见 CSV 的 `no_media_reason`、"
              "`terminal_failure_roles`、`error`。未启动及探测未过与状态阈值问题分别记录。"
              "首次事件后自然结束的修复见 [修复与本地验证](2026-10-20_t4_media_completion_fix.md)。"]
    lines += [
        "",
        "**输入方式与未覆盖范围**",
        "",
        "GPT 和 Claude 使用每段视频的 4 个带时间戳的图像帧（0.25、1.25、2.25、3.25 秒），不含音频。"
        "Qwen 使用完整 MP4 的原生视频输入；接口通过两组颜色顺序控制，但不能据此宣称音频理解已验证。"
        "DeepSeek 在当前路由的原生视频和帧输入探测均未通过，因此没有运行视频轨迹；探测中的截断错误不能证明该模型原则上不支持视觉。",
        "",
        "视频事件按 `online_multimodal_v2` 的状态阈值与冷却规则触发，并在后续 policy 观察中输入。"
        "角色行动和环境反馈不同，会使同一场景下各模型、两种条件的触发时机和事件种类不同。"
        "最后一轮产生事件后若自然结束，就没有下一次 policy 调用来接收该视频。",
        "",
        f"首个 policy 请求核验：两条件均有调用记录的 {data['initial_request_comparison']['both_present']} 组中，"
        f"messages 相同 {data['initial_request_comparison']['messages_equal']} 组，"
        f"sampling 相同 {data['initial_request_comparison']['sampling_equal']} 组；"
        f"首请求包含媒体的条件数为 {data['initial_request_comparison']['first_calls_with_media']}。"
        "因此首次媒体输入之前的输出差异不能直接归因于观看了视频。",
        "",
        f"三个主模型未纳入的场景：{', '.join(data['excluded_main_scenarios'])}。这是完整资产可用子集实验，不是 50 场景全覆盖；Qwen 只纳入 001–004。",
        "",
        "**所有场景的视频条件**",
        "",
        "“媒N”表示 N 次带媒体 policy 请求完成并返回文本；不是 N 段独立视频，也不是理解正确率。"
        "“评分✓”表示视频轨迹及终局评分完成，“配对✓”额外要求文字条件完成。"
        "未见触发只描述当前保存证据，不把运行中或失败前未保存的状态当作永远不会触发。",
        "",
        "| 场景 | GPT | Claude | DeepSeek | Qwen |",
        "|---|---|---|---|---|",
    ]
    for sid in data["all_scenario_ids"]:
        lines.append("| " + sid + " | " + " | ".join(cell(lookup.get((sid, model, "text_video"))) for model in MODELS) + " |")
    lines += ["", "**完成但未接收媒体的轨迹**", "",
              "| 场景 | 模型 | 完成轮数 | 保存的触发数 | 触发轮 | 结束原因 |",
              "|---|---|---:|---:|---|---|"]
    for row in rows:
        if row["status"] == "completed_without_video_exposure":
            lines.append(f"| {row['scenario_id']} | {row['model_id']} | {row['completed_turns']} | "
                         f"{row['recorded_trigger_count']} | {','.join(row['trigger_turn_ids']) or '无'} | {row['ending_reason']} |")
    no_media = [r for r in rows if r["status"] == "completed_without_video_exposure"]
    terminal_only = [r for r in no_media if r["completed_turns"] == 1 and r["trigger_turn_ids"] == ["t1"]
                     and r["ending_reason"] == "natural_completion"]
    lines += ["", f"当前 {len(no_media)} 条完成无媒体轨迹中，{len(terminal_only)} 条在第 1 轮产生事件后立即自然结束，"
              "没有下一次 policy 调用。这里的缺口发生在触发与后续观察之间，不能简单称为没有触发。"]
    lines += ["", "**失败分布与运行状态**", "",
              "| 批次 | 保存状态 | 进程存活 | 结果终态数 | 计划数 | API 请求数 |",
              "|---|---|---|---:|---:|---:|"]
    for run, value in data["runs"].items():
        status = value["status"]
        lines.append(f"| {run} | {status.get('status')} | {value['process_alive']} | "
                     f"{status.get('finished')} | {status.get('planned')} | {status.get('api_requests')} |")
    lines += ["", "原 39 场景 run 的终态数包含移交记录；此处保留其原始运行状态，模型覆盖表已去重。", "",
              "| 终止错误类别 | 轨迹数 |", "|---|---:|"]
    for key, value in data["failure_categories"].items():
        lines.append(f"| {key} | {value} |")
    lines += ["", "调用明细保留失败发生角色、请求序号、耗时及错误类别。`terminal_failure_roles` 只在原错误可匹配时确定；"
              "其他失败调用可能已被后续重试恢复，不能直接当成轨迹终止原因。", "",
              "**同批次内有效配对的成绩**", "",
              "每维 0–10。下表只汇报同 run 配对的“视频−文字”均值，不跨 run 拼接成功单边，不将恢复维度的 N/A 填零。"
              "四维均值排除经常不适用的恢复维度；样本仍小且未人工校准。", "",
              "| 批次 | 模型 | 配对数 | 目标 | 适应 | 风险 | 关系 | 四维均值 | 恢复差值及样本数 |",
              "|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for item in data["paired_scores"]:
        metrics = item["metrics"]
        def fmt(key):
            value = metrics[key]["mean"]
            return "N/A" if value is None else f"{value:+.2f}"
        lines.append(f"| {item['run_id']} | {item['model_id']} | {item['pairs']} | " +
                     " | ".join(fmt(key) for key in ("goal_achievement", "state_adaptation", "risk_management",
                                                     "relationship_outcome", "core_four_mean")) +
                     f" | {fmt('recovery')} (n={metrics['recovery']['n']}) |")
    lines += [
        "",
        "**补测和裁判敏感性**",
        "",
        "Qwen 被测策略与 Qwen 裁判是不同实验：前者是四场景新轨迹，后者与 DeepSeek 一起对已冻结的八组 Claude 轨迹复评。"
        "独立复评 32/32 已完成；两位裁判没有复现 GPT50_010 视频轨迹原来的全零评分。"
        "复评仍有部分维度负差值，不能把裁判分歧解释成视觉条件必然有益或无害。"
        "详见 [Claude 诊断与补测](2026-10-20_t4_claude_video_diagnosis.txt)及"
        " [三位裁判五维对照](../../build/t4_claude_rejudge_autodl_20261020/five_dimension_comparison.csv)。",
        "",
        "| Qwen 场景 | 保存触发数 | 带视频成功调用数 | 首次成功媒体请求序号 | 终止角色 | 终止类别 |",
        "|---|---:|---:|---:|---|---|",
    ]
    for row in rows:
        if row["model_id"] == "qwen" and row["condition"] == "text_video":
            lines.append(f"| {row['scenario_id']} | {row['recorded_trigger_count']} | "
                         f"{row['successful_media_call_count']} | {row['first_successful_media_call_index'] or '无'} | "
                         f"{','.join(row['terminal_failure_roles']) or '未确定'} | {row['error_category']} |")
    lines += [
        "",
        "Qwen 001、002、004 的带原生视频请求均已成功返回，随后环境 state 调用失败；"
        "003 没有完整第一轮或触发记录，首次环境 state 调用已超时。四条视频轨迹都不能计入完成评分或有效配对。",
        "",
        "**与离线任务的关系**",
        "",
        "T1–T3 的新版 300 题及 270 个文字／视频配对是题库与输入条件构建，不能计入这里的在线多模态模型测试。"
        "T2 仍有 45 场景的回放缺口，全部题目的人工真值待确认。"
        "详见 [离线题库记录](2026-10-20_scenarios_v2.md)。",
        "",
        "**继续分析时应保留的信息**",
        "",
        "- 分别报告触发覆盖、媒体请求成功率、整条轨迹成功率和有效配对率；同时保留失败分母及事件发生后的中断。",
        "- 当前完成无媒体轨迹的终局触发已单列；后续设计若要保证视觉暴露，需要显式设计触发后的观察机会，并作为新协议单独实验。",
        "- 模型间比较注明帧输入与原生视频的差别；同场景也可能走不同互动路径，当前结果衡量整条条件路径的差异。",
        "- 环境超时、结构化输出、seed 参数拒绝和裁判错误分别记录。修复或重新实验应另存版本，保留现有冻结运行。",
        "",
        "**刷新与复核**",
        "",
        f"`python scripts/audit_t4_multimodal_exposure.py --output-prefix {prefix.relative_to(ROOT)}`",
        "",
        "脚本只读取本地产物，更新本汇总及 CSV，不调用模型，不重启实验。"
        "JSON 保存每个读取源文件的 SHA256、字节数和修改时间；各行保留原始证据路径。"
        "扫描不是跨文件原子快照，因此记录开始与结束时间；解析失败会报错，不静默填零。",
        "",
    ]
    return "\n".join(lines)


def audit(root=ROOT):
    evidence = Evidence(root)
    started = now()
    runs, plans, capabilities = {}, {}, {}
    for run_id in RUN_IDS:
        directory = root / "build" / run_id / "run"
        plans[run_id] = evidence.read(directory / "plan.json")
        capabilities[run_id] = evidence.read(directory / "capabilities.json")
        runs[run_id] = {
            "status": {k: v for k, v in evidence.read(directory / "status.json").items() if k != "models"},
            "process_alive": process_alive(directory),
            "cohort_scenarios": plans[run_id]["config"]["scenario_ids"],
            "methods": {
                key: plans[run_id].get(key) for key in
                ("policy_prompt", "max_turns", "minimum_natural_turns", "primary_comparison")
            },
            "judge_model": plans[run_id]["providers"][plans[run_id]["config"]["judge"]]["model"],
            "capabilities": capabilities[run_id],
        }
    first, continuation, parallel, qwen = RUN_IDS
    cohorts = {run: set(plan["config"]["scenario_ids"]) for run, plan in plans.items()}
    assert cohorts[parallel] <= cohorts[continuation] <= cohorts[first]
    delegation = evidence.read(root / "build" / continuation / "run/delegation.json")
    assert set(delegation["scenario_ids"]) == cohorts[parallel]
    owners = {
        first: cohorts[first] - cohorts[continuation],
        continuation: cohorts[continuation] - cohorts[parallel],
        parallel: cohorts[parallel], qwen: cohorts[qwen],
    }
    rows, calls, events = [], [], []
    for run_id in RUN_IDS:
        plan = plans[run_id]
        for sid in sorted(owners[run_id]):
            for model in (("qwen",) if run_id == qwen else MODELS[:3]):
                for condition in ("text_only", "text_video"):
                    row, episode_calls, episode_events = read_episode(
                        evidence, run_id, sid, model, condition, plan,
                        capabilities[run_id][model], runs[run_id]["process_alive"],
                    )
                    rows.append(row)
                    calls.extend(episode_calls)
                    events.extend(episode_events)
    by_key = {(r["run_id"], r["scenario_id"], r["model_id"], r["condition"]): r for r in rows}
    assert len(by_key) == len(rows)
    for row in rows:
        if row["condition"] == "text_video":
            text = by_key[(row["run_id"], row["scenario_id"], row["model_id"], "text_only")]
            row["valid_pair"] = bool(row["scored_with_verified_media"] and text["status"] == "completed")
            text["valid_pair"] = row["valid_pair"]
    integrity = {
        "text_controls_with_media_calls": sum(r["condition"] == "text_only" and r["media_call_count"] > 0 for r in rows),
        "completed_video_without_successful_media_call": sum(
            r["condition"] == "text_video" and r["status"] == "completed" and not r["successful_media_call_count"] for r in rows),
        "completed_without_exposure_but_media_call_succeeded": sum(
            r["status"] == "completed_without_video_exposure" and r["successful_media_call_count"] > 0 for r in rows),
        "result_delivery_count_mismatches": sum(
            r["result_video_delivery_count"] is not None and r["result_video_delivery_count"] != r["prepared_media_count"]
            for r in rows),
    }
    if any(integrity.values()):
        raise ValueError(f"Evidence inconsistency requires review: {integrity}")
    paired = []
    for run_id in RUN_IDS:
        for model in MODELS:
            video = [r for r in rows if r["run_id"] == run_id and r["model_id"] == model
                     and r["condition"] == "text_video" and r["valid_pair"]]
            if not video:
                continue
            metrics = {}
            for metric in METRICS:
                deltas = []
                for row in video:
                    text = by_key[(run_id, row["scenario_id"], model, "text_only")]
                    a, b = row["scores"][metric], text["scores"][metric]
                    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                        deltas.append(a - b)
                metrics[metric] = {"n": len(deltas), "mean": round(mean(deltas), 4) if deltas else None}
            paired.append({"run_id": run_id, "model_id": model, "pairs": len(video), "metrics": metrics})
    names = {model: plans[qwen if model == "qwen" else first]["providers"][model]["model"] for model in MODELS}
    all_sids = [f"GPT50_{i:03d}" for i in range(1, 51)]
    scene_rows = []
    initial_comparison = {"both_present": 0, "messages_equal": 0, "sampling_equal": 0,
                          "first_calls_with_media": sum(
                              bool(r["first_policy_call"] and r["first_policy_call"]["has_media"]) for r in rows)}
    lookup = {(r["scenario_id"], r["model_id"], r["condition"]): r for r in rows}
    for sid in all_sids:
        for model in MODELS:
            video = lookup.get((sid, model, "text_video"))
            text = lookup.get((sid, model, "text_only"))
            first_video = video["first_policy_call"] if video else None
            first_text = text["first_policy_call"] if text else None
            messages_equal = sampling_equal = None
            if first_video and first_text:
                initial_comparison["both_present"] += 1
                messages_equal = first_video["messages_sha256"] == first_text["messages_sha256"]
                sampling_equal = first_video["sampling"] == first_text["sampling"]
                initial_comparison["messages_equal"] += messages_equal
                initial_comparison["sampling_equal"] += sampling_equal
            scene_rows.append({
                "scenario_id": sid, "model_id": model, "model_name": names[model],
                "selected": video is not None, "run_id": video["run_id"] if video else "",
                "text_status": text["status"] if text else "not_selected",
                "video_status": video["status"] if video else "not_selected",
                "display": cell(video),
                "first_request_messages_equal": messages_equal,
                "first_request_sampling_equal": sampling_equal,
                "no_media_reason": video["no_media_reason"] if video else "not_selected",
                "no_media_reason_zh": NO_MEDIA_REASONS[video["no_media_reason"] if video else "not_selected"],
                **{k: video[k] if video else None for k in (
                    "transport", "completed_turns", "recorded_trigger_count", "trigger_turn_ids",
                    "event_families", "prepared_media_count", "media_call_count",
                    "successful_media_call_count", "first_successful_media_call_index",
                    "scored_with_verified_media", "valid_pair", "exposure_status",
                    "terminal_failure_roles", "error_category", "error",
                )},
            })
    return {
        "format": "t4_multimodal_exposure_audit_v1",
        "scan_started_at": started, "scan_finished_at": now(),
        "all_scenario_ids": all_sids, "excluded_main_scenarios": sorted(set(all_sids) - cohorts[first]),
        "runs": runs, "model_names": names,
        "model_summary": {model: summarize_model(rows, model) for model in MODELS},
        "failure_categories": dict(Counter(r["error_category"] for r in rows if r["status"] == "failed")),
        "integrity_checks": integrity, "paired_scores": paired,
        "initial_request_comparison": initial_comparison,
        "no_media_reason_definitions": NO_MEDIA_REASONS,
        "episodes": rows, "scenes": scene_rows, "calls": calls, "events": events,
        "sources": evidence.sources,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-prefix", type=Path,
                        default=Path("reports/experiments/2026-10-20_t4_multimodal_exposure"))
    args = parser.parse_args()
    prefix = args.output_prefix.resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    data = audit()
    for key in ("episodes", "scenes", "calls", "events"):
        write_csv(prefix.with_name(prefix.name + f"_{key}.csv"), data[key])
    prefix.with_suffix(".json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    prefix.with_suffix(".md").write_text(report_text(data, prefix))
    print(json.dumps({key: data[key] for key in ("scan_finished_at", "model_summary", "integrity_checks")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
