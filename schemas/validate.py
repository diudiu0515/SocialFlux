"""Dependency-free validation for the Phase-A/v1 JSON contracts."""

from pathlib import Path
import json


def _bounded(value, path):
    if isinstance(value, dict):
        for key, item in value.items():
            _bounded(item, f"{path}.{key}")
    elif not isinstance(value, (int, float)) or not 0 <= value <= 10:
        raise ValueError(f"{path} must be numeric in [0, 10]")


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
