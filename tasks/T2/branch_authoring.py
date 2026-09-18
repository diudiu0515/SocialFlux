"""Author a complete alternative T2 history in one coherent model call."""

from __future__ import annotations

import json

from providers.structured import complete_json
from scripts.t2_common import call_count


def branch_prompt(spec, scenario, shared_prefix, source_tail, shared_ending):
    expected_ids = [turn["turn_id"] for turn in source_tail]
    schema = {
        "turns": [{
            "turn_id": turn_id,
            "evaluated_agent": "该轮受评角色直接台词",
            "environment_character": "该轮对方直接台词",
        } for turn_id in expected_ids],
        "authoring_summary": "B 与 A 的关键经历差异及为何 ending 仍自然",
    }
    payload = {
        "scenario": {
            "background": scenario["background"],
            "evaluated_agent_role": scenario["evaluated_agent_role"],
            "environment_agent": scenario["environment_agent"],
        },
        "shared_prefix": shared_prefix,
        "source_history_a_suffix": source_tail,
        "adaptation_point": spec["adaptation_point"],
        "source_anchor_evidence": spec.get("source_anchor_evidence", []),
        "history_b_direction": spec["history_b_direction"],
        "protected_facts": spec["protected_facts"],
        "shared_ending": shared_ending,
    }
    return (
        "为 SocialFlux T2 一次性编写完整 History B 分叉段。它与 A 共享人物、背景、分叉前历史和"
        "关键事实，只改写指定的关键经历。两个人都必须根据前文自然回应；允许克制、误解、澄清、"
        "拒绝或有限让步。不要逐轮套用固定节奏，不要为了制造差异新增制度、证据、权力或已经完成的"
        "行动，不要替对方执行动作。提案、承诺、行为报告和可核验结果必须区分。"
        "分叉段不跨公开时间/事件边界，视为同一次接触；不要让新提出的未来期限在相邻轮次自动到达，"
        "也不要把尚未到期的承诺写成已经履约或违约。"
        "最后给定的 shared ending 在 A/B 两边都要自然，但不要提前复述 ending。只输出指定 JSON，"
        "不输出隐藏状态或"
        "构造说明到人物台词中。\n输出结构：\n"
        + json.dumps(schema, ensure_ascii=False)
        + "\n材料：\n"
        + json.dumps(payload, ensure_ascii=False, sort_keys=True)
    )


def validate_authored_branch(value, expected_turn_ids, source_tail):
    if not isinstance(value, dict) or set(value) != {"turns", "authoring_summary"}:
        raise ValueError("branch authoring top keys")
    if not str(value["authoring_summary"]).strip():
        raise ValueError("branch authoring summary")
    turns = value["turns"]
    if not isinstance(turns, list) or len(turns) != len(expected_turn_ids):
        raise ValueError("branch turn count")
    if [turn.get("turn_id") for turn in turns] != list(expected_turn_ids):
        raise ValueError("branch turn ids")
    for turn in turns:
        if set(turn) != {"turn_id", "evaluated_agent", "environment_character"}:
            raise ValueError("branch turn keys")
        for role in ("evaluated_agent", "environment_character"):
            text = str(turn[role]).strip()
            if not text or len(text) > 320 or "\n" in text:
                raise ValueError(f"branch {role} format")
    source_pairs = [
        (turn["evaluated_agent"], turn["environment_character"])
        for turn in source_tail
    ]
    branch_pairs = [
        (turn["evaluated_agent"], turn["environment_character"])
        for turn in turns
    ]
    if branch_pairs == source_pairs:
        raise ValueError("branch is identical to source history")
    return value


def author_branch(provider, spec, scenario, shared_prefix, source_tail, shared_ending, seed):
    expected = [turn["turn_id"] for turn in source_tail]
    authored = complete_json(
        provider,
        [{"role": "user", "content": branch_prompt(
            spec, scenario, shared_prefix, source_tail, shared_ending,
        )}],
        {"temperature": 0.45, "top_p": 0.9, "seed": seed},
        lambda value: validate_authored_branch(value, expected, source_tail),
        context=f"T2 complete branch authoring {scenario['scenario_id']}",
        max_attempts=2,
        retry_guidance=(
            "Return the complete branch once, with exactly the requested turn IDs and two direct "
            "utterances per turn. Preserve protected facts and do not report an unobserved completion."
        ),
    )
    return authored, call_count(provider)
