"""Semantic reviews for T2 pairs and answers.

The pair review records every environment turn as read, but emits detailed
annotations only for actual problems.  Reviews never claim human acceptance and
never rewrite dialogue to force a pass.
"""

from __future__ import annotations

import json

from providers.structured import complete_json
from providers.base import call_count
ENVIRONMENT_ISSUE_CATEGORIES = {
    "empty_repetition",
    "request_omission",
    "action_ownership",
    "unsupported_fact_or_institution",
    "promise_completion_confusion",
    "fact_contradiction",
    "character_or_motivation_break",
    "unnatural_response",
    "other",
}

PAIR_CHECKS = {
    "source_a_coherent",
    "history_b_coherent",
    "difference_locatable",
    "ending_natural_in_a",
    "ending_natural_in_b",
    "ownership_and_facts_sound",
    "no_sustained_empty_loop",
    "state_expression_link_supported",
    "history_is_necessary",
}


def reviewed_environment_turns(instance):
    expected = {}
    for side in ("A", "B"):
        for turn in instance["input"][f"history_{side.lower()}"]:
            expected[(side, turn["turn_id"])] = turn["environment_character"]
    ending_id = instance["input"]["shared_current_action"]["turn_id"]
    expected[("shared", ending_id)] = instance["input"][
        "shared_current_observation"
    ]["current_response"]
    return expected


def pair_review_prompt(pair):
    payload = {
        "source_provenance": pair["source_a"],
        "adaptation": pair["adaptation"],
        "public_instance": pair["instance"],
        "private_audit_only": {
            "state_a": pair["backend"]["state_a"],
            "state_b": pair["backend"]["state_b"],
            "expression_intent_a": pair["backend"]["expression_intent_a"],
            "expression_intent_b": pair["backend"]["expression_intent_b"],
            "program_checks": pair["program_checks"],
        },
    }
    return (
        "你是 SocialFlux T2 配对的模型语义复核者，不是人工验收。完整阅读 A、B 和共享 ending。"
        "判断人物和历史是否连贯、差异是否可定位、动作归属与事实边界是否正确、提案/承诺/完成是否"
        "混淆、请求是否被回应、是否持续空转、相同 ending 在两侧是否自然。必要确认不是空转，措辞"
        "不漂亮不是拒绝理由。后台状态只用于核验，不能代替正文证据。\n"
        "reviewed_environment_turns 必须列出 A/B 历史每轮及 shared ending，表示已逐句阅读；不要为"
        "正常台词写冗长评价。environment_issues 只列实际问题，必须逐字引用对应 environment_character"
        "片段，并标注类别和任务影响。严重污染状态或任务答案才 reject；局部明确问题为 needs_revision；"
        "没有可定位问题才 approve。只输出 JSON："
        '{"decision":"approve|needs_revision|reject","checks":{'
        + ",".join(f'"{key}":true' for key in sorted(PAIR_CHECKS))
        + '},"reviewed_environment_turns":[{"side":"A|B|shared","turn_id":"t1"}],'
        '"environment_issues":[{"side":"A|B|shared","turn_id":"t1",'
        '"categories":["empty_repetition"],"quote":"对应目标角色原话片段",'
        '"description":"具体问题","task_impact":"对状态或答案的影响"}],'
        '"rationale":"整体结论"}\n允许类别：'
        + json.dumps(sorted(ENVIRONMENT_ISSUE_CATEGORIES), ensure_ascii=False)
        + "\n复核材料：\n"
        + json.dumps(payload, ensure_ascii=False, sort_keys=True)
    )


