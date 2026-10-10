"""Generate a machine T4 judgment from a completed public trajectory."""

from __future__ import annotations

from evaluation.t4_evaluation import public_t4_judge_packet, validate_t4_judgment
from prompts.loader import render_prompt
from providers.structured import complete_json
from tasks.T2.runtime import call_count


def generate_judgment(provider, trajectory, scenario, seed, *, max_attempts=3,
                      observation_condition="text_only", sampling=None):
    packet = public_t4_judge_packet(trajectory, scenario)
    messages = build_judge_messages(packet, trajectory, observation_condition)
    valid_turn_ids = [turn["turn_id"] for turn in trajectory["turns"]]
    start = call_count(provider)
    judgment = complete_json(
        provider,
        messages,
        {"temperature": 0.1, "top_p": 0.9, **(sampling or {}), "seed": seed},
        lambda value: validate_t4_judgment(value, valid_turn_ids),
        context=f"T4 judgment {trajectory['trajectory_id']}",
        max_attempts=max_attempts,
        retry_guidance=(
            "Use exactly the five dimensions. Cite only visible turn IDs and keep "
            "automatic human_validation_status set to not_human_validated."
        ),
    )
    return packet, judgment, call_count(provider) - start


def build_judge_messages(packet, trajectory, observation_condition="text_only"):
    """Keep judge evidence separate from the evaluated policy's condition.

    Default text judging is blind to policy modality. Video judging adds actual
    video blocks; never serialize cue descriptions or planned asset metadata.
    """
    prompt = render_prompt("t4_judge_v2", packet)
    if observation_condition == "text_only":
        return [{"role": "user", "content": prompt}]
    if observation_condition != "text_video":
        raise ValueError("invalid T4 judge observation condition")
    content = [{"type": "text", "text": prompt}]
    for turn in trajectory["turns"]:
        for media in turn.get("media", []):
            if media.get("media_type") != "video":
                continue
            url = media.get("asset_url")
            if media.get("asset_status") != "available" or not isinstance(url, str) or not url.startswith("https://"):
                raise ValueError("T4 video judging requires available HTTPS video assets")
            content.extend([
                {"type": "text", "text": f"Observed video after {turn['turn_id']}:"},
                {"type": "video_url", "video_url": {"url": url}},
            ])
    if len(content) == 1:
        raise ValueError("T4 text_video judging requires at least one actual video")
    return [{"role": "user", "content": content}]
