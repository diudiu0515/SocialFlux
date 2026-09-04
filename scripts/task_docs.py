"""Render rollout-derived T1/T2/T3 candidates for human spot checks.

The benchmark JSONL stays leakage-safe. This module writes a separate, private
review overlay next to each scenario's rollouts so a researcher can understand
what was generated without manually joining trajectory and intervention files.
"""

from collections import defaultdict
from pathlib import Path

from environment.delta_mapper import flatten_state


TASK_ORDER = (
    "T1_state_tracking",
    "T2_history_sensitive_merge",
    "T3_counterfactual_choice_effect",
)


def _text(value, fallback="—"):
    if value is None:
        return fallback
    value = str(value).strip()
    return value or fallback


def _state_at_checkpoint(trajectory, public_history_length):
    """Return private state after a public history and before its next turn."""
    turns = trajectory.get("turns", [])
    if public_history_length < len(turns):
        return turns[public_history_length].get("state_before", {})
    if turns:
        return turns[-1].get("state_after", {})
    return trajectory.get("initial_state", {})


def _state_snapshot(state):
    values = flatten_state(state or {})
    if not values:
        return "无可用状态值"
    return "；".join(f"`{key}`={value}" for key, value in sorted(values.items()))


def _transition(before, after):
    left = flatten_state(before or {})
    right = flatten_state(after or {})
    keys = sorted(set(left) | set(right))
    if not keys:
        return "无可用状态值"
    parts = []
    for key in keys:
        old = left.get(key, "—")
        new = right.get(key, "—")
        direction = "不变"
        if isinstance(old, (int, float)) and isinstance(new, (int, float)):
            direction = "上升" if new > old else "下降" if new < old else "不变"
        parts.append(f"`{key}` {old} → {new}（{direction}）")
    return "；".join(parts)


def _observable(observation):
    observation = observation or {}
    expression = observation.get("observable_expression", {}) or {}
    cues = observation.get("observable_cues", []) or expression.get("behavioral_cues", []) or []
    return [
        f"- 当前回应：{_text(observation.get('current_response'))}",
        f"- 表情：{_text(expression.get('facial_expression'))}",
        f"- 视线：{_text(expression.get('gaze'))}",
        f"- 语气/韵律：{_text(expression.get('prosody') or expression.get('speech_style'))}",
        f"- 可观察线索：{_text('；'.join(map(str, cues)) if cues else None)}",
    ]


def _public_history(history, heading="公开对话历史"):
    lines = [f"**{heading}**", ""]
    if not history:
        return lines + ["- 尚无历史轮次。", ""]
    for index, turn in enumerate(history, 1):
        if "policy_action" in turn:
            turn_id = turn.get("turn_id", f"turn-{index}")
            lines.extend([
                f"- {turn_id}，被评估角色：{_text(turn.get('policy_action', {}).get('text'))}",
                f"  - 环境角色：{_text(turn.get('environment_response'))}",
            ])
        else:
            role = {
                "evaluated_agent": "被评估角色",
                "environment_agent": "环境角色",
            }.get(turn.get("role"), _text(turn.get("role"), "角色"))
            lines.append(f"- {turn.get('turn_id', index)}，{role}：{_text(turn.get('text'))}")
    lines.append("")
    return lines


def _target_line(instance):
    target = instance.get("target_spec", {})
    states = target.get("target_state_ids", [])
    target_id = target.get("target_character_id") or instance.get("input", {}).get("target_character_id")
    state_text = ", ".join(f"`{item}`" for item in states) if states else "按场景完整状态空间判断"
    return f"目标角色：`{_text(target_id)}`；目标状态：{state_text}。"


