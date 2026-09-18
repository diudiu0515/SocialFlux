"""Author distinct, locally executable T3 candidate actions."""

from __future__ import annotations

import json

from providers.structured import complete_json
from scripts.t2_common import call_count


def action_prompt(checkpoint, count=3):
    schema = {
        "actions": [
            {"text": f"候选行动 {index + 1} 的完整直接台词", "strategy": "简短策略说明"}
            for index in range(count)
        ]
    }
    return (
        "你为 SocialFlux T3 在同一公开 checkpoint 构造自由文本候选行动。候选属于被评估者，"
        "必须直接回应最新可观察上下文，在该时点可立即执行，并在策略上有实质区别。允许澄清、"
        "提出有边界的方案、拒绝、暂缓或关系修复；不要只做礼貌程度不同的同义改写。不得新增"
        "制度、权力、关键事实或已完成行动，不得偷走对方动作，不得读取 latent state 或未来。"
        f"恰好返回 {count} 个候选；text 只能是 1–3 句自然直接台词。只输出：\n"
        + json.dumps(schema, ensure_ascii=False)
        + "\n公开 checkpoint：\n"
        + json.dumps(checkpoint, ensure_ascii=False, sort_keys=True)
    )


def validate_actions(value, count=3):
    if not isinstance(value, dict) or set(value) != {"actions"}:
        raise ValueError("T3 action top keys")
    actions = value["actions"]
    if not isinstance(actions, list) or len(actions) != count:
        raise ValueError("T3 action count")
    if any(not isinstance(row, dict) or set(row) != {"text", "strategy"} for row in actions):
        raise ValueError("T3 action keys")
    texts = [str(row["text"]).strip() for row in actions]
    strategies = [str(row["strategy"]).strip() for row in actions]
    if any(not text or not strategy for text, strategy in zip(texts, strategies)):
        raise ValueError("T3 empty action")
    if len(set(texts)) != count or len(set(strategies)) != count:
        raise ValueError("T3 actions are not distinct")
    return value


def generate_actions(provider, checkpoint, seed, *, count=3, max_attempts=3):
    start = call_count(provider)
    result = complete_json(
        provider,
        [{"role": "user", "content": action_prompt(checkpoint, count)}],
        {"temperature": 0.35, "top_p": 0.9, "seed": seed},
        lambda value: validate_actions(value, count),
        context="T3 candidate action authoring",
        max_attempts=max_attempts,
        retry_guidance=(
            f"Return exactly {count} distinct, executable direct utterances and "
            "a distinct strategy description for each."
        ),
    )
    return result, call_count(provider) - start
