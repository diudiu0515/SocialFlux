"""Scenario-bound online multimodal trigger profiles.

The canonical scenario keeps its authored three-event media plan unchanged.
For online T4, this module derives a denser, versioned trigger sidecar from
the scenario's four-dimensional initial state.  The profile changes only the
observable layer; it never updates latent state or environment text.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re

from .delta_mapper import flatten_state


ONLINE_MULTIMODAL_PROFILE = "online_multimodal_v2"
ONLINE_MULTIMODAL_PROFILE_FORMAT = "socialflux_online_multimodal_profile_v2"

_FAMILY_ORDER = (
    "emotion",
    "behavioral_disposition",
    "relationship",
    "consequence_risk",
)

_NEGATIVE_VARIABLES = {
    "anger",
    "anxiety",
    "avoidance_urge",
    "commitment_breach_risk",
    "disappointment",
    "exclusion_risk",
    "fear",
    "frustration",
    "goal_failure_risk",
    "guilt",
    "hostility",
    "institutional_harm_risk",
    "material_loss_risk",
    "relationship_rupture_risk",
    "reputational_harm_risk",
    "resistance_intent",
    "safety_harm_risk",
}

_EVENT_FAMILIES = {
    "activated_tension": {
        "cue_template": "A brief, silent rise in visible tension.",
        "observable_expression": {
            "facial_expression": "面部短暂绷紧，随后恢复克制",
            "gaze": "注视略有停顿",
            "speech_style": "不改变文字内容",
            "prosody": "无额外台词",
            "behavioral_cues": ["轻微收紧下颌", "呼吸短暂停顿"],
        },
    },
    "easing_tension": {
        "cue_template": "A brief, silent easing of visible tension.",
        "observable_expression": {
            "facial_expression": "眉眼和下颌略微放松",
            "gaze": "重新建立较自然的注视",
            "speech_style": "不改变文字内容",
            "prosody": "无额外台词",
            "behavioral_cues": ["缓慢呼气", "肩部轻微放松"],
        },
    },
    "open_engagement": {
        "cue_template": "A subtle, silent shift toward engagement.",
        "observable_expression": {
            "facial_expression": "神情更专注但不过度积极",
            "gaze": "注视更稳定",
            "speech_style": "不改变文字内容",
            "prosody": "无额外台词",
            "behavioral_cues": ["身体轻微前倾", "小幅点头"],
        },
    },
    "guarded_withdrawal": {
        "cue_template": "A subtle, silent shift toward guarded distance.",
        "observable_expression": {
            "facial_expression": "表情收敛，防备感略有增加",
            "gaze": "短暂移开后再看向对方",
            "speech_style": "不改变文字内容",
            "prosody": "无额外台词",
            "behavioral_cues": ["身体略微后移", "手部动作减少"],
        },
    },
    "firm_boundary": {
        "cue_template": "A brief, silent firming of posture and boundary.",
        "observable_expression": {
            "facial_expression": "表情变得坚定而克制",
            "gaze": "保持直接但不具攻击性的注视",
            "speech_style": "不改变文字内容",
            "prosody": "无额外台词",
            "behavioral_cues": ["坐姿略微挺直", "动作变得简洁"],
        },
    },
    "risk_concern": {
        "cue_template": "A brief, silent sign of renewed concern.",
        "observable_expression": {
            "facial_expression": "眉间短暂收紧，显出审慎",
            "gaze": "视线停留片刻",
            "speech_style": "不改变文字内容",
            "prosody": "无额外台词",
            "behavioral_cues": ["短暂停顿", "轻微吸气"],
        },
    },
    "cautious_relief": {
        "cue_template": "A brief, silent sign of cautious relief.",
        "observable_expression": {
            "facial_expression": "紧绷感略有缓解但仍保持审慎",
            "gaze": "注视恢复稳定",
            "speech_style": "不改变文字内容",
            "prosody": "无额外台词",
            "behavioral_cues": ["轻缓呼气", "姿态略微放松"],
        },
    },
}

ONLINE_EVENT_FAMILIES = tuple(_EVENT_FAMILIES)


def _scenario_sha256(scenario):
    payload = json.dumps(
        scenario,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _slug(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def _event_family(variable, direction):
    state_family, leaf = variable.split(".", 1)
    increasing = direction == "increase"
    if state_family == "consequence_risk":
        return "risk_concern" if increasing else "cautious_relief"
    if leaf == "boundary_assertion" and increasing:
        return "firm_boundary"
    if leaf in _NEGATIVE_VARIABLES:
        return "activated_tension" if increasing else "easing_tension"
    return "open_engagement" if increasing else "guarded_withdrawal"


def _ordered_state_paths(initial_state):
    flattened = flatten_state(initial_state)
    by_family = {
        family: [
            path for path in flattened if path.startswith(f"{family}.")
        ]
        for family in _FAMILY_ORDER
    }
    # Round-robin keeps the first eligible leaf from all four state families
    # ahead of a second leaf from any one family. This affects only which
    # observable cue wins when several real transitions are simultaneously
    # eligible; it never changes latent state.
    return [
        paths[index]
        for index in range(max(map(len, by_family.values()), default=0))
        for paths in by_family.values()
        if index < len(paths)
    ]


def _asset_record(event_assets, scenario_id, event_family):
    assets = event_assets or {}
    scenario_assets = assets.get(scenario_id, assets)
    if not isinstance(scenario_assets, dict):
        raise ValueError("scenario event_assets must be an object")
    record = deepcopy(scenario_assets.get(event_family, {}))
    if isinstance(record, str):
        record = {"asset_path": record}
    if not isinstance(record, dict):
        raise ValueError("online multimodal event asset records must be objects")
    return record


def build_online_multimodal_profile(scenario, event_assets=None):
    """Build bidirectional one-step crossings over all four state families."""
    initial_state = scenario.get("initial_state", {})
    values = flatten_state(initial_state)
    triggers = []
    priority = 1

    # Each variable's two directions stay adjacent while state families rotate.
    # Only one direction can be active, so simultaneous changes are drained in
    # family-balanced order under the runtime cooldown.
    for variable in _ordered_state_paths(initial_state):
        for direction in ("increase", "decrease"):
            initial = values[variable]
            threshold = initial + (1 if direction == "increase" else -1)
            if not 0 <= threshold <= 10:
                continue
            operator = ">=" if direction == "increase" else "<="
            family = _event_family(variable, direction)
            family_spec = _EVENT_FAMILIES[family]
            asset = _asset_record(
                event_assets, scenario.get("scenario_id"), family
            )
            asset_id = asset.get(
                "media_asset_id",
                f"{scenario.get('scenario_id')}:online_nonverbal_v1:{family}",
            )
            trigger = {
                "trigger_id": (
                    f"ommv2_{_slug(variable)}_"
                    f"{'up' if direction == 'increase' else 'down'}"
                ),
                "priority": priority,
                "trigger_mode": "crossing",
                "conditions": {
                    variable: {
                        "operator": operator,
                        "threshold": threshold,
                    }
                },
                "change_conditions": {},
                "cooldown_turns": 20,
                "observable_expression": deepcopy(
                    family_spec["observable_expression"]
                ),
                "cue_template": family_spec["cue_template"],
                "media_type": "video",
                "duration_seconds": float(asset.get("duration_seconds", 4)),
                "media_asset_id": asset_id,
                "asset_path": asset.get("asset_path"),
                "asset_url": asset.get("asset_url"),
                "event_family": family,
                "response_neutral": True,
                "spoken_content": False,
                "source_state_variable": variable,
                "source_state_family": variable.split(".", 1)[0],
                "source_direction": direction,
            }
            triggers.append(trigger)
            priority += 1

    return {
        "format": ONLINE_MULTIMODAL_PROFILE_FORMAT,
        "profile": ONLINE_MULTIMODAL_PROFILE,
        "scenario_id": scenario.get("scenario_id"),
        "scenario_sha256": _scenario_sha256(scenario),
        "trigger_count": len(triggers),
        "event_families": sorted({
            trigger["event_family"] for trigger in triggers
        }),
        "state_family_trigger_counts": {
            family: sum(
                trigger["source_state_family"] == family
                for trigger in triggers
            )
            for family in _FAMILY_ORDER
        },
        "triggers": triggers,
        "generation_rule": (
            "each selected four-family state leaf at S0 plus or minus one; "
            "no event is eligible at unchanged S0"
        ),
    }