def validate_pair_review(value, instance):
    keys = {
        "decision", "checks", "reviewed_environment_turns",
        "environment_issues", "rationale",
    }
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("T2 pair review top keys")
    if value["decision"] not in {"approve", "needs_revision", "reject"}:
        raise ValueError("T2 pair review decision")
    if set(value["checks"]) != PAIR_CHECKS or any(
        not isinstance(value["checks"][key], bool) for key in PAIR_CHECKS
    ):
        raise ValueError("T2 pair review checks")
    expected = reviewed_environment_turns(instance)
    reviewed = value["reviewed_environment_turns"]
    if not isinstance(reviewed, list) or any(
        not isinstance(row, dict) or set(row) != {"side", "turn_id"}
        for row in reviewed
    ):
        raise ValueError("T2 reviewed environment turns")
    reviewed_keys = [(row["side"], row["turn_id"]) for row in reviewed]
    if len(set(reviewed_keys)) != len(reviewed_keys) or set(reviewed_keys) != set(expected):
        raise ValueError("T2 reviewed environment turn coverage")
    issues = value["environment_issues"]
    if not isinstance(issues, list):
        raise ValueError("T2 environment issues")
    issue_keys = {
        "side", "turn_id", "categories", "quote", "description", "task_impact",
    }
    for issue in issues:
        if not isinstance(issue, dict) or set(issue) != issue_keys:
            raise ValueError("T2 environment issue keys")
        key = (issue["side"], issue["turn_id"])
        if key not in expected:
            raise ValueError("T2 environment issue reference")
        categories = issue["categories"]
        if not isinstance(categories, list) or not categories:
            raise ValueError("T2 environment issue categories")
        if not set(categories) <= ENVIRONMENT_ISSUE_CATEGORIES:
            raise ValueError("T2 environment issue category value")
        quote = str(issue["quote"]).strip()
        if not quote or quote not in expected[key]:
            raise ValueError("T2 environment issue quote")
        if not str(issue["description"]).strip() or not str(issue["task_impact"]).strip():
            raise ValueError("T2 environment issue explanation")
    if not str(value["rationale"]).strip():
        raise ValueError("T2 pair review rationale")
    return value


def review_pair(provider, pair, seed):
    review = complete_json(
        provider,
        [{"role": "user", "content": pair_review_prompt(pair)}],
        {"temperature": 0.1, "top_p": 0.9, "seed": seed},
        lambda value: validate_pair_review(value, pair["instance"]),
        context=f"T2 pair semantic review {pair['scenario_id']}",
        max_attempts=2,
        retry_guidance=(
            "List each A/B/shared environment turn exactly once in reviewed_environment_turns. "
            "Only actual problems belong in environment_issues, with a verbatim quote."
        ),
    )
    return review, call_count(provider)


ANSWER_CHECKS = {
    "target_role_correct",
    "evidence_side_and_quote_correct",
    "comparison_supported_by_public_history",
    "shared_expression_explanation_supported",
    "uncertainty_calibrated",
}


def answer_review_prompt(instance, answer):
    return (
        "你是 SocialFlux T2 机器答案复核者，不是人工验收，也不生成新答案。只根据公开 instance"
        "检查目标角色、A/B 引证侧别、比较方向、相同外在表达解释及不确定性。不得使用 latent 数值"
        "决定答案。问题引用具体 state_id/side/turn_id。只输出 JSON："
        '{"decision":"approve|needs_revision|reject","checks":{'
        + ",".join(f'"{key}":true' for key in sorted(ANSWER_CHECKS))
        + '},"issues":[{"state_id":"relationship.trust","side":"A|B|shared|answer",'
        '"turn_ids":["t1"],"description":"具体问题","task_impact":"如何影响答案"}],'
        '"rationale":"整体结论"}\n材料：\n'
        + json.dumps({"instance": instance, "llm_answer": answer}, ensure_ascii=False, sort_keys=True)
    )


def validate_answer_review(value):
    if not isinstance(value, dict) or set(value) != {"decision", "checks", "issues", "rationale"}:
        raise ValueError("T2 answer review top keys")
    if value["decision"] not in {"approve", "needs_revision", "reject"}:
        raise ValueError("T2 answer review decision")
    if set(value["checks"]) != ANSWER_CHECKS or any(
        not isinstance(value["checks"][key], bool) for key in ANSWER_CHECKS
    ):
        raise ValueError("T2 answer review checks")
    if not isinstance(value["issues"], list):
        raise ValueError("T2 answer review issues")
    for issue in value["issues"]:
        if set(issue) != {"state_id", "side", "turn_ids", "description", "task_impact"}:
            raise ValueError("T2 answer review issue keys")
        if issue["side"] not in {"A", "B", "shared", "answer"}:
            raise ValueError("T2 answer review issue side")
        if not isinstance(issue["turn_ids"], list):
            raise ValueError("T2 answer review turn ids")
    if not str(value["rationale"]).strip():
        raise ValueError("T2 answer review rationale")
    return value


def review_answer(provider, instance, answer, seed):
    review = complete_json(
        provider,
        [{"role": "user", "content": answer_review_prompt(instance, answer)}],
        {"temperature": 0.1, "top_p": 0.9, "seed": seed},
        validate_answer_review,
        context=f"T2 answer semantic review {instance['instance_id']}",
        max_attempts=2,
        retry_guidance="Cite concrete public turn IDs and do not call this human acceptance.",
    )
    return review, call_count(provider)
