"""Generate leakage-safe machine proposals for SocialFlux T3."""

from __future__ import annotations

from copy import deepcopy
import json

from prompts.loader import render_prompt
from providers.structured import complete_json
from tasks.T2.runtime import call_count
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


def answer_prompt(instance, private_persona=None, condition="main"):
    if instance.get("benchmark_version") == "socialflux_offline_choice_v1":
        from tasks.offline_choice import answer_prompt as choice_prompt
        return choice_prompt(instance)
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
    oracle_instruction = ""
    if condition == "oracle_state_ablation":
        oracle_instruction = (
            "这是独立 Oracle-State ablation，不属于主任务。可以读取 input.oracle_state，"
            "但不得把 oracle 条件或私有数值写入公开证据；答案必须保留同样的输出合同。"
        )
    elif condition != "main":
        raise ValueError(f"unsupported T3 answer condition: {condition}")
    private_section = (
        "作者侧私有 Persona（仅用于条件化解释，不得作为公开证据引用或写入答案）：\n"
        + json.dumps(private_persona, ensure_ascii=False, sort_keys=True)
        if private_persona is not None else ""
    )
    return render_prompt(
        "task_t3_v1",
        instance,
        condition_instruction=oracle_instruction,
        output_schema_json=json.dumps(schema, ensure_ascii=False),
        private_persona_section=private_section,
    )


def validate_answer(value, instance):
    if instance.get("benchmark_version") == "socialflux_offline_choice_v1":
        from tasks.offline_choice import parse_answer
        parsed = parse_answer(json.dumps(value), instance["options"])
        if parsed["format_error"]:
            raise ValueError(parsed["format_error"])
        return {"answer": parsed["answer"]}
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
    condition="main",
):
    if instance.get("benchmark_version") == "socialflux_offline_choice_v1":
        from tasks.offline_choice import generate_answer as choice_answer
        return choice_answer(provider, instance, seed)
    instance = canonicalize_instance(instance)
    start = call_count(provider)
    answer = complete_json(
        provider,
        [{"role": "user", "content": answer_prompt(instance, private_persona, condition)}],
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
