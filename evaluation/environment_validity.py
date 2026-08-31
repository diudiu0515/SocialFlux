"""Transparent scorecard helpers for the environment validation gate."""

from environment.delta_mapper import flatten_state


def _direction(before, after, key):
    delta = after[key] - before[key]
    return 1 if delta > 0 else -1 if delta < 0 else 0


def validate_controlled_policies(trajectories, expectations):
    report = {}
    for policy_id, expected in expectations.items():
        rows = [row for row in trajectories if row["policy_id"] == policy_id]
        if not rows or not rows[0]["turns"]:
            report[policy_id] = {"passed": False, "reason": "missing rollout"}
            continue
        final = rows[0]["turns"][-1]
        before = flatten_state(rows[0]["initial_state"])
        after = flatten_state(final["state_after"])
        checks = {key: _direction(before, after, key) == sign for key, sign in expected.items()}
        report[policy_id] = {"passed": all(checks.values()), "checks": checks}
    return report


def controlled_policy_sensitivity(trajectories, variable):
    """Report the final spread induced by controlled interventions."""
    values = []
    for trajectory in trajectories:
        if trajectory.get("turns"):
            values.append(flatten_state(trajectory["turns"][-1]["state_after"]).get(variable))
    values = [value for value in values if value is not None]
    return {"variable": variable, "n": len(values), "spread": max(values) - min(values) if values else 0,
            "sensitive": len(set(values)) > 1}
