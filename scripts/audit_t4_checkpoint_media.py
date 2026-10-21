#!/usr/bin/env python3
"""Audit completed checkpoint calls and publish findings without further APIs."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.t4_batch import digest, save
from scripts.audit_t4_multimodal_exposure import Evidence, media_blocks, now, write_csv

DIRECTORY = ROOT / "build/t4_expanded_api_20261020/checkpoint_diagnostic"
PREFIX = ROOT / "reports/experiments/2026-10-20_t4_checkpoint_findings"


def text_projection(messages):
    return [{
        "role": m["role"],
        "content": m["content"] if isinstance(m["content"], str) else
        "".join(b["text"] for b in m["content"] if b.get("type") == "text"),
    } for m in messages]


def main():
    evidence = Evidence(ROOT)
    data = evidence.read(DIRECTORY / "results.json")
    if data["status"] != "completed" or data["finished"] != data["planned"]:
        raise ValueError("wait for the bounded diagnostic to finish")
    plan = evidence.read(DIRECTORY / "plan.json")
    budget = evidence.read(DIRECTORY / "request_budget.json")
    authorization = evidence.read(DIRECTORY / "authorization.json")
    rows, flags, groups = [], [], {}
    for result in data["results"]:
        sid, name, variant = (result[k] for k in ("scenario_id", "model_id", "variant"))
        folder = DIRECTORY / "responses" / sid / name / variant
        paths = list((folder / "calls").glob("*.json"))
        assert len(paths) == 1, "first-pass diagnostic requires one call per item"
        call = evidence.read(paths[0])
        message_hash = digest(text_projection(call["messages"]))
        prepared = evidence.read(folder / "input.json")
        assert message_hash == prepared["text_sha256"]
        assert call["sampling"] == plan["sampling"]
        groups.setdefault((sid, name), []).append(message_hash)
        blocks = media_blocks(call["messages"])
        assert bool(blocks) == (variant == "video")
        expected_blocks = 4 if plan["models"][name]["transport"] == "video_frames" else 1
        assert variant != "video" or len(blocks) == expected_blocks
        raw = call.get("raw_output")
        received = call["status"] == "completed" and isinstance(raw, str) and bool(raw.strip())
        if result["status"] == "response_received":
            assert received and raw == result["response"]
        # Record this observed anomaly as an agent review, not a human annotation
        # or a general role-quality classifier.
        flag = ""
        if sid == "GPT50_024" and name == "claude" and variant == "video" and (
            isinstance(raw, str) and "I'm Kiro" in raw and "not able to roleplay" in raw
        ):
            flag = "explicit_role_refusal_and_developer_assistant_response"
            flags.append({
                "scenario_id": sid, "model_id": name, "variant": variant,
                "flag": flag, "review_type": "agent_review_not_human_validation",
                "evidence_quote": "I'm Kiro, an AI development environment.",
                "response_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                "local_action_validation": result.get("local_action_validation"),
                "interpretation": "Off-role response; self-identification does not establish the actual backend model.",
            })
        if sid == "GPT50_024" and name == "deepseek_flash" and variant == "video" and (
            isinstance(raw, str) and "旁白里那句“就在那天”" in raw
            and "就在那天" not in json.dumps(call["messages"], ensure_ascii=False)
        ):
            flag = "unverified_concrete_script_quote"
            flags.append({
                "scenario_id": sid, "model_id": name, "variant": variant,
                "flag": flag, "review_type": "agent_review_not_human_validation",
                "evidence_quote": "旁白里那句“就在那天”也得去掉",
                "response_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                "local_action_validation": result.get("local_action_validation"),
                "interpretation": "The supplied text contains no such narration line; image-only frames provide no spoken narration. Do not treat the invented concrete quote as an established scenario fact.",
            })
        rows.append({
            "scenario_id": sid, "model_id": name, "model_name": plan["models"][name]["model"],
            "variant": variant, "call_status": call["status"], "nonempty_response_received": received,
            "media_block_count": len(blocks), "media_types": sorted({b["type"] for b in blocks}),
            "text_sha256": message_hash, "sampling": call["sampling"],
            "wall_seconds": call.get("wall_seconds"), "error": call.get("error", ""),
            "local_action_validation": result.get("local_action_validation"),
            "agent_review_flag": flag, "response": result.get("response"),
            "call_path": str(paths[0].relative_to(ROOT)),
        })
    assert len(rows) == len({(r["scenario_id"], r["model_id"], r["variant"]) for r in rows}) == 36
    assert budget["request_count"] == 36 and budget["limit"] == 36
    assert all(len(v) == 3 and len(set(v)) == 1 for v in groups.values())
    for source in plan["sources"].values():
        assert hashlib.sha256((ROOT / source["path"]).read_bytes()).hexdigest() == source["sha256"]
    assert hashlib.sha256((ROOT / "scripts/run_t4_checkpoint_media_diagnostic.py").read_bytes()).hexdigest() == plan["script_sha256"]
    main_directory = DIRECTORY.parent / "run"
    for name, expected in (("gpt", 10), ("qwen", 7)):
        scored = evidence.read(main_directory / "episodes/GPT50_002" / name / "text_only/result.json")
        assert scored["scores"]["goal_achievement"] == expected
    assets = evidence.read(main_directory / "preregistration.json")["assets"]
    visual_asset = assets["GPT50_024:online_nonverbal_v1:activated_tension"]
    for frame in visual_asset["frames"]:
        assert hashlib.sha256(Path(frame["path"]).read_bytes()).hexdigest() == frame["sha256"]
    models = {}
    for name in plan["models"]:
        selected = [r for r in rows if r["model_id"] == name]
        models[name] = {
            "model": plan["models"][name]["model"],
            "transport": plan["models"][name]["transport"],
            "api_responses": sum(r["nonempty_response_received"] for r in selected),
            "successful_media_responses": sum(r["nonempty_response_received"] and r["variant"] == "video" for r in selected),
            "agent_review_flags": sum(bool(r["agent_review_flag"]) for r in selected),
        }
    comparisons = data["response_comparisons"]
    repeat_changes = sum(p["text_repeats_differ"] is True for p in comparisons)
    media_changes = sum(p["video_differs_from_both_texts"] is True for p in comparisons)
    main_snapshot = evidence.read(ROOT / "reports/experiments/2026-10-20_t4_expanded_api.json", {})
    result = {
        "audited_at": now(), "request_count": budget["request_count"],
        "responses_received": sum(r["nonempty_response_received"] for r in rows),
        "identical_text_and_sampling_groups": len(groups),
        "text_repeat_changes": repeat_changes, "video_different_from_both_texts": media_changes,
        "model_summary": models, "agent_review_flags": flags,
        "human_validation_status": "not_human_validated",
        "source_trajectory_hashes_unchanged": True, "frozen_script_hash_unchanged": True,
        "visually_reviewed_frames": visual_asset["frames"],
        "authorization": authorization, "calls": rows,
        "main_run_snapshot_at": main_snapshot.get("updated_at"),
        "main_run_paired_effects": main_snapshot.get("paired_effects", {}),
        "source_files": evidence.sources,
    }
    save(PREFIX.with_suffix(".json"), result)
    write_csv(PREFIX.with_suffix(".csv"), sorted(rows, key=lambda r: (r["scenario_id"], r["model_id"], r["variant"])))
    lines = [
        "# T4 固定节点对照核验与实验发现", "",
        f"核验时间：{result['audited_at']}。36 次授权调用全部结束，"
        f"收到非空回应 {result['responses_received']}/36；"
        f"带媒体请求成功 {sum(v['successful_media_responses'] for v in models.values())}/12。",
        "12 组实际请求的文字与采样参数严格一致，文字条件均无媒体；"
        "每项仅调用一次，无补抽，原轨迹及执行脚本哈希保持不变。",
        "",
        "[逐请求核验 CSV](2026-10-20_t4_checkpoint_findings.csv) · "
        "[完整核验 JSON](2026-10-20_t4_checkpoint_findings.json) · "
        "[三条件原始回应](2026-10-20_t4_checkpoint_media.md) · "
        "[完整轨迹实时补测](2026-10-20_t4_expanded_api.md)",
        "",
        "| 模型 | 非空回应 / 6 | 成功媒体回应 / 2 | 已标记语义复核项 |",
        "|---|---:|---:|---:|",
    ]
    for m in models.values():
        lines.append(f"| {m['model']} | {m['api_responses']} | {m['successful_media_responses']} | {m['agent_review_flags']} |")
    lines += [
        "", "**回应差异的含义**", "",
        f"两次纯文字回应在 {repeat_changes}/12 组中已经不同；"
        f"媒体回应与两次文字均不同的有 {media_changes}/12 组。"
        "这是去空白和标点后的字符串差异，不是质量评分或媒体因果效果。"
        "当前样本能验证媒体请求成功及具体回应行为，不能据此宣称稳定收益。",
        "",
        "**已发现的回应问题**", "",
    ]
    if flags:
        lines += [
            "Claude 在 024 的文字 A/B 均继续处理发布与核实任务，媒体条件却用英文拒绝扮演，"
            "自称 “I'm Kiro, an AI development environment.” 并转向提供编程协助。"
            "这是一次实际角色脱离，不能算有效场景行动；模型的自称不能证明后端模型身份。",
            "该项当前 `hard_only` 校验返回 true，表明格式通过不能替代语义质量审查。"
            "保留原结果，不修改已冻结校验或把此次异常重试成成功；这里的标记属于助手复核，不是人工正式标签。",
            "",
            "DeepSeek-V4.1-Flash 在 024 的媒体回应提出删除“旁白里那句‘就在那天’”，"
            "但输入中没有这句旁白，抽帧也没有语音或该文字。"
            "这是新增了未经输入支持的具体台词，作为事实依据问题保留；两次文字回应没有提出这句台词。"
            "单次出现不能证明媒体必然导致此问题，也没有据此改写任何 T4 得分。",
            "",
        ]
    lines += [
        "**完整轨迹分差仍是小样本**", "",
        f"主补测快照：{main_snapshot.get('updated_at', 'unknown')}；"
        "只有同场景、同模型、同批次的完整文字与媒体轨迹构成配对。",
        "",
        "| 模型 | 有效配对数 | 核心四维 多模态减文字 |",
        "|---|---:|---:|",
    ]
    for name, metrics in main_snapshot.get("paired_effects", {}).items():
        value = metrics["core_four_mean"]
        if value["n"]:
            lines.append(f"| {main_snapshot['model_names'][name]} | {value['n']} | {value['mean']:+.4f} |")
    lines += [
        "",
        "这些是不同完整轨迹的条件分差，不能用固定节点回应差异替代；"
        "也不能把同一场景内多个模型当作多个独立场景。原生视频和抽帧两种传输在跨模型比较时亦有差异。",
        "",
        "**需要复核的素材与评分因素**", "",
        "实际查看 024 已发送的四帧后可见：0.25 秒双臂放下，1.25–3.25 秒双拳抬至头侧。"
        "这是较明显的动作线索，不能把其结果直接外推到细微表情识别；"
        "素材目前只记录结构校验通过，动作的自然度和情绪适配性仍需人工复核。此处未验证音频理解。",
        "主补测 002 的自动裁判还存在口径差异待复核：GPT 文字轨迹的目标达成给 10 分，"
        "同时承认书面文件尚未交付；Qwen3.5 文字轨迹给 7 分，其中一个扣分理由正是尚未实际收到书面文件。"
        "轨迹具体内容不同，不能据此断言评分错误，但这提示“对话承诺”与“外部完成”的判准需要校准。"
        "原始分数全部保留，未追加裁判 API 调用。",
        "",
    ]
    PREFIX.with_suffix(".md").write_text("\n".join(lines))
    print(json.dumps({k: result[k] for k in ("audited_at", "request_count", "responses_received",
                                            "text_repeat_changes", "video_different_from_both_texts",
                                            "model_summary")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
