#!/usr/bin/env python3
"""Unify the one-attempt-per-scenario Scale20 batch for human review."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.instance_quality import audit_trajectory
from evaluation.rollout_gate import audit_rollout

OUTPUT_ROOTS = (
    ROOT / "build/scale20_v1/full20_v1_8301",
    ROOT / "build/scale20_v1/full20_v1_8302",
    ROOT / "build/scale20_v1/full20_v1_8304",
    ROOT / "build/scale20_v1/full20_v1_8304_extra",
)
OUTPUT = ROOT / "build/scale20_v1/full20_human_review.json"
MARKDOWN = ROOT / "build/scale20_v1/full20_human_review.md"

MODEL_REVIEW = {
    "IA_PIPE_001": ("clear_issue", "t3–t5重复等待；t9环境照抄；多次把尚未提供/标注的材料写成已完成。"),
    "IA_PIPE_002": ("priority_human_review", "仅2轮；环境仍欠当前答复却被记为自然结束，适合判断终止标准是否过严。"),
    "IA_PIPE_003": ("priority_human_review", "4轮借款节点连贯，承诺与实际转账记录有区分；长度不足主数据要求。"),
    "IA_PIPE_004": ("priority_human_review", "5轮照护分工较自然；新增李阿姨属合理情境补全，但在结构错误前未完成后续核验。"),
    "IA_PIPE_005": ("clear_issue", "t4、t10、t15–t18存在说话人照抄/动作偷取，t9后持续围绕护士站与小时工空转。"),
    "IA_PIPE_006": ("priority_human_review", "3轮调查报道协作连贯，但法务当天初审与发布步骤偏快，且长度很短。"),
    "IA_PIPE_007": ("priority_human_review", "5轮平台申诉较自然；平台内部风控解释属于模型补全，需人工判断是否越过事实边界。"),
    "IA_PIPE_008": ("clear_issue", "无依据扩展具体治疗方案、器官损伤与评估频率；t17–t20重复，预算截断。"),
    "IA_PIPE_009": ("priority_human_review", "4轮工作归属讨论自然，但环境最后仍未正面回答归属边界却自然结束。"),
    "IA_PIPE_010": ("priority_human_review", "9轮总体连贯；20%灰度、72小时与24小时均作为新提案出现，需判断是否合理而非过度制度化。"),
    "IA_PIPE_011": ("clear_issue", "仅2轮并新增半小时后到场的合规负责人，改变行动可行性。"),
    "IA_PIPE_012": ("priority_human_review", "3轮共同育儿安排基本连贯；7点/9点、图书馆活动属新增提案而非既有事实。"),
    "IA_PIPE_013": ("clear_issue", "3轮中新增48小时启动要求，环境随即把它写成自身安排；动作归属边界不稳。"),
    "IA_PIPE_014": ("clear_issue", "t7–t12重复已知风险范围，t13照抄，且把独立董事审核程序逐步写成已启动事实。"),
    "IA_PIPE_015": ("clear_issue", "20轮持续追加草案、标签、图表和审批条件，几乎没有新互动意义。"),
    "IA_PIPE_016": ("priority_human_review", "8轮餐厅试运行较自然；t2环境照抄，老张排班/职责补全需人工确认可接受程度。"),
    "IA_PIPE_017": ("clear_issue", "t7–t20反复承诺明天确认诊断和意愿，持续无信息循环。"),
    "IA_PIPE_018": ("clear_issue", "20轮从信号模板漂移到令牌、哈希、随机字符，技术内容无依据且持续空转。"),
    "IA_PIPE_019": ("borderline_human_review", "前10轮较自然且有治理权取舍；t11–t16明显重复，新增董事会权限事实需核对场景边界。"),
    "IA_PIPE_020": ("clear_issue", "8轮基本连贯，但在伦理审查尚未完成时推进当晚签署，存在关键时序与权利风险。"),
}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def find_artifact(root: Path, scenario_id: str):
    matches = []
    for path in root.rglob("*.json"):
        if path.name in {"progress.json", "manifest.json"}:
            continue
        try:
            value = read_json(path)
        except (json.JSONDecodeError, OSError):
            continue
        if value.get("scenario_id") == scenario_id:
            matches.append((path, value))
    if len(matches) != 1:
        raise ValueError(f"expected one artifact for {scenario_id} in {root}, found {len(matches)}")
    return matches[0]


def _contains_nonzero(value):
    if isinstance(value, dict):
        return any(_contains_nonzero(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_nonzero(item) for item in value)
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value != 0


def changed_turn_count(trajectory):
    return sum(
        _contains_nonzero(turn.get("numeric_state_delta", {}))
        or _contains_nonzero(turn.get("numeric_dynamics_delta", {}))
        for turn in trajectory["turns"]
    )


def main():
    attempts = {}
    for root in OUTPUT_ROOTS:
        progress = read_json(root / "progress.json")
        for attempt in progress["attempts"]:
            scenario_id = attempt["scenario_id"]
            if scenario_id in attempts:
                raise ValueError(f"duplicate completed attempt: {scenario_id}")
            artifact_path, trajectory = find_artifact(root, scenario_id)
            attempts[scenario_id] = (attempt, artifact_path, trajectory)
    expected = {f"IA_PIPE_{index:03d}" for index in range(1, 21)}
    if set(attempts) != expected:
        raise ValueError(f"scenario coverage mismatch: {sorted(expected - set(attempts))}")

    candidates = []
    status_counts = Counter()
    review_counts = Counter()
    total_turns = 0
    total_requests = Counter()
    for scenario_id in sorted(attempts):
        attempt, path, trajectory = attempts[scenario_id]
        machine_structure = audit_trajectory(trajectory)
        machine_gate = audit_rollout(trajectory)
        review_label, review_note = MODEL_REVIEW[scenario_id]
        turns = trajectory.get("turns", [])
        requests = trajectory.get("actual_request_counts", {})
        stage_presence = {
            "every_turn_has_appraisal": all(bool(turn.get("appraisal")) for turn in turns),
            "every_turn_has_deterministic_state_update": all("state_after" in turn and "dynamics_after" in turn for turn in turns),
            "every_turn_has_response": all(bool(turn.get("environment_response")) for turn in turns),
            "every_turn_has_ledger_snapshot": all("interaction_ledger_after" in turn for turn in turns),
        }
        status_counts[attempt["status"]] += 1
        review_counts[review_label] += 1
        total_turns += len(turns)
        for key in ("policy", "appraisal", "response", "total"):
            total_requests[key] += int(requests.get(key, 0))
        candidates.append({
            "scenario_id": scenario_id,
            "trajectory_id": trajectory["trajectory_id"],
            "artifact_path": str(path.relative_to(ROOT)),
            "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "generation_status": attempt["status"],
            "turn_count": len(turns),
            "ending": trajectory.get("ending"),
            "actual_request_counts": requests,
            "machine_precheck": attempt.get("precheck"),
            "machine_structure_audit": machine_structure,
            "machine_rollout_gate": machine_gate,
            "framework_presence": stage_presence,
            "changed_turn_count": changed_turn_count(trajectory),
            "model_semantic_review": {"label": review_label, "note": review_note},
            "human_review": "pending",
        })

    payload = {
        "format": "socialflux_scale20_full20_human_review_v1",
        "status": "generated_pending_human_review",
        "quality_version": "scale20_v1_natural_fragment_progression",
        "configuration_count": 20,
        "generated_scenario_count": 20,
        "selected_trajectory_count": 20,
        "total_turns": total_turns,
        "turns_with_nonzero_state_or_dynamics_update": sum(item["changed_turn_count"] for item in candidates),
        "generation_status_counts": dict(sorted(status_counts.items())),
        "model_semantic_review_counts": dict(sorted(review_counts.items())),
        "actual_request_counts": dict(total_requests),
        "architecture": ["structured_appraisal_llm", "deterministic_python_update", "response_generation_llm"],
        "human_review_warning": "模型语义复核仅作优先级提示，不是人工验收或 Ground Truth。",
        "candidates": candidates,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# SocialFlux Scale20 单条 Rollout 人工审核包", "",
        f"- 场景：20/20", f"- 轨迹：20", f"- 总轮数：{total_turns}",
        f"- 生成状态：{dict(sorted(status_counts.items()))}",
        f"- 模型复核：{dict(sorted(review_counts.items()))}",
        "- 注意：模型复核不是人工验收。", "", "## 汇总", "",
        "| Scenario | 轮数 | 生成状态 | 模型复核 | 人工状态 |", "|---|---:|---|---|---|",
    ]
    for item in candidates:
        lines.append(f"| {item['scenario_id']} | {item['turn_count']} | {item['generation_status']} | {item['model_semantic_review']['label']} | pending |")
    lines.extend(["", "## 二十条完整对话", ""])
    for item in candidates:
        trajectory = attempts[item["scenario_id"]][2]
        lines.extend([
            f"### {item['scenario_id']} · {item['trajectory_id']}", "",
            f"生成状态：`{item['generation_status']}`；轮数：{item['turn_count']}；模型复核：`{item['model_semantic_review']['label']}`。", "",
            f"模型提示：{item['model_semantic_review']['note']}", "",
        ])
        for turn in trajectory["turns"]:
            lines.extend([
                f"**{turn['turn_id']} Agent：** {turn.get('policy_action', {}).get('text', '')}", "",
                f"**{turn['turn_id']} Environment：** {turn.get('environment_response', '')}", "",
            ])
    MARKDOWN.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("status", "generated_scenario_count", "total_turns", "generation_status_counts", "model_semantic_review_counts", "actual_request_counts")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
