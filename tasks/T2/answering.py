"""Generate and structurally validate machine answers for T2 instances."""

from __future__ import annotations

import json

from providers.structured import complete_json
from scripts.t2_common import DIRECTIONS, call_count


def answer_prompt(instance):
    visible_ids = [turn["turn_id"] for turn in instance["input"]["history_a"]]
    example_turn = visible_ids[0]
    schema = {
        "instance_id": instance["instance_id"],
        "selected_state_ids": ["state.id"],
        "predictions": [{
            "state_id": "state.id",
            "direction_probabilities": {
                "higher_in_a": 0.0,
                "similar": 0.0,
                "higher_in_b": 0.0,
                "cannot_determine": 0.0,
            },
            "evidence_a": [{
                "turn_id": example_turn,
                "target_quote": "目标角色在该轮的原话",
                "interpretation": "该原话如何支持判断",
            }],
            "evidence_b": [{
                "turn_id": example_turn,
                "target_quote": "目标角色在该轮的原话",
                "interpretation": "该原话如何支持判断",
            }],
            "key_history_events_a": [example_turn],
            "key_history_events_b": [example_turn],
            "rationale": "只根据公开证据解释",
            "confidence": 0.0,
        }],
        "shared_expression_explanation": {
            "history_a": "相同表达在 A 中可能承担的沟通功能",
            "history_b": "相同表达在 B 中可能承担的沟通功能",
            "uncertainty": "替代解释或证据边界",
        },
        "history_necessity": {
            "judgment": "necessary",
            "explanation": "去掉历史后为何失去关键依据",
        },
    }
    return (
        "你为 SocialFlux T2 生成候选答案，答案之后由人判断正确与否，不是自动 GT。只能使用"
        "公开 History A/B、相同 shared ending 和 target_spec，不得读取后台状态。判断对象是"
        "input.target_character，也就是 environment_character；evaluated_agent 的言行只能作为"
        "影响目标角色的事件，不能冒充目标角色状态证据。从候选变量中优先选 1–3 个有双侧证据的"
        "变量。如果只有一侧存在可引用的目标角色证据，允许另一侧 evidence 和 key events 为空，"
        "但 cannot_determine 必须是最高概率；两侧都没有证据的变量不要选择。微笑不自动等于高兴，"
        "同意不自动等于信任恢复。"
        f"证据 turn_id 只能来自 {visible_ids}，target_quote 必须逐字摘自对应侧、对应轮的 "
        "environment_character。四项概率之和为 1。只输出以下 JSON 且不增加字段：\n"
        + json.dumps(schema, ensure_ascii=False)
        + "\nT2 实例：\n"
        + json.dumps(instance, ensure_ascii=False, sort_keys=True)
    )


def validate_answer(value, instance):
    expected = {
        "instance_id", "selected_state_ids", "predictions",
        "shared_expression_explanation", "history_necessity",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("T2 answer top keys")
    if value["instance_id"] != instance["instance_id"]:
        raise ValueError("T2 answer instance id")
    candidates = set(instance["target_spec"]["candidate_state_ids"])
    selected = value["selected_state_ids"]
    if not isinstance(selected, list) or not 1 <= len(selected) <= 3:
        raise ValueError("T2 selected state count")
    if len(set(selected)) != len(selected) or not set(selected) <= candidates:
        raise ValueError("T2 selected state ids")
    predictions = value["predictions"]
    if not isinstance(predictions, list) or {
        row.get("state_id") for row in predictions
    } != set(selected):
        raise ValueError("T2 prediction coverage")
    visible = {turn["turn_id"] for turn in instance["input"]["history_a"]}
    row_keys = {
        "state_id", "direction_probabilities", "evidence_a", "evidence_b",
        "key_history_events_a", "key_history_events_b", "rationale", "confidence",
    }
    for row in predictions:
        if set(row) != row_keys:
            raise ValueError("T2 prediction keys")
        probabilities = row["direction_probabilities"]
        if set(probabilities) != set(DIRECTIONS):
            raise ValueError("T2 direction keys")
        if any(not isinstance(x, (int, float)) or not 0 <= x <= 1 for x in probabilities.values()):
            raise ValueError("T2 direction values")
        if abs(sum(probabilities.values()) - 1.0) > 0.02:
            raise ValueError("T2 direction probabilities")
        for side, key in (("a", "evidence_a"), ("b", "evidence_b")):
            evidence = row[key]
            if not isinstance(evidence, list) or len(evidence) > 3:
                raise ValueError(f"T2 invalid {key}")
            history = {
                turn["turn_id"]: turn["environment_character"]
                for turn in instance["input"][f"history_{side}"]
            }
            for citation in evidence:
                if not isinstance(citation, dict) or set(citation) != {
                    "turn_id", "target_quote", "interpretation",
                }:
                    raise ValueError(f"T2 invalid {key} citation")
                turn_id = citation["turn_id"]
                quote = str(citation["target_quote"]).strip()
                if turn_id not in visible or turn_id not in history:
                    raise ValueError(f"T2 invalid {key} turn")
                if not quote or quote not in history[turn_id]:
                    raise ValueError(f"T2 {key} quote is not target speech")
                if not str(citation["interpretation"]).strip():
                    raise ValueError(f"T2 invalid {key} interpretation")
        for key in ("key_history_events_a", "key_history_events_b"):
            if not isinstance(row[key], list) or not set(row[key]) <= visible:
                raise ValueError(f"T2 invalid {key}")
        if not row["evidence_a"] and not row["evidence_b"]:
            raise ValueError("T2 selected state has no public evidence")
        one_side_missing = not row["evidence_a"] or not row["evidence_b"]
        other_directions = [
            probabilities[key] for key in DIRECTIONS
            if key != "cannot_determine"
        ]
        if one_side_missing and probabilities["cannot_determine"] < max(other_directions):
            raise ValueError("T2 missing-side evidence requires cannot_determine")
        if row["evidence_a"] and not row["key_history_events_a"]:
            raise ValueError("T2 evidence_a requires key history event")
        if row["evidence_b"] and not row["key_history_events_b"]:
            raise ValueError("T2 evidence_b requires key history event")
        if not str(row["rationale"]).strip():
            raise ValueError("T2 rationale")
        if not isinstance(row["confidence"], (int, float)) or not 0 <= row["confidence"] <= 1:
            raise ValueError("T2 confidence")
    expression = value["shared_expression_explanation"]
    if set(expression) != {"history_a", "history_b", "uncertainty"}:
        raise ValueError("T2 expression keys")
    if any(not str(expression[key]).strip() for key in expression):
        raise ValueError("T2 expression explanation")
    necessity = value["history_necessity"]
    if set(necessity) != {"judgment", "explanation"}:
        raise ValueError("T2 history necessity keys")
    if necessity["judgment"] not in {"necessary", "partially_necessary", "not_demonstrated"}:
        raise ValueError("T2 history necessity judgment")
    if not str(necessity["explanation"]).strip():
        raise ValueError("T2 history necessity explanation")
    return value


def generate_answer(provider, instance, seed, *, max_attempts=3):
    answer = complete_json(
        provider,
        [{"role": "user", "content": answer_prompt(instance)}],
        {"temperature": 0.2, "top_p": 0.9, "seed": seed},
        lambda value: validate_answer(value, instance),
        context=f"T2 answer {instance['instance_id']}",
        max_attempts=max_attempts,
        retry_guidance=(
            "Cite only target-character quotations from the visible side and turn. Select one to "
            "three supported candidate states and make the four probabilities sum to one."
        ),
    )
    return answer, call_count(provider)
