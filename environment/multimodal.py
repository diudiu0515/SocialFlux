"""State-triggered observable expression and media generation."""

from copy import deepcopy

from .delta_mapper import flatten_state
from .online_multimodal import (
    ONLINE_MULTIMODAL_PROFILE,
    build_online_multimodal_profile,
)


_OPERATORS = {
    ">=": lambda value, threshold: value >= threshold,
    ">": lambda value, threshold: value > threshold,
    "<=": lambda value, threshold: value <= threshold,
    "<": lambda value, threshold: value < threshold,
    "==": lambda value, threshold: value == threshold,
}


def _flat(state, dynamics):
    result = flatten_state(state)
    result.update(flatten_state(dynamics))
    return result


def _condition_matches(values, conditions):
    for variable, condition in conditions.items():
        if variable not in values:
            raise ValueError(f"multimodal trigger references unknown variable: {variable}")
        operator = condition["operator"]
        if operator not in _OPERATORS:
            raise ValueError(f"unsupported multimodal operator: {operator}")
        if not _OPERATORS[operator](values[variable], condition["threshold"]):
            return False
    return True


def _relaxed_conditions(conditions, margin):
    """Return runtime-only relaxed thresholds without mutating the scenario."""
    relaxed = deepcopy(conditions)
    for condition in relaxed.values():
        operator = condition.get("operator")
        threshold = condition.get("threshold")
        if not isinstance(threshold, (int, float)) or not margin:
            continue
        if operator in (">=", ">"):
            condition["threshold"] = threshold - margin
        elif operator in ("<=", "<"):
            condition["threshold"] = threshold + margin
    return relaxed


def _trigger_policy(value):
    supplied = deepcopy(value or {})
    policy = {
        "profile": "scenario_default",
        "threshold_margin": 0,
        "change_threshold_margin": 0,
        "cooldown_turns": None,
        "crossing_as_threshold": False,
        "max_events_per_turn": 1,
        "max_events_per_episode": None,
        "max_fires_per_trigger": None,
        "global_cooldown_turns": 0,
        "event_family_cooldown_turns": 0,
        "defer_first_media_completion": False,
        "event_assets": {},
    }
    if supplied.get("profile") == ONLINE_MULTIMODAL_PROFILE:
        policy.update({
            "crossing_as_threshold": True,
            "max_events_per_episode": 5,
            "max_fires_per_trigger": 1,
            "global_cooldown_turns": 2,
            "event_family_cooldown_turns": 3,
        })
    policy.update(supplied)
    for key in ("threshold_margin", "change_threshold_margin"):
        if (
            isinstance(policy[key], bool)
            or not isinstance(policy[key], (int, float))
            or policy[key] < 0
        ):
            raise ValueError(f"multimodal trigger policy {key} must be non-negative")
    cooldown = policy["cooldown_turns"]
    if cooldown is not None and (
        isinstance(cooldown, bool) or not isinstance(cooldown, int) or cooldown < 0
    ):
        raise ValueError("multimodal trigger policy cooldown_turns must be null or non-negative")
    if policy["max_events_per_turn"] != 1:
        raise ValueError("canonical online runtime allows exactly one media event per turn")
    if not isinstance(policy["crossing_as_threshold"], bool):
        raise ValueError("multimodal trigger policy crossing_as_threshold must be boolean")
    if not isinstance(policy["defer_first_media_completion"], bool):
        raise ValueError("multimodal trigger policy defer_first_media_completion must be boolean")
    if policy["defer_first_media_completion"] and policy["profile"] != ONLINE_MULTIMODAL_PROFILE:
        raise ValueError("first media completion deferral requires online_multimodal_v2")
    for key in ("max_events_per_episode", "max_fires_per_trigger"):
        limit = policy[key]
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit < 1
        ):
            raise ValueError(
                f"multimodal trigger policy {key} must be null or positive"
            )
    for key in ("global_cooldown_turns", "event_family_cooldown_turns"):
        cooldown_value = policy[key]
        if (
            isinstance(cooldown_value, bool)
            or not isinstance(cooldown_value, int)
            or cooldown_value < 0
        ):
            raise ValueError(
                f"multimodal trigger policy {key} must be non-negative"
            )
    if not isinstance(policy["event_assets"], dict):
        raise ValueError(
            "multimodal trigger policy event_assets must be an object"
        )
    return policy


