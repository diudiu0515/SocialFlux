#!/usr/bin/env python3
"""Bounded same-observation response checks; never score them as T4 trajectories."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "build/t4_expanded_api_20261020/runtime"
sys.path.insert(0, str(RUNTIME))
from evaluation.t4_batch import digest, save
from evaluation.t4_media import compact_media
from evaluation.t4_multimodal import AssetPolicy, AuditedProvider, RequestBudget
from providers.text import normalize_text, strip_outer_dialogue_quotes

OUT = ROOT / "build/t4_expanded_api_20261020/checkpoint_diagnostic"
REPORT = ROOT / "reports/experiments/2026-10-20_t4_checkpoint_media"
SOURCES = {
    "GPT50_002": "build/t4_gpt41_paired_20261020/run/episodes/GPT50_002/gpt/text_video/trajectory.json",
    "GPT50_024": "build/t4_gpt33_parallel_20261020/run/episodes/GPT50_024/claude/text_video/trajectory.json",
}


def now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def text_projection(messages):
    return [{
        "role": m["role"],
        "content": m["content"] if isinstance(m["content"], str) else
        "".join(b["text"] for b in m["content"] if b.get("type") == "text"),
    } for m in messages]


def publish(plan, rows, budget, finished=False):
    pairs = []
    for sid in plan["scenario_ids"]:
        for model in plan["models"]:
            group = {r["variant"]: r for r in rows if r["scenario_id"] == sid and r["model_id"] == model}
            if len(group) != 3:
                continue
            good = all(r["status"] == "response_received" for r in group.values())
            norm = {v: normalize_text(r.get("response", "")) for v, r in group.items()}
            pairs.append({
                "scenario_id": sid, "model_id": model, "all_three_received": good,
                "text_repeats_differ": norm["text_a"] != norm["text_b"] if good else None,
                "video_differs_from_both_texts": norm["video"] not in (norm["text_a"], norm["text_b"]) if good else None,
                "responses": {v: r.get("response") for v, r in group.items()},
            })
    data = {"updated_at": now(), "status": "completed" if finished else "running",
            "finished": len(rows), "planned": plan["request_limit"],
            "api_requests": budget.count, "plan": plan, "results": rows, "response_comparisons": pairs}
    save(OUT / "results.json", data)
    save(REPORT.with_suffix(".json"), data)
    lines = [
        "# T4 相同对话节点媒体回应对照",
        "",
        f"更新：{data['updated_at']}。状态：{data['status']}，完成 {len(rows)}/{plan['request_limit']} 次请求。",
        "",
        "两个节点分别取自 GPT 的 002 和 Claude 的 024 已保存终局触发轨迹。"
        "冻结它们的公开 observation_after，只将 status 从 completed 改为 active，模拟新版规则给予的下一次回应机会；"
        "原轨迹、状态数值及原成绩不改动。节点对所有被测模型相同。",
        "",
        "每个模型在每个节点请求两次纯文字回应和一次带媒体回应，文字部分及采样完全相同，"
        "temperature=0.6、top_p=0.9、不传 seed，每项只调用一次、不重抽。"
        "抽帧保持原时间顺序，此对照去掉额外的时间标签文字，以保持三个请求的文字完全一致。"
        "这是独立的回应敏感性诊断，没有重跑环境、终局或裁判，不产生 T4 分数。",
        "",
        "[完整输入出处、参数与回应 JSON](2026-10-20_t4_checkpoint_media.json) · "
        "[完整轨迹补测](2026-10-20_t4_expanded_api.md)",
        "",
        "| 场景 | 模型 | 三次请求均成功 | 两次文字回应不同 | 视频回应与两次文字均不同 |",
        "|---|---|---|---|---|",
    ]
    for pair in pairs:
        display = lambda v: "是" if v is True else "否" if v is False else "不可比较"
        lines.append("| " + " | ".join([pair["scenario_id"], plan["models"][pair["model_id"]]["model"],
                                       display(pair["all_three_received"]), display(pair["text_repeats_differ"]),
                                       display(pair["video_differs_from_both_texts"])]) + " |")
    lines += [
        "",
        "字符串不同只说明输出不同。若两次纯文字输出也不同，就不能把视频回应的每一处变化都归因于媒体；"
        "这些结果需要结合原视频与回应内容阅读，不能作为多模态质量提升的分数。",
        "",
    ]
    for pair in pairs:
        lines += [f"**{pair['scenario_id']} · {plan['models'][pair['model_id']]['model']}**", ""]
        for variant, label in (("text_a", "文字 A"), ("text_b", "文字 B"), ("video", "多模态")):
            lines += [f"{label}：{pair['responses'][variant] or '请求未得到有效回应'}", ""]
    REPORT.with_suffix(".md").write_text("\n".join(lines))
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "request_budget.json").exists():
        raise ValueError("diagnostic already exists; preserve its first-pass outcomes")
    main_plan = json.loads((RUNTIME.parent / "run/plan.json").read_text())
    caps = json.loads((RUNTIME.parent / "run/capabilities.json").read_text())
    # The runtime's route files are frozen; do not resolve mutable root routes.
    from scripts.run_t4_multimodal_experiment import model_configs
    config = deepcopy(main_plan["config"])
    for entry in config["models"]:
        entry["routes"] = str(RUNTIME / entry["routes"])
    configs = model_configs(config)
    names = [n for n in config["policy_models"] if caps[n]["selected_transport"]]
    assets = json.loads((RUNTIME.parent / "run/preregistration.json").read_text())["assets"]
    observations, sources = {}, {}
    for sid, relative in SOURCES.items():
        path = ROOT / relative
        original = json.loads(path.read_text())
        observation = deepcopy(original["turns"][-1]["observation_after"])
        assert observation["media"] and observation["status"] == "completed"
        observation["status"] = "active"
        observations[sid] = observation
        source_path = ROOT / "data/gpt50/experiment/scenario/scenarios_state_v3" / (
            "scenario_" + sid[-3:]) / ("scenario_" + sid[-3:] + ".json")
        sources[sid] = {"path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "original_policy_model": original["policy_provenance"]["model"],
                        "original_api_endpoint": original["policy_provenance"]["endpoint"],
                        "scenario_source": json.loads(source_path.read_text())["source"],
                        "changed_fields": {"status": {"before": "completed", "after": "active"}},
                        "observation_sha256": digest(observation)}
        save(OUT / "inputs" / (sid + ".json"), observation)
    limit = len(names) * len(SOURCES) * 3
    plan = {"scenario_ids": list(SOURCES), "sources": sources, "created_at": now(),
            "models": {n: {"model": configs[n]["model"], "transport": caps[n]["selected_transport"]} for n in names},
            "sampling": {"temperature": 0.6, "top_p": 0.9}, "request_limit": limit,
            "workers": 2, "no_environment_or_judge_calls": True,
            "frame_timestamp_labels": "omitted_to_match_all_text_exactly; frame_order_preserved",
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if (OUT / "plan.json").exists():
        existing = json.loads((OUT / "plan.json").read_text())
        plan["created_at"] = existing["created_at"]
        if existing != plan:
            raise ValueError("prepared diagnostic changed")
    budget = RequestBudget(OUT / "request_budget.json", limit)
    jobs = []
    # Validate all paired text projections and freeze compact requests before any API.
    for sid, observation in observations.items():
        for name in names:
            hashes = []
            for variant in ("text_a", "text_b", "video"):
                directory = OUT / "responses" / sid / name / variant
                condition = "text_video" if variant == "video" else "text_only"
                policy = AssetPolicy(
                    f"checkpoint_{sid}_{name}", None, prompt_id="task_t4_action_v21",
                    validation_profile="hard_only", minimum_natural_turns=1,
                    sampling=plan["sampling"], observation_condition=condition,
                    media_input_format="openai_video_url" if variant == "video" else None,
                    assets=assets, transport=caps[name]["selected_transport"],
                    audit_path=directory / "prepared_media.json")
                messages, _ = policy._build_request(observation)
                for message in messages:
                    if isinstance(message["content"], list):
                        message["content"] = [
                            block for index, block in enumerate(message["content"])
                            if not (index > 0 and block.get("type") == "text"
                                    and block.get("text", "").startswith("Video timestamp "))
                        ]
                hashes.append(digest(text_projection(messages)))
                save(directory / "input.json", {"messages": compact_media(messages),
                                                "text_sha256": hashes[-1], "sampling": plan["sampling"]})
                jobs.append((sid, name, variant, directory, policy, messages))
            assert len(set(hashes)) == 1, "paired text differs"
    save(OUT / "plan.json", plan)
    if args.prepare_only:
        print(f"Prepared {limit} requests with identical paired text; no API calls.")
        return

    def run(job):
        sid, name, variant, directory, policy, messages = job
        provider = AuditedProvider({**configs[name], "max_tokens": 1800}, directory / "calls", budget)
        row = {"scenario_id": sid, "model_id": name, "variant": variant, "started_at": now(),
               "input_path": str((directory / "input.json").relative_to(ROOT))}
        try:
            response = provider.complete(messages, **plan["sampling"])
            if not response or not response.strip():
                raise ValueError("empty response")
            validity = policy._validate_candidate_for_profile(strip_outer_dialogue_quotes(response), observations[sid])
            row.update(status="response_received", response=response, local_action_validation=validity)
        except Exception as exc:
            row.update(status="failed", error=str(exc))
        row["finished_at"] = now()
        save(directory / "result.json", row)
        return row

    rows = []
    publish(plan, rows, budget)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, job) for job in jobs]
        for future in as_completed(futures):
            rows.append(future.result())
            publish(plan, rows, budget)
            print(f"{len(rows)}/{limit} responses recorded", flush=True)
    data = publish(plan, rows, budget, finished=True)
    print(json.dumps({"status": data["status"], "finished": len(rows), "api_requests": budget.count}))


if __name__ == "__main__":
    main()
