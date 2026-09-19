"""Generate leakage-safe machine proposals for SocialFlux T3."""

from __future__ import annotations

from copy import deepcopy
import json

from providers.structured import complete_json
from scripts.t2_common import call_count
from tasks.T3.t3_probability_utils import (
    DIRECTION_LABELS,
    validate_probabilities,
)


def _public_turn_id(value):
    if isinstance(value, bool):
        raise ValueError("boolean is not a public turn id")
    if isinstance(value, int):
        return f"t{value}"
    text = str(value).strip()
    if text.isdigit():
        return f"t{text}"
    return text


def canonicalize_instance(instance):
    """Normalize legacy numeric public IDs before prompting or validation."""
    normalized = deepcopy(instance)
    for turn in normalized["input"].get("history", []):
        turn["turn_id"] = _public_turn_id(turn["turn_id"])
    current = normalized["input"].get("current_observation", {})
    if "turn_id" in current:
        current["turn_id"] = _public_turn_id(current["turn_id"])
    return normalized


def answer_prompt(instance, private_persona=None):
    state_ids = instance["target_spec"]["target_state_ids"]
    actions = instance["input"]["candidate_actions"]
    schema = {
        "instance_id": instance["instance_id"],
        "options": [
            {
                "action_index": index,
                "state_predictions": [
                    {
                        "state_id": state_id,
                        "immediate": {label: 0.0 for label in DIRECTION_LABELS},
                        "delayed": {label: 0.0 for label in DIRECTION_LABELS},
                        "evidence_turn_ids": ["t1"],
                    }
                    for state_id in state_ids
                ],
            }
            for index in range(len(actions))
        ],
    }
    return (
        "你为 SocialFlux T3 生成机器候选答案，之后由人判断正确与否；答案不是 GT。"
        "可以使用另附的作者侧私有 Persona 条件化解释，但它不是公开证据，不得引用或泄露。"
        "所有 candidate_actions 从同一公开 checkpoint 分支。只根据公开 history、current_observation、"
        "候选行动与统一 horizon，预测每个行动相对 checkpoint 对目标角色状态的即时和延迟影响。"
        "主任务不提供 latent state；除另附 Persona 外不得推测其他私有信息、引入支线外部事件或把行动承诺当作完成。"
        "不同动作可能产生相同影响，但不能为了省事把所有动作和状态机械填成同一分布。延迟预测"
        "必须尊重 target_spec 的共享 continuation protocol 与 frozen event plan；缺少支持时提高 "
        "cannot_determine。evidence_turn_ids 只能引用输入 history 的真实 turn_id，不能引用候选执行"
        "后的虚构未来。每个概率对象的全部值之和必须为 1。只输出以下 JSON，不增减字段：\n"
        + json.dumps(schema, ensure_ascii=False)
        + "\nT3 实例：\n"
        + json.dumps(instance, ensure_ascii=False, sort_keys=True)
        + (
            "\n作者侧私有 Persona（仅用于条件化解释，不得作为公开证据引用或写入答案）：\n"
            + json.dumps(private_persona, ensure_ascii=False, sort_keys=True)
            if private_persona is not None else ""
        )
    )


def validate_answer(value, instance):
    if not isinstance(value, dict) or set(value) != {"instance_id", "options"}:
        raise ValueError("T3 answer top keys")
    if value["instance_id"] != instance["instance_id"]:
        raise ValueError("T3 answer instance id")
    action_count = len(instance["input"]["candidate_actions"])
    options = value["options"]
    if (
        not isinstance(options, list)
        or len(options) != action_count
        or {row.get("action_index") for row in options} != set(range(action_count))
    ):
        raise ValueError("T3 option coverage")
    state_ids = list(instance["target_spec"]["target_state_ids"])
    visible = {turn["turn_id"] for turn in instance["input"].get("history", [])}
    current_turn_id = instance["input"].get("current_observation", {}).get("turn_id")
    if current_turn_id:
        visible.add(current_turn_id)
    for option in options:
        if set(option) != {"action_index", "state_predictions"}:
            raise ValueError("T3 option keys")
        rows = option["state_predictions"]
        if (
            not isinstance(rows, list)
            or len(rows) != len(state_ids)
            or {row.get("state_id") for row in rows} != set(state_ids)
        ):
            raise ValueError("T3 state coverage")
        for row in rows:
            if set(row) != {
                "state_id", "immediate", "delayed", "evidence_turn_ids",
            }:
                raise ValueError("T3 state prediction keys")
            validate_probabilities(row["immediate"])
            validate_probabilities(row["delayed"])
            evidence = row["evidence_turn_ids"]
            if (
                not isinstance(evidence, list)
                or len(set(evidence)) != len(evidence)
                or not set(evidence) <= visible
            ):
                raise ValueError("T3 evidence turn ids")
        rows.sort(key=lambda row: state_ids.index(row["state_id"]))
    options.sort(key=lambda row: row["action_index"])
    return value


def generate_answer(
    provider, instance, seed, *, private_persona=None, max_attempts=3,
):
    instance = canonicalize_instance(instance)
    start = call_count(provider)
    answer = complete_json(
        provider,
        [{"role": "user", "content": answer_prompt(instance, private_persona)}],
        {"temperature": 0.15, "top_p": 0.9, "seed": seed},
        lambda value: validate_answer(value, instance),
        context=f"T3 answer {instance['instance_id']}",
        max_attempts=max_attempts,
        retry_guidance=(
            "Cover each action and target state exactly once. Every immediate and "
            "delayed probability object must use all direction labels and sum to 1."
        ),
    )
    return answer, call_count(provider) - start
