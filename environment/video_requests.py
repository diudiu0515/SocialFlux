"""Provider-neutral safe video request construction."""

from __future__ import annotations

from copy import deepcopy

from prompts.loader import render_prompt


TALKING_HEAD_PROMPT_ID = "talking_head_generation_v1"


def video_prompt(scenario, response, expression, variant=1):
    persona = scenario["environment_agent"]["persona"]
    cues = "；".join(str(item) for item in expression.get("behavioral_cues", []))
    variant_note = (
        "保持克制的近景构图，强调细微面部变化。"
        if variant % 2 == 1
        else "保持固定机位的中近景构图，强调视线与姿态变化。"
    )
    return render_prompt(
        TALKING_HEAD_PROMPT_ID,
        character_name=str(persona.get("name", "人物")),
        character_role=str(persona.get("role", "对话参与者")),
        variant_note=variant_note,
        public_response=str(response),
        facial_expression=str(
            expression.get("facial_expression", "自然克制")
        ),
        gaze=str(expression.get("gaze", "自然注视")),
        speech_style=str(expression.get("speech_style", "正常语速")),
        prosody=str(expression.get("prosody", "克制")),
        behavioral_cues=cues or "自然呼吸、眨眼和轻微头部动作",
    ).strip()


def build_video_request(
    scenario,
    response,
    expression,
    *,
    duration_seconds=5,
    continuity_reference=None,
    variant=1,
):
    response = str(response).strip()
    if not response:
        raise ValueError("video request requires a public response")
    if not isinstance(expression, dict) or not expression:
        raise ValueError("video request requires observable expression")
    duration_seconds = float(duration_seconds)
    if not 3 <= duration_seconds <= 8:
        raise ValueError("video duration must be between 3 and 8 seconds")
    if continuity_reference is not None and not isinstance(
        continuity_reference, str
    ):
        raise ValueError("video continuity reference must be a string or null")
    return {
        "prompt_id": TALKING_HEAD_PROMPT_ID,
        "prompt": video_prompt(scenario, response, expression, variant),
        "duration_seconds": duration_seconds,
        "continuity_reference": continuity_reference,
        "safety_check": {
            "contains_private_state": False,
            "contains_threshold_logic": False,
            "contains_benchmark_answer": False,
        },
    }


def attach_online_requests(scenario, multimodal, response):
    events = multimodal.get("private_events") or []
    expression = deepcopy(multimodal.get("observable_expression") or {})
    requests = []
    for event in events:
        event["observable_expression"] = deepcopy(expression)
        request = build_video_request(
            scenario,
            response,
            expression,
            duration_seconds=event.get("duration_seconds", 5),
        )
        event["video_api_request"] = request
        event["video_api_status"] = "request_ready"
        requests.append({
            "media_event_id": event["media_event_id"],
            "request": request,
            "status": "request_ready",
        })
    multimodal["video_api_requests"] = requests
    return multimodal
