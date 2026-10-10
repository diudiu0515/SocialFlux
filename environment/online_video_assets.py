"""Provider-neutral assets for response-neutral online multimodal cues."""

from __future__ import annotations

import hashlib
import json

from prompts.loader import render_prompt

from .online_multimodal import ONLINE_EVENT_FAMILIES


ONLINE_NONVERBAL_PROMPT_ID = "online_nonverbal_event_v3"
ONLINE_ASSET_REQUEST_FORMAT = "socialflux_online_nonverbal_video_request_v1"

_FAMILY_DIRECTIONS = {
    "activated_tension": (
        "Clearly draw the eyebrows together, set the jaw with closed lips, raise "
        "both shoulders visibly, and hold a fixed forward gaze for one full second."
    ),
    "easing_tension": (
        "Begin visibly tense, then recline the upper body backward by about twenty "
        "centimeters, interlace both hands behind the head with elbows fully visible, "
        "close both eyes during one long exhale, and hold this relaxed posture."
    ),
    "open_engagement": (
        "Lean the upper body forward by about fifteen centimeters, establish direct "
        "eye contact, raise one open hand beside the face, wave it side-to-side two "
        "clear times, then lower the hand and give one natural nod."
    ),
    "guarded_withdrawal": (
        "Turn the head and upper torso about forty-five degrees to one side, break "
        "eye contact completely, and hold that visibly withdrawn pose for two seconds."
    ),
    "firm_boundary": (
        "Straighten fully, square both shoulders, fold both forearms firmly across "
        "the chest, keep the chin level, and hold a steady direct gaze with a "
        "closed jaw for two seconds."
    ),
    "risk_concern": (
        "Remain facing forward, then recoil backward by about fifteen centimeters "
        "while quickly raising both open hands beside the lower cheeks; widen the "
        "eyes, raise the eyebrows high, and freeze in this alert pose for two seconds."
    ),
    "cautious_relief": (
        "Briefly sweep one hand across the forehead, lower that hand fully, drop "
        "both shoulders visibly, then show a closed-mouth half-smile and finish "
        "with one gentle nod."
    ),
}

_FAMILY_AUDIO_DIRECTIONS = {
    "activated_tension": (
        "one short nasal inhale with a faint clothing-tension rustle, then quiet "
        "held breathing; no words or voiced syllables"
    ),
    "easing_tension": (
        "one clearly audible slow unvoiced exhale synchronized with reclining and "
        "placing both hands behind the head; no words or voiced syllables"
    ),
    "open_engagement": (
        "a soft chair-and-clothing shift during the forward lean, followed by calm "
        "quiet breathing; no hum, words, or voiced syllables"
    ),
    "guarded_withdrawal": (
        "one brief fabric rustle and soft chair creak synchronized with the turn "
        "away, followed by quiet room tone; no words or voiced syllables"
    ),
    "firm_boundary": (
        "one soft chair-settling sound as the posture straightens, then steady quiet "
        "breathing; no hum, words, or voiced syllables"
    ),
    "risk_concern": (
        "one sharp involuntary unvoiced inhale synchronized with the recoil, plus a "
        "brief clothing rustle; no scream, words, or voiced syllables"
    ),
    "cautious_relief": (
        "one audible unvoiced relieved exhale with a soft sleeve rustle during the "
        "forehead sweep; no hum, words, or voiced syllables"
    ),
}

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
):
    if event_family not in ONLINE_EVENT_FAMILIES:
        raise ValueError(f"unknown online event family: {event_family}")
    identity = online_identity_spec(scenario)
    return render_prompt(
        ONLINE_NONVERBAL_PROMPT_ID,
        character_name=identity["character_name"],
        character_role=identity["character_role"],
        appearance=identity["appearance"],
        wardrobe=identity["wardrobe"],
        background=identity["background"],
        camera=identity["camera"],
        reference_instruction=(
            "Use the reference video as the approved visual performance: preserve "
            "its identity, framing, target movement, and timing closely while "
            "adding the required synchronized nonverbal audio."
            if preserve_reference_motion
            else "If a reference video is supplied, use it for identity, wardrobe, "
            "background, and camera continuity, but perform the target movement "
            "specified below clearly."
        ),
        family_direction=_FAMILY_DIRECTIONS[event_family],
        audio_direction=_FAMILY_AUDIO_DIRECTIONS[event_family],
    ).strip()


def build_online_asset_request(
    scenario,
    event_family,
    *,
    duration_seconds=4,
    reference_video_file=None,
    preserve_reference_motion=False,
):
    duration = float(duration_seconds)
    if not 4 <= duration <= 15:
        raise ValueError("online nonverbal video duration must be in 4..15 seconds")
    if reference_video_file is not None:
        reference_video_file = str(reference_video_file).strip()
        if not reference_video_file:
            raise ValueError("reference_video_file cannot be empty")
    return {
        "format": ONLINE_ASSET_REQUEST_FORMAT,
        "prompt_id": ONLINE_NONVERBAL_PROMPT_ID,
        "prompt": online_asset_prompt(
            scenario,
            event_family,
            preserve_reference_motion=preserve_reference_motion,
        ),
        "duration_seconds": duration,
        "generate_audio": True,
        "ratio": "16:9",
        "scenario_id": scenario.get("scenario_id"),
        "event_family": event_family,
        "identity": online_identity_spec(scenario),
        "reference_video_file": reference_video_file,
        "audio": {
            "required": True,
            "mode": "synchronized_response_neutral_nonverbal",
            "direction": _FAMILY_AUDIO_DIRECTIONS[event_family],
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
