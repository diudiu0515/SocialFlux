"""State-triggered observable expression and media generation."""

from copy import deepcopy

from .delta_mapper import flatten_state


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
    policy = {
        "profile": "scenario_default",
        "threshold_margin": 0,
        "change_threshold_margin": 0,
        "cooldown_turns": None,
        "crossing_as_threshold": False,
        "max_events_per_turn": 1,
    }
    policy.update(deepcopy(value or {}))
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
    return policy


def _public_media(event):
    return {
        "media_type": event["media_type"],
        "asset_status": "spec_only" if event["media_asset_id"] is None else "available",
        "asset_path": None,
        "media_asset_id": event["media_asset_id"],
        "duration_seconds": event["duration_seconds"],
    }


class ObservableExpressionLayer:
    """Project private state changes into public behavioral signals."""

    def __init__(self, scenario, trigger_policy=None):
        self.scenario = scenario
        self.trigger_policy = _trigger_policy(trigger_policy)
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
            self.scenario.get("video_triggers", []),
            key=lambda item: item.get("priority", 999),
        )
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
                "duration_seconds": trigger.get("duration_seconds", 4),
                "trigger_policy_profile": self.trigger_policy["profile"],
            }
            private_events.append(event)
            public_expression = expression
            last_trigger_turns[trigger["trigger_id"]] = turn_id
            # docs/source-notes/multimodel.md: at most one highest-priority event per turn.
            break
        return {
            "private_events": private_events,
            "observable_expression": public_expression,
            "media": [_public_media(event) for event in private_events],
            "changes": changes,
        }
