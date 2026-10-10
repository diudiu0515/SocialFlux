"""Select and author a controlled T2 adaptation spec from one real rollout A."""

from __future__ import annotations

import json

from prompts.loader import render_prompt
from providers.structured import complete_json
from tasks.T2.runtime import call_count
from tasks.extraction import public_history


EXPRESSION_FIELDS = {
    "facial_expression",
    "gaze",
    "speech_style",
    "prosody",
    "behavioral_cues",
}


def candidate_windows(
    trajectory,
    *,
    minimum_shared_prefix_turns=2,
    minimum_branch_turns=2,
    maximum_branch_turns=4,
):
    turns = trajectory.get("turns", [])
    windows = []
    for fork_index in range(minimum_shared_prefix_turns, len(turns)):
        first_ending = fork_index + minimum_branch_turns
        last_ending = min(
            len(turns) - 1,
            fork_index + maximum_branch_turns,
        )
        for ending_index in range(first_ending, last_ending + 1):
            branch = turns[fork_index:ending_index]
            if any(turn.get("segment_transition_after") for turn in branch):
                continue
            windows.append({
                "fork_turn_id": turns[fork_index]["turn_id"],
                "ending_turn_id": turns[ending_index]["turn_id"],
                "prefix_turn_count": fork_index,
                "adapted_turn_count": ending_index - fork_index,
            })
    return windows


def spec_prompt(scenario, trajectory, windows):
    schema = {
        "fork_turn_id": windows[0]["fork_turn_id"],
        "ending_turn_id": windows[0]["ending_turn_id"],
        "adaptation_point": "改变哪段有研究意义的经历及其影响",
        "source_anchor_evidence": [{
            "turn_id": "A 分叉段中的轮次",
            "speaker": "evaluated_agent 或 environment_character",
        }],
        "history_b_direction": "B 如何自然改写关键经历并让同一 ending 仍可信",
        "protected_facts": ["必须保持不变的已成立公开事实"],
        "shared_ending_behavior": {
            "facial_expression": "客观可见表情",
            "gaze": "客观可见视线",
            "speech_style": "可听说话方式",
            "prosody": "可听韵律",
            "behavioral_cues": ["客观可见动作"],
        },
        "rationale": "为何这个窗口适合受控历史差异比较",
    }
    packet = {
        "scenario": {
            "scenario_id": scenario["scenario_id"],
            "background": scenario["background"],
            "evaluated_agent_role": scenario["evaluated_agent_role"],
            "target_character": scenario["environment_agent"]["persona"],
            "target_state_ids": scenario["target_state_ids"],
        },
        "observable_history_a": public_history(trajectory),
        "candidate_windows": windows,
    }
    return render_prompt(
        "task_t2_adaptation_spec_v1",
        packet,
        output_schema_json=json.dumps(schema, ensure_ascii=False),
    )


def validate_spec(value, windows, trajectory=None):
    required = {
        "fork_turn_id",
        "ending_turn_id",
        "adaptation_point",
        "source_anchor_evidence",
        "history_b_direction",
        "protected_facts",
        "shared_ending_behavior",
        "rationale",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("T2 adaptation spec fields mismatch")
    allowed = {
        (window["fork_turn_id"], window["ending_turn_id"])
        for window in windows
    }
    if (value["fork_turn_id"], value["ending_turn_id"]) not in allowed:
        raise ValueError("T2 adaptation spec selected an invalid window")
    evidence = value["source_anchor_evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("T2 adaptation spec source anchor evidence")
    enriched_evidence = []
    if trajectory is not None:
        turns = trajectory.get("turns", [])
        indexes = {turn["turn_id"]: index for index, turn in enumerate(turns)}
        fork_index = indexes[value["fork_turn_id"]]
        ending_index = indexes[value["ending_turn_id"]]
        for item in evidence:
            if not isinstance(item, dict) or set(item) != {"turn_id", "speaker"}:
                raise ValueError("T2 adaptation spec source anchor shape")
            turn_id = item["turn_id"]
            if turn_id not in indexes or not fork_index <= indexes[turn_id] < ending_index:
                raise ValueError("T2 adaptation spec source anchor outside branch")
            speaker = item["speaker"]
            turn = turns[indexes[turn_id]]
            if speaker == "evaluated_agent":
                source_text = (turn.get("policy_action") or {}).get("text", "")
            elif speaker == "environment_character":
                source_text = turn.get("environment_response", "")
            else:
                raise ValueError("T2 adaptation spec source anchor speaker")
            if not isinstance(source_text, str) or not source_text.strip():
                raise ValueError("T2 adaptation spec source anchor text missing")
            enriched_evidence.append({**item, "quote": source_text})
    else:
        for item in evidence:
            if not isinstance(item, dict) or set(item) != {"turn_id", "speaker"}:
                raise ValueError("T2 adaptation spec source anchor shape")
    for key in ("adaptation_point", "history_b_direction", "rationale"):
        if not str(value[key]).strip():
            raise ValueError(f"T2 adaptation spec missing {key}")
    facts = value["protected_facts"]
    if (
        not isinstance(facts, list)
        or not facts
        or any(not isinstance(item, str) or not item.strip() for item in facts)
    ):
        raise ValueError("T2 adaptation spec protected facts")
    behavior = value["shared_ending_behavior"]
    if not isinstance(behavior, dict) or set(behavior) != EXPRESSION_FIELDS:
        raise ValueError("T2 shared ending behavior fields")
    for key in EXPRESSION_FIELDS - {"behavioral_cues"}:
        if not isinstance(behavior[key], str) or not behavior[key].strip():
            raise ValueError(f"T2 shared ending behavior {key}")
    cues = behavior["behavioral_cues"]
    if (
        not isinstance(cues, list)
        or len(cues) > 3
        or any(not isinstance(item, str) or not item.strip() for item in cues)
    ):
        raise ValueError("T2 shared ending behavioral cues")
    result = dict(value)
    if trajectory is not None:
        result["source_anchor_evidence"] = enriched_evidence
    return result


def author_spec(provider, scenario, trajectory, seed, selection_settings=None):
    settings = selection_settings or {}
    windows = candidate_windows(
        trajectory,
        minimum_shared_prefix_turns=int(
            settings.get("minimum_shared_prefix_turns", 2)
        ),
        minimum_branch_turns=int(settings.get("minimum_branch_turns", 2)),
        maximum_branch_turns=int(settings.get("maximum_branch_turns", 4)),
    )
    if not windows:
        return None, 0
    start = call_count(provider)
    spec = complete_json(
        provider,
        [{"role": "user", "content": spec_prompt(scenario, trajectory, windows)}],
        {"temperature": 0.25, "top_p": 0.9, "seed": seed},
        lambda value: validate_spec(value, windows, trajectory),
        context=f"T2 adaptation spec {scenario['scenario_id']}",
        max_attempts=2,
        retry_guidance=(
            "Choose an exact candidate window and preserve public facts. "
            "Anchor the adaptation to exact speech inside the selected branch; "
            "do not invent an earlier event or off-screen history. "
            "Every facial_expression, gaze, speech_style, and prosody field must "
            "contain a short objective observation; do not leave them blank."
        ),
    )
    return spec, call_count(provider) - start
