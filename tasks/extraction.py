"""Canonical T1/T3 checkpoint extraction from observable rollout history.

This module owns the production prompt, schema validation, and structured model
call. Benchmark scripts import it so model comparisons exercise the same path
used by later dataset construction.
"""

from __future__ import annotations

from copy import deepcopy
import json

from providers.structured import complete_json


def public_history(trajectory):
    return [
        {
            "turn_id": turn["turn_id"],
            "evaluated_agent": turn["policy_action"]["text"],
            "environment_character": turn["environment_response"],
            "observable_expression": deepcopy(turn.get("observable_expression", {})),
            "public_events_after": deepcopy(turn.get("public_events_after", [])),
        }
        for turn in trajectory["turns"]
    ]


def extraction_prompt(scenario, trajectory):
    packet = {
        "scenario_id": scenario["scenario_id"],
        "title": scenario["title"],
        "background": scenario["background"],
        "evaluated_role": {
            key: scenario["evaluated_agent_role"].get(key)
            for key in ("name", "role", "explicit_goal")
        },
        "target_character": {
            "name": scenario["environment_agent"]["persona"]["name"],
            "role": scenario["environment_agent"]["persona"]["role"],
        },
        "allowed_target_state_ids": scenario["target_state_ids"],
        "observable_history": public_history(trajectory),
    }
    example = {
        "t1": [{
            "checkpoint_turn_id": "t4",
            "target_state_ids": ["emotion.anxiety", "relationship.trust"],
            "evidence_turn_ids": ["t2", "t4"],
            "rationale": "why this checkpoint supports state inference",
        }],
        "t3": {
            "checkpoint_turn_id": "t3",
            "target_state_ids": ["motivation.resolve"],
            "future_turns_available": 5,
            "rationale": "why distinct actions could produce comparable consequences",
        },
    }
    return (
        "你为 SocialFlux 从一条完整公开互动中提取 T1/T3 构造点。"
        "只使用提供的公开历史，不推测隐藏动机或 latent 数值。T1 选择 1–2 个真正有历史证据的"
        "checkpoint；状态必须来自 allowed_target_state_ids，证据轮不得晚于 checkpoint。"
        "T3 选择一个尚有至少 5 个后续轮次、且当时确有多个可执行行动策略的 checkpoint；"
        "如果整条轨迹没有这样的 checkpoint，t3 必须返回 null，不能续写历史或缩短窗口。"
        "future_turns_available 必须等于该 checkpoint 后实际剩余的轮数。不要生成答案或候选台词。"
        "只返回与下例同结构的 JSON，不要增加字段：\n"
        + json.dumps(example, ensure_ascii=False)
        + "\n公开输入：\n"
        + json.dumps(packet, ensure_ascii=False, sort_keys=True)
    )


def validate_extraction(value, scenario, trajectory):
    if not isinstance(value, dict) or set(value) != {"t1", "t3"}:
        raise ValueError("task extraction top-level fields mismatch")
    valid_states = set(scenario["target_state_ids"])
    turn_ids = [turn["turn_id"] for turn in trajectory["turns"]]
    turn_index = {turn_id: index for index, turn_id in enumerate(turn_ids)}

    t1 = value["t1"]
    if not isinstance(t1, list) or not 1 <= len(t1) <= 2:
        raise ValueError("T1 extraction must contain one or two checkpoints")
    expected_t1_fields = {
        "checkpoint_turn_id", "target_state_ids", "evidence_turn_ids", "rationale",
    }
    for row in t1:
        if not isinstance(row, dict) or set(row) != expected_t1_fields:
            raise ValueError("T1 extraction fields mismatch")
        checkpoint = row["checkpoint_turn_id"]
        states = row["target_state_ids"]
        evidence = row["evidence_turn_ids"]
        if checkpoint not in turn_index:
            raise ValueError("T1 checkpoint does not exist")
        if not isinstance(states, list) or not 1 <= len(states) <= 3:
            raise ValueError("T1 target state count")
        if len(set(states)) != len(states) or not set(states) <= valid_states:
            raise ValueError("T1 target states are invalid")
        if not isinstance(evidence, list) or not 1 <= len(evidence) <= 4:
            raise ValueError("T1 evidence count")
        if len(set(evidence)) != len(evidence) or not set(evidence) <= set(turn_ids):
            raise ValueError("T1 evidence turn does not exist")
        if any(turn_index[item] > turn_index[checkpoint] for item in evidence):
            raise ValueError("T1 evidence occurs after checkpoint")
        if not str(row["rationale"]).strip():
            raise ValueError("T1 rationale is empty")

    t3 = value["t3"]
    if t3 is None:
        if len(turn_ids) >= 6:
            raise ValueError("T3 may be null only when no five-turn future window exists")
        return value
    expected_t3_fields = {
        "checkpoint_turn_id", "target_state_ids", "future_turns_available", "rationale",
    }
    if not isinstance(t3, dict) or set(t3) != expected_t3_fields:
        raise ValueError("T3 extraction fields mismatch")
    checkpoint = t3["checkpoint_turn_id"]
    if checkpoint not in turn_index:
        raise ValueError("T3 checkpoint does not exist")
    remaining = len(turn_ids) - turn_index[checkpoint] - 1
    if remaining < 5 or t3["future_turns_available"] != remaining:
        raise ValueError("T3 future window is incorrect or too short")
    states = t3["target_state_ids"]
    if (
        not isinstance(states, list)
        or not 1 <= len(states) <= 3
        or len(set(states)) != len(states)
        or not set(states) <= valid_states
    ):
        raise ValueError("T3 target states are invalid")
    if not str(t3["rationale"]).strip():
        raise ValueError("T3 rationale is empty")
    return value


def generate_extraction(
    provider,
    scenario,
    trajectory,
    *,
    seed,
    max_attempts=2,
):
    return complete_json(
        provider,
        [{"role": "user", "content": extraction_prompt(scenario, trajectory)}],
        {"temperature": 0.2, "top_p": 0.9, "seed": seed},
        lambda value: validate_extraction(value, scenario, trajectory),
        context=f"task extraction {scenario['scenario_id']}",
        max_attempts=max_attempts,
        retry_guidance=(
            "Use only listed state and turn IDs. Evidence cannot follow its T1 checkpoint. "
            "For T3, count all turns strictly after the checkpoint and require at least five; "
            "return t3=null when the trajectory is too short."
        ),
    )