def media_completion_guard(
    trigger_policy, *, turn_id, previous_trigger_turns, multimodal,
    natural_completion, hard_termination,
):
    """Reserve one response to the first real video event in either condition.

    Only a natural ending on the event-producing turn can be deferred. State,
    thresholds, later endings, explicit scenario stops and the turn cap are not
    changed. The environment does not inspect the policy's modality condition.
    """
    if not trigger_policy.get("defer_first_media_completion", False):
        return None
    events = [event for event in multimodal.get("private_events", [])
              if event.get("media_type") == "video"]
    available = any(
        item.get("media_type") == "video" and item.get("asset_status") == "available"
        for item in multimodal.get("media", [])
    )
    first_event = bool(events) and previous_trigger_turns.get("__event_count__", 0) == 0
    deferred = bool(natural_completion and first_event and available and not hard_termination)
    return {
        "policy": "first_event_response_v1",
        "first_video_event": first_event,
        "available_media": available,
        "natural_completion_requested": bool(natural_completion),
        "hard_termination": bool(hard_termination),
        "natural_completion_deferred": deferred,
        "response_opportunity_turn": turn_id + 1 if deferred else None,
        "event_ids": [event.get("media_event_id") for event in events],
    }


def _public_media(event):
    asset_path = event.get("asset_path")
    asset_url = event.get("asset_url")
    if asset_path or asset_url:
        asset_status = "available"
    elif event.get("media_asset_id"):
        asset_status = "planned"
    else:
        asset_status = "spec_only"
    return {
        "media_type": event["media_type"],
        "asset_status": asset_status,
        "asset_path": asset_path,
        "asset_url": asset_url,
        "media_asset_id": event["media_asset_id"],
        "duration_seconds": event["duration_seconds"],
    }


