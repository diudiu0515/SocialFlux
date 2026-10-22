"""Author a complete alternative T2 history in one coherent model call."""

from __future__ import annotations

import json

from prompts.loader import render_prompt
from providers.structured import complete_json
from providers.base import call_count
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
    return render_prompt(
        "task_t2_controlled_branch_v1",
        payload,
        output_schema_json=json.dumps(schema, ensure_ascii=False),
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
