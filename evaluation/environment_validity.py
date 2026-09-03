"""Evidence helpers for natural trajectories and local checkpoint interventions."""

from environment.delta_mapper import flatten_state


def trajectory_structure(trajectory):
    turns = trajectory.get("turns", [])
    state_values = [
        value
        for turn in turns
        for value in flatten_state(turn.get("state_after", {})).values()
    ]
    dynamics_values = [
        value
        for turn in turns
        for value in flatten_state(turn.get("dynamics_after", {})).values()
    ]
    checks = {
        "free_form_actions": all(
            isinstance(turn.get("policy_action"), dict)
            and bool(turn["policy_action"].get("text", "").strip())
            and "action_id" not in turn["policy_action"]
            for turn in turns
        ),
        "state_bounds": all(0 <= value <= 10 for value in state_values),
        "dynamics_bounds": all(0 <= value <= 10 for value in dynamics_values),
        "nonempty_responses": all(turn.get("environment_response", "").strip() for turn in turns),
        "ordered_turns": [turn.get("turn_id") for turn in turns]
        == [f"t{index}" for index in range(1, len(turns) + 1)],
        "model_provenance": bool(trajectory.get("policy_provenance"))
        and bool(trajectory.get("environment_provenance")),
    }
    return {"checks": checks, "passed": bool(turns) and all(checks.values())}


def local_action_intervention_evidence(branches):
    if len(branches) < 2:
        return {"branch_count": len(branches), "divergent": False, "spread": {}}
    states = [flatten_state(branch["state_after_immediate"]) for branch in branches]
    variables = sorted(set().union(*(set(state) for state in states)))
    spread = {
        variable: max(state[variable] for state in states)
        - min(state[variable] for state in states)
        for variable in variables
        if all(variable in state for state in states)
    }
    return {
        "branch_count": len(branches),
        "divergent": any(value > 0 for value in spread.values()),
        "spread": spread,
    }


def seed_coverage(trajectories):
    groups = {}
    for trajectory in trajectories:
        provenance = trajectory.get("policy_provenance", {})
        key = (trajectory.get("scenario_id"), provenance.get("provider"), provenance.get("model"))
        groups.setdefault(key, set()).add(provenance.get("sampling", {}).get("seed"))
    comparable = {
        "|".join(str(item) for item in key): sorted(seed for seed in seeds if seed is not None)
        for key, seeds in groups.items()
        if len({seed for seed in seeds if seed is not None}) >= 2
    }
    return {"comparable_groups": comparable, "ready": bool(comparable)}
