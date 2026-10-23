"""Provider-neutral assets for response-neutral online multimodal cues."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from prompts.loader import render_prompt

from .online_multimodal import ONLINE_EVENT_FAMILIES
from .state_performance import FAMILY, online_prompt, fresh_performance_prompt


ONLINE_NONVERBAL_PROMPT_ID = "online_nonverbal_state_performance_v4"
ONLINE_ASSET_REQUEST_FORMAT = "socialflux_online_nonverbal_video_request_v1"


def active_online_manifest(root):
    """Explicit activation; historical task IDs never silently change files."""
    root = Path(root).resolve()
    config_path = root / 'configs/online_multimodal_assets.json'
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    selected = config.get('active_manifest', 'data/gpt50/experiment/multimodal_delivery_v1/online_multimodal/manifest.json')
    path = (root / selected).resolve()
    if not path.is_relative_to(root / 'data/gpt50/experiment') or path.name != 'manifest.json':
        raise ValueError('Invalid active online asset manifest')
    return path

_AGE = (
    "late twenties",
    "early thirties",
    "late thirties",
    "early forties",
    "late forties",
)
_FACE = ("oval", "angular", "round", "long", "broad", "heart-shaped")
_HAIR = (
    "short straight black hair",
    "short wavy dark-brown hair",
    "close-cropped salt-and-pepper hair",
    "medium-length curly black hair",
    "short auburn hair",
    "shoulder-length dark-brown hair tied back",
    "short tightly curled dark hair",
    "medium-length straight chestnut hair",
)
_DETAIL = (
    "thin dark rectangular glasses",
    "thin round metal glasses",
    "no eyewear and a faint cheek dimple",
    "no eyewear and a subtle eyebrow asymmetry",
    "no eyewear and a small beauty mark near one cheek",
    "clear-frame glasses",
)
_WARDROBE = (
    "a charcoal overshirt over a plain slate top",
    "a muted navy cardigan over a plain cream top",
    "a dark olive jacket over a plain black top",
    "a soft gray blazer over a plain blue top",
    "a burgundy knit layer over a plain neutral top",
    "a sand-colored jacket over a plain dark top",
    "a muted teal overshirt over a plain gray top",
)
_BACKGROUND = (
    "a softly lit generic office wall with no visible text",
    "a neutral consultation-room wall with an unbranded lamp",
    "a quiet generic workspace with a plain blurred shelf",
    "a restrained meeting-room background with no logos",
    "a neutral operations-room wall with indistinct unbranded fixtures",
)


def _canonical_sha256(value):
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _ascii_text(value, fallback):
    value = str(value or "").strip()
    return value if value and value.isascii() else fallback


def online_identity_spec(scenario):
    """Create one deterministic, fictional continuity specification per scenario."""
    persona = scenario.get("environment_agent", {}).get("persona", {})
    identity_source = {
        "scenario_id": scenario.get("scenario_id"),
        "name": persona.get("name"),
        "role": persona.get("role"),
    }
    digest_hex = _canonical_sha256(identity_source)
    digest = bytes.fromhex(digest_hex)
    appearance = (
        f"an adult in their {_AGE[digest[0] % len(_AGE)]} with a "
        f"{_FACE[digest[1] % len(_FACE)]} face, "
        f"{_HAIR[digest[2] % len(_HAIR)]}, and "
        f"{_DETAIL[digest[3] % len(_DETAIL)]}"
    )
    return {
        "identity_id": (
            f"{scenario.get('scenario_id')}:fictional_identity_v1:"
            f"{digest_hex[:12]}"
        ),
        "character_name": _ascii_text(
            persona.get("name"), "the scenario character"
        ),
        "character_role": _ascii_text(
            persona.get("role"), "conversation participant"
        ),
        "appearance": appearance,
        "wardrobe": _WARDROBE[digest[4] % len(_WARDROBE)],
        "background": _BACKGROUND[digest[5] % len(_BACKGROUND)],
        "camera": "fixed eye-level medium close-up, 16:9, natural soft lighting",
    }


def online_asset_prompt(
    scenario,
    event_family,
    *,
    preserve_reference_motion=False,
    duration_seconds=4,
    identity_override=None,
):
    if event_family not in ONLINE_EVENT_FAMILIES:
        raise ValueError(f"unknown online event family: {event_family}")
    identity = identity_override or online_identity_spec(scenario)
    return render_prompt(ONLINE_NONVERBAL_PROMPT_ID,
                         performance_direction=online_prompt(identity, event_family, duration_seconds)).strip()


def build_online_asset_request(
    scenario,
    event_family,
    *,
    duration_seconds=4,
    reference_video_file=None,
    preserve_reference_motion=False,
    identity_override=None,
):
    duration = float(duration_seconds)
    if not 4 <= duration <= 15:
        raise ValueError("online nonverbal video duration must be in 4..15 seconds")
    if reference_video_file is not None:
        reference_video_file = str(reference_video_file).strip()
        if not reference_video_file:
            raise ValueError("reference_video_file cannot be empty")
    request = {
        "format": ONLINE_ASSET_REQUEST_FORMAT,
        "prompt_id": ONLINE_NONVERBAL_PROMPT_ID,
        "prompt": online_asset_prompt(
            scenario,
            event_family,
            preserve_reference_motion=preserve_reference_motion,
            duration_seconds=duration,
            identity_override=identity_override,
        ),
        "duration_seconds": duration,
        "generate_audio": True,
        "ratio": "16:9",
        "scenario_id": scenario.get("scenario_id"),
        "event_family": event_family,
        "identity": identity_override or online_identity_spec(scenario),
        "reference_video_file": reference_video_file,
        "audio": {
            "required": True,
            "mode": "synchronized_response_neutral_nonverbal",
            "direction": FAMILY[event_family]['audio'],
            "spoken_content": False,
        },
        "safety_check": {
            "contains_spoken_content": False,
            "contains_response_text": False,
            "contains_private_state": False,
            "contains_threshold_logic": False,
            "contains_benchmark_answer": False,
        },
    }
    if reference_video_file and not preserve_reference_motion:
        request['prompt'] = fresh_performance_prompt(request['prompt'], duration=duration, event_family=event_family)
    return request
