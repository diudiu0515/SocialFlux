"""Generate leakage-safe machine proposals for SocialFlux T1.

This module is the single owner of the T1 answer prompt and structural
validation.  Its outputs are machine proposals for human review, never ground
truth.
"""

from __future__ import annotations

import json

from providers.structured import complete_json
from scripts.t2_common import call_count
from tasks.T1.t1_probability_utils import (
    INTENSITY_LABELS,
    validate_probabilities as validate_intensity_probabilities,
)
from tasks.T3.t3_probability_utils import (
    DIRECTION_LABELS,
    validate_probabilities as validate_direction_probabilities,
)


def answer_prompt(instance, private_persona=None):
    target_ids = instance["target_spec"]["target_state_ids"]
    schema = {
        "instance_id": instance["instance_id"],
        "predictions": [
            {
                "state_id": state_id,
                "intensity_probabilities": {
                    label: 0.0 for label in INTENSITY_LABELS
                },
                "change_probabilities": {
                    label: 0.0 for label in DIRECTION_LABELS
                },
                "evidence_turn_ids": ["t1"],
                "confidence": 0.0,
            }
            for state_id in target_ids
        ],
    }
    return (
        "你为 SocialFlux T1 生成机器候选答案，之后由人判断正确与否；答案不是 GT。"
        "可以使用另附的作者侧私有 Persona 条件化解释，但它不是公开证据，不得引用或泄露。"
        "只使用 input 中公开可观察的完整历史与 current_checkpoint，判断对象严格是 "
        "target_character_id。不得读取或推测 latent state、appraisal、私有动机或未来事件。"
        "对每个 target_state_id 分别估计当前强度和相对最近有意义证据的变化方向；状态可以不变，"
        "不同状态可以朝不同方向变化。公开证据不足时应给 cannot_determine 较高概率，不要把"
        "微笑直接等同于高兴，也不要把口头同意直接等同于信任恢复或行动完成。evidence_turn_ids "
        "只能引用公开 history 中真实存在的 turn_id。每个概率对象的全部值之和必须为 1。"
        "只输出以下 JSON 结构，不增减字段：\n"
        + json.dumps(schema, ensure_ascii=False)
        + "\nT1 实例：\n"
        + json.dumps(instance, ensure_ascii=False, sort_keys=True)
        + (
            "\n作者侧私有 Persona（仅用于条件化解释，不得作为公开证据引用或写入答案）：\n"
            + json.dumps(private_persona, ensure_ascii=False, sort_keys=True)
            if private_persona is not None else ""
        )
    )


def validate_answer(value, instance):
    if not isinstance(value, dict) or set(value) != {"instance_id", "predictions"}:
        raise ValueError("T1 answer top keys")
    if value["instance_id"] != instance["instance_id"]:
        raise ValueError("T1 answer instance id")
    target_ids = list(instance["target_spec"]["target_state_ids"])
    rows = value["predictions"]
    if not isinstance(rows, list) or len(rows) != len(target_ids):
        raise ValueError("T1 prediction count")
    if {row.get("state_id") for row in rows} != set(target_ids):
        raise ValueError("T1 state coverage")
    visible = {
        turn["turn_id"] for turn in instance["input"].get("history", [])
    }
    expected = {
        "state_id", "intensity_probabilities", "change_probabilities",
        "evidence_turn_ids", "confidence",
    }
    for row in rows:
        if set(row) != expected:
            raise ValueError("T1 prediction keys")
        validate_intensity_probabilities(row["intensity_probabilities"])
        validate_direction_probabilities(row["change_probabilities"])
        evidence = row["evidence_turn_ids"]
        if (
            not isinstance(evidence, list)
            or len(set(evidence)) != len(evidence)
            or not set(evidence) <= visible
        ):
            raise ValueError("T1 evidence turn ids")
        confidence = row["confidence"]
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0 <= confidence <= 1
        ):
            raise ValueError("T1 confidence")
    rows.sort(key=lambda row: target_ids.index(row["state_id"]))
    return value


def generate_answer(
    provider, instance, seed, *, private_persona=None, max_attempts=3,
):
    start = call_count(provider)
    answer = complete_json(
        provider,
        [{"role": "user", "content": answer_prompt(instance, private_persona)}],
        {"temperature": 0.15, "top_p": 0.9, "seed": seed},
        lambda value: validate_answer(value, instance),
        context=f"T1 answer {instance['instance_id']}",
        max_attempts=max_attempts,
        retry_guidance=(
            "Cover every target state exactly once. Use all required probability "
            "labels and make each probability object sum to 1. Cite visible turn IDs only."
        ),
    )
    return answer, call_count(provider) - start
