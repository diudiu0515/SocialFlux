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

    def __init__(self, scenario):
        self.scenario = scenario
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
        public_expression = deepcopy(self.default_expression)
        for trigger in self.scenario.get("video_triggers", []):
            conditions = trigger.get("conditions", {})
            currently_active = _condition_matches(current_values, conditions)
            mode = trigger.get("trigger_mode", "crossing")
            if mode == "crossing":
                previously_active = _condition_matches(previous_values, conditions)
                eligible = currently_active and not previously_active
            elif mode == "threshold":
                eligible = currently_active
            elif mode == "state_change":
                eligible = _condition_matches(changes, trigger.get("change_conditions", {}))
            else:
                raise ValueError(f"unsupported trigger_mode: {mode}")
            last_turn = last_trigger_turns.get(trigger["trigger_id"])
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
            }
            private_events.append(event)
            public_expression = expression
            last_trigger_turns[trigger["trigger_id"]] = turn_id
        return {
            "private_events": private_events,
            "observable_expression": public_expression,
            "media": [_public_media(event) for event in private_events],
            "changes": changes,
        }