def _render_t1(instance, trajectories):
    inputs = instance["input"]
    source_id = instance["metadata"]["source_trajectory_id"]
    trajectory = trajectories.get(source_id, {})
    index = max(0, len(inputs.get("history", [])) - 1)
    turns = trajectory.get("turns", [])
    turn = turns[index] if index < len(turns) else {}
    lines = [
        f"### `{instance['instance_id']}`",
        "",
        "任务说明：阅读截至当前检查点的对话，判断环境角色此刻的主观状态；正式答案仍等待人工标注。",
        "",
        f"- 来源 trajectory：`{source_id}`，检查点：`{turn.get('turn_id', index + 1)}`",
        f"- {_target_line(instance)}",
        "",
    ]
    lines.extend(_public_history(inputs.get("history", [])))
    lines.extend(["**当前可观察信息**", "", *_observable(inputs.get("current_checkpoint")), ""])
    lines.extend([
        "**私有诊断层（仅供研究员核验生成合理性，不得作为模型输入或正式 GT）**",
        "",
        f"- 本轮内部状态变化：{_transition(turn.get('state_before'), turn.get('state_after'))}",
        f"- 本轮互动动力变化：{_transition(turn.get('dynamics_before'), turn.get('dynamics_after'))}",
        "- 人工抽查：对照最后一句 action，确认变化方向、幅度、persona 条件化和历史依赖是否合理。",
        "",
    ])
    return lines


def _render_t2(instance, trajectories):
    inputs = instance["input"]
    source_ids = instance["metadata"]["source_trajectory_ids"]
    history_a = inputs.get("history_a", [])
    history_b = inputs.get("history_b", [])
    state_a = _state_at_checkpoint(trajectories.get(source_ids[0], {}), len(history_a))
    state_b = _state_at_checkpoint(trajectories.get(source_ids[1], {}), len(history_b))
    lines = [
        f"### `{instance['instance_id']}`",
        "",
        "任务说明：两段不同历史被合流到同一个当前观察 O*；判断目标角色在各状态维度上是 A 更高、相近、B 更高，还是无法确定。",
        "",
        f"- 来源 trajectory A/B：`{source_ids[0]}` / `{source_ids[1]}`",
        f"- {_target_line(instance)}",
        "",
    ]
    lines.extend(_public_history(history_a, "历史 A"))
    lines.extend(_public_history(history_b, "历史 B"))
    lines.extend(["**共享当前观察 O\\***", "", *_observable(inputs.get("shared_current_observation")), ""])
    lines.extend([
        "**私有诊断层（仅供研究员核验生成合理性，不得作为模型输入或正式 GT）**",
        "",
        f"- A 合流前内部状态：{_state_snapshot(state_a)}",
        f"- B 合流前内部状态：{_state_snapshot(state_b)}",
        f"- A → B 数值对照：{_transition(state_a, state_b)}",
        "- 人工抽查：先确认 A/B 历史确实不同，再确认 O* 对两边都自然、没有复述任一历史，也没有泄漏私有状态。",
        "",
    ])
    return lines


def _render_t3(instance, branches):
    inputs = instance["input"]
    metadata = instance["metadata"]
    branch_key = (metadata["source_trajectory_id"], metadata["checkpoint_turn_id"])
    matching = branches.get(branch_key, [])
    lines = [
        f"### `{instance['instance_id']}`",
        "",
        "任务说明：从同一检查点替换下一句 action，对比每个候选对目标角色的即时和延迟影响；正式答案仍等待人工标注。",
        "",
        f"- 来源 trajectory：`{branch_key[0]}`，检查点：`{branch_key[1]}`",
        f"- {_target_line(instance)}",
        f"- 延迟观察窗口：`{instance.get('target_spec', {}).get('delayed_horizon', '—')}` 轮",
        "",
    ]
    lines.extend(_public_history(inputs.get("history", [])))
    lines.extend(["**当前可观察信息**", "", *_observable(inputs.get("current_observation")), ""])
    lines.extend(["**候选 action 与私有模拟诊断**", ""])
    if not matching:
        lines.extend(["- 未找到配套 intervention branch；该实例不可交付，需重新运行。", ""])
    for index, action in enumerate(inputs.get("candidate_actions", []), 1):
        branch = matching[index - 1] if index - 1 < len(matching) else {}
        lines.extend([
            f"#### 候选 {index}",
            "",
            f"> {_text(action.get('text'))}",
            "",
            "私有诊断（仅供研究员核验，不得作为模型输入或正式 GT）：",
            "",
            f"- 即时状态：{_transition(branch.get('state_before'), branch.get('state_after_immediate'))}",
            f"- 延迟状态：{_transition(branch.get('state_before'), branch.get('state_after_delayed'))}",
            f"- 即时互动动力：{_transition(branch.get('dynamics_before'), branch.get('dynamics_after_immediate'))}",
            f"- 延迟互动动力：{_transition(branch.get('dynamics_before'), branch.get('dynamics_after_delayed'))}",
            "",
        ])
    lines.extend([
        "人工抽查：比较候选间差异是否来自局部 action，而非分支协议变化；同时检查即时与延迟方向是否符合人物和历史。",
        "",
    ])
    return lines


