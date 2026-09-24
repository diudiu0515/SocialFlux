"""Provider-neutral safe video request construction."""

from __future__ import annotations

from copy import deepcopy
import math
import re

from prompts.loader import render_prompt


TALKING_HEAD_PROMPT_ID = "talking_head_generation_v1"
DEFAULT_EXPRESSION_POLICY = {
    "profile": "subtle_contextual_v1",
    "default_intensity": "low_to_moderate",
    "maximum_behavioral_cues": 2,
    "require_public_text_and_context_alignment": True,
    "allow_exaggerated_acting": False,
    "apply_cues_sequentially_when_possible": True,
}


def estimate_spoken_duration(response, *, minimum=3, maximum=15):
    """Estimate whole-second English speech plus natural lead/tail room."""
    text = str(response).strip()
    if not text:
        raise ValueError("video duration requires a public response")
    words = re.findall(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*", text)
    if not words:
        raise ValueError("video duration requires an English public response")
    # Calm dialogue is commonly near 2.5 words/second. One extra second
    # leaves room for a response beat, breath, and natural closing pause.
    seconds = 1 + math.ceil(len(words) / 2.5)
    return float(max(minimum, min(maximum, seconds)))


def video_prompt(
    scenario, response, expression, variant=1, expression_policy=None
):
    persona = scenario["environment_agent"]["persona"]
    policy = {**DEFAULT_EXPRESSION_POLICY, **(expression_policy or {})}
    cue_limit = int(policy["maximum_behavioral_cues"])
    if not 1 <= cue_limit <= 3:
        raise ValueError("maximum behavioral cues must be in 1..3")
    cue_items = [
        str(item).strip() for item in expression.get("behavioral_cues", [])
        if str(item).strip()
    ][:cue_limit]
    cues = "; ".join(cue_items)
    variant_note = (
        "Use a restrained close-up emphasizing subtle facial changes."
        if variant % 2 == 1
        else "Use a fixed medium close-up emphasizing gaze and posture changes."
    )
    return render_prompt(
        TALKING_HEAD_PROMPT_ID,
        character_name=str(persona.get("name", "the character")),
        character_role=str(persona.get("role", "conversation participant")),
        variant_note=variant_note,
        public_response=str(response),
        facial_expression=str(
            expression.get("facial_expression", "natural and restrained")
        ),
        gaze=str(expression.get("gaze", "natural eye contact")),
        speech_style=str(expression.get("speech_style", "natural pace")),
        prosody=str(expression.get("prosody", "restrained")),
        behavioral_cues=cues or "natural breathing, blinking, and subtle head movement",
        expression_intensity=str(policy["default_intensity"]).replace("_", "-"),
    ).strip()


def build_video_request(
    scenario,
    response,
    expression,
    *,
    duration_seconds=None,
    continuity_reference=None,
    variant=1,
    expression_policy=None,
):
    response = str(response).strip()
    if not response:
        raise ValueError("video request requires a public response")
    if not isinstance(expression, dict) or not expression:
        raise ValueError("video request requires observable expression")
    duration_seconds = float(
        estimate_spoken_duration(response)
        if duration_seconds is None
        else duration_seconds
    )
    if not 3 <= duration_seconds <= 15:
        raise ValueError("video duration must be between 3 and 15 seconds")
    if continuity_reference is not None and not isinstance(
        continuity_reference, str
    ):
        raise ValueError("video continuity reference must be a string or null")
    return {
        "prompt_id": TALKING_HEAD_PROMPT_ID,
        "prompt": video_prompt(
            scenario, response, expression, variant, expression_policy
        ),
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
