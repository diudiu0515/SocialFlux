"""Scenario termination checks."""

def check_termination(turn_id, max_turns, state=None, dynamics=None, scenario=None):
    if turn_id >= max_turns:
        return True, "max_turns"
    for condition in (scenario or {}).get("termination_conditions", []):
        if condition.get("type") == "turns" and turn_id >= condition.get("value", max_turns):
            return True, condition.get("reason", "scenario_condition")
    return False, None
