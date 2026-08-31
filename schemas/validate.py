"""Dependency-free validation for the Phase-A/v1 JSON contracts."""

from pathlib import Path
import json


def _bounded(value, path):
    if isinstance(value, dict):
        for key, item in value.items():
            _bounded(item, f"{path}.{key}")
    elif not isinstance(value, (int, float)) or not 0 <= value <= 10:
        raise ValueError(f"{path} must be numeric in [0, 10]")


def _validate_multimodal(scenario):
    for trigger in scenario.get("video_triggers", []):
        for key in ("trigger_id", "trigger_mode", "conditions", "cue_template", "observable_expression"):
            if key not in trigger:
                raise ValueError(f"video trigger missing {key}")
        if trigger["trigger_mode"] not in ("threshold", "crossing", "state_change"):
            raise ValueError("video trigger has unsupported trigger_mode")
        condition_set = trigger.get("conditions", {})
        for variable, condition in condition_set.items():
            if not isinstance(condition, dict) or condition.get("operator") not in (">=", ">", "<=", "<", "=="):
                raise ValueError(f"invalid condition for video trigger variable {variable}")
            if not isinstance(condition.get("threshold"), (int, float)):
                raise ValueError(f"video trigger threshold must be numeric for {variable}")
        if trigger["trigger_mode"] == "state_change" and not trigger.get("change_conditions"):
            raise ValueError("state_change trigger requires change_conditions")
        if trigger.get("cooldown_turns", 0) < 0:
            raise ValueError("video trigger cooldown_turns must be non-negative")
        expression = trigger["observable_expression"]
        if not isinstance(expression, dict) or not expression:
            raise ValueError("video trigger observable_expression must be a non-empty object")


def validate_scenario(scenario):
    required = ("scenario_id", "background", "environment_agent", "evaluated_agent_role",
                "initial_state", "initial_dynamics", "action_effects", "max_turns")
    missing = [key for key in required if key not in scenario]
    if missing:
        raise ValueError(f"scenario missing required fields: {missing}")
    agent = scenario["environment_agent"]
    for key in ("persona", "explicit_goal", "hidden_intention"):
        if key not in agent:
            raise ValueError(f"environment_agent missing {key}")
    _bounded(scenario["initial_state"], "initial_state")
    _bounded(scenario["initial_dynamics"], "initial_dynamics")
    if not isinstance(scenario["max_turns"], int) or scenario["max_turns"] < 1:
        raise ValueError("max_turns must be a positive integer")
    _validate_multimodal(scenario)
    return scenario


def validate_trajectory(trajectory):
    required = ("trajectory_id", "scenario_id", "policy_id", "initial_state",
                "initial_dynamics", "turns", "ending")
    missing = [key for key in required if key not in trajectory]
    if missing:
        raise ValueError(f"trajectory missing required fields: {missing}")
    return trajectory


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