def render_task_review(scenario, instances, trajectory_records, branch_records):
    """Return one deterministic Chinese Markdown review package."""
    trajectories = {item["trajectory_id"]: item for item in trajectory_records}
    branches = defaultdict(list)
    for branch in branch_records:
        key = (branch.get("source_trajectory_id"), branch.get("checkpoint_turn_id"))
        branches[key].append(branch)
    grouped = {task: [] for task in TASK_ORDER}
    for instance in instances:
        grouped.setdefault(instance["task_type"], []).append(instance)

    persona = scenario.get("environment_agent", {}).get("persona", {})
    lines = [
        f"# {scenario['title']} — T1/T2/T3 人工抽查包",
        "",
        "> 本文档由 pipeline 从同目录真实 rollout、离线 instance 与局部反事实 branch 确定性生成。公开题面与私有诊断严格分区；私有诊断不能进入 benchmark 输入，也不是人工 Ground Truth。",
        "",
        f"- Scenario ID：`{scenario['scenario_id']}`",
        f"- 环境角色：{_text(persona.get('name'))}（{_text(persona.get('role'))}）",
        f"- 生成数量：T1 `{len(grouped['T1_state_tracking'])}`；T2 `{len(grouped['T2_history_sensitive_merge'])}`；T3 `{len(grouped['T3_counterfactual_choice_effect'])}`",
        "- 标注状态：`pending_human_annotation`",
        "",
        "## 怎么抽查",
        "",
        "1. 先只读公开历史、当前观察和候选 action，独立写下判断。",
        "2. 再展开私有诊断，检查 simulator 的状态方向与幅度，而不是把它直接当答案。",
        "3. 发现人物失真、历史断裂、共享观察不兼容、候选近义重复或分支无差异时，记录 instance ID 并退回重生成。",
        "",
        "## T1：当前状态跟踪",
        "",
    ]
    if not grouped["T1_state_tracking"]:
        lines.extend(["**缺失：本 scenario 尚未提取 T1。**", ""])
    for instance in grouped["T1_state_tracking"]:
        lines.extend(_render_t1(instance, trajectories))
    lines.extend(["## T2：历史敏感合流", ""])
    if not grouped["T2_history_sensitive_merge"]:
        lines.extend(["**缺失：本 scenario 尚未提取 T2。**", ""])
    for instance in grouped["T2_history_sensitive_merge"]:
        lines.extend(_render_t2(instance, trajectories))
    lines.extend(["## T3：局部反事实 action 效果", ""])
    if not grouped["T3_counterfactual_choice_effect"]:
        lines.extend(["**缺失：本 scenario 尚未提取 T3。**", ""])
    for instance in grouped["T3_counterfactual_choice_effect"]:
        lines.extend(_render_t3(instance, branches))
    return "\n".join(lines).rstrip() + "\n"


def write_task_review(path, scenario, instances, trajectories, branches):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_task_review(scenario, instances, trajectories, branches),
        encoding="utf-8",
    )
    return path