class ObservableExpressionLayer:
    """Project private state changes into public behavioral signals."""

    def __init__(self, scenario, trigger_policy=None):
        self.scenario = scenario
        self.trigger_policy = _trigger_policy(trigger_policy)
        if self.trigger_policy["profile"] == ONLINE_MULTIMODAL_PROFILE:
            self.online_profile = build_online_multimodal_profile(
                scenario, self.trigger_policy["event_assets"]
            )
            self.triggers = self.online_profile["triggers"]
        else:
            self.online_profile = None
            self.triggers = deepcopy(scenario.get("video_triggers", []))
        self.default_expression = deepcopy(
            scenario.get("observable_expression", {}).get(
                "default",
                {
                    "facial_expression": "平静但保持注意力",
                    "gaze": "保持自然注视",
                    "speech_style": "正常语速，信息清楚",
                    "prosody": "语气克制",
                    "behavioral_cues": [],
                },
            )
        )

    def evaluate(self, *, turn_id, previous_state, previous_dynamics, state, dynamics, last_trigger_turns):
        previous_values = _flat(previous_state, previous_dynamics)
        current_values = _flat(state, dynamics)
        changes = {
            key: current_values[key] - previous_values.get(key, current_values[key])
            for key in current_values
        }
        private_events = []
        # No salient composite/rapid-change event means no special observable cue.
        public_expression = {
            "facial_expression": "",
            "gaze": "",
            "speech_style": "",
            "prosody": "",
            "behavioral_cues": [],
        }
        triggers = sorted(
            self.triggers,
            key=lambda item: (
                last_trigger_turns.get(
                    f"__state_family_fire_count__:"
                    f"{item.get('source_state_family')}",
                    0,
                ),
                item.get("priority", 999),
            ),
        )
        episode_limit = self.trigger_policy["max_events_per_episode"]
        episode_count = last_trigger_turns.get("__event_count__", 0)
        if episode_limit is not None and episode_count >= episode_limit:
            triggers = []
        last_global = last_trigger_turns.get("__global__")
        global_cooldown = self.trigger_policy["global_cooldown_turns"]
        if (
            last_global is not None
            and turn_id < last_global + global_cooldown
        ):
            triggers = []
        for trigger in triggers:
            conditions = _relaxed_conditions(
                trigger.get("conditions", {}),
                self.trigger_policy["threshold_margin"],
            )
            currently_active = _condition_matches(current_values, conditions)
            mode = trigger.get("trigger_mode", "crossing")
            if mode == "crossing":
                previously_active = _condition_matches(previous_values, conditions)
                eligible = currently_active and (
                    self.trigger_policy["crossing_as_threshold"]
                    or not previously_active
                )
            elif mode == "threshold":
                eligible = currently_active
            elif mode == "state_change":
                change_conditions = _relaxed_conditions(
                    trigger.get("change_conditions", {}),
                    self.trigger_policy["change_threshold_margin"],
                )
                eligible = _condition_matches(changes, change_conditions)
            else:
                raise ValueError(f"unsupported trigger_mode: {mode}")
            last_turn = last_trigger_turns.get(trigger["trigger_id"])
            cooldown = self.trigger_policy["cooldown_turns"]
            if cooldown is None:
                cooldown = trigger.get("cooldown_turns", 0)
            fire_count = last_trigger_turns.get(
                f"__fire_count__:{trigger['trigger_id']}", 0
            )
            fire_limit = self.trigger_policy["max_fires_per_trigger"]
            if fire_limit is not None and fire_count >= fire_limit:
                eligible = False
            family = trigger.get("event_family")
            family_last = last_trigger_turns.get(f"__family__:{family}")
            family_cooldown = self.trigger_policy["event_family_cooldown_turns"]
            if (
                eligible and family and family_last is not None
                and turn_id < family_last + family_cooldown
            ):
                eligible = False
            if eligible and last_turn is not None and turn_id < last_turn + cooldown:
                eligible = False
            if not eligible:
                continue
            expression = deepcopy(trigger["observable_expression"])
            event = {
                "media_event_id": f"media_t{turn_id:02d}_{trigger['trigger_id']}",
                "turn_id": f"t{turn_id:02d}",
                "trigger_id": trigger["trigger_id"],
                "trigger_mode": mode,
                "trigger_variables": {
                    key: current_values[key] for key in conditions if key in current_values
                },
                "observable_expression": expression,
                "media_type": trigger.get("media_type", "video"),
                "cue_template": trigger["cue_template"],
                "media_asset_id": trigger.get("media_asset_id"),
                "asset_path": trigger.get("asset_path"),
                "asset_url": trigger.get("asset_url"),
                "duration_seconds": trigger.get("duration_seconds", 4),
                "trigger_policy_profile": self.trigger_policy["profile"],
                "event_family": family,
                "source_state_family": trigger.get("source_state_family"),
                "source_state_variable": trigger.get("source_state_variable"),
                "source_direction": trigger.get("source_direction"),
                "response_neutral": bool(trigger.get("response_neutral", False)),
                "spoken_content": bool(trigger.get("spoken_content", True)),
                "scenario_profile_sha256": (
                    self.online_profile.get("scenario_sha256")
                    if self.online_profile else None
                ),
            }
            private_events.append(event)
            public_expression = expression
            last_trigger_turns[trigger["trigger_id"]] = turn_id
            last_trigger_turns["__global__"] = turn_id
            last_trigger_turns["__event_count__"] = episode_count + 1
            last_trigger_turns[f"__fire_count__:{trigger['trigger_id']}"] = (
                fire_count + 1
            )
            if family:
                last_trigger_turns[f"__family__:{family}"] = turn_id
            state_family = trigger.get("source_state_family")
            if state_family:
                key = f"__state_family_fire_count__:{state_family}"
                last_trigger_turns[key] = last_trigger_turns.get(key, 0) + 1
            # docs/source-notes/multimodel.md: at most one highest-priority event per turn.
            break
        return {
            "private_events": private_events,
            "observable_expression": public_expression,
            "media": [_public_media(event) for event in private_events],
            "changes": changes,
        }
