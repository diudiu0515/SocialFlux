"""Author distinct, locally executable T3 candidate actions."""

from __future__ import annotations

import json

from prompts.loader import render_prompt
from providers.structured import complete_json
from providers.base import call_count
def action_prompt(checkpoint, count=3):
    schema = {
        "actions": [
            {"text": f"候选行动 {index + 1} 的完整直接台词", "strategy": "简短策略说明"}
            for index in range(count)
        ]
    }
    return render_prompt(
        "task_t3_action_candidates_v1",
        checkpoint,
        candidate_count=str(count),
        output_schema_json=json.dumps(schema, ensure_ascii=False),
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
