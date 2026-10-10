"""Role-visible background is authored separately from private world context."""

from .public_situation import build_policy_situation, sanitize_public_text


def policy_background(scenario):
    """Never infer that the mixed author background is known to the policy.

    Legacy scenarios without an explicit view fail closed to empty background;
    identity, own goal, actual observed dialogue and approved narrative remain.
    Candidate batches must supply and review this field before rollout.
    """
    value = scenario.get("policy_background", "")
    if not isinstance(value, str):
        raise ValueError("policy_background must be text")
    if "policy_background" in scenario and not value.strip():
        raise ValueError("explicit policy_background must be non-empty")
    return sanitize_public_text(value)


def public_scenario_context(scenario):
    """The review/T4 export must use the same visibility boundary as policy."""
    from .observation import build_public_evaluated_role
    persona = scenario.get("environment_agent", {}).get("persona", {})
    return {
        "background": policy_background(scenario),
        "public_situation": build_policy_situation(scenario),
        "evaluated_agent_role": build_public_evaluated_role(scenario.get("evaluated_agent_role", {})),
        "environment_role": {key: persona[key] for key in ("name", "role") if key in persona},
    }


def policy_progress_view(scenario, ledger):
    """Do not leak mixed author background through the t0 ledger seed."""
    from .interaction_ledger import public_progress_view
    result = public_progress_view(ledger)
    facts = []
    for fact in result["established_facts"]:
        if fact.get("id") == "scenario:background":
            # Knowing one's own private context does not make it common ground.
            visible = sanitize_public_text(scenario.get("shared_background", ""))
            if visible:
                facts.append({**fact, "text": visible})
        else:
            # Actual dialogue disclosures remain visible; do not blacklist text.
            facts.append(fact)
    result["established_facts"] = facts
    return result


def shared_initial_background(scenario):
    """Role-private summaries are not automatically shared ledger facts."""
    if "policy_background" in scenario or "environment_background" in scenario:
        return sanitize_public_text(scenario.get("shared_background", ""))
    return sanitize_public_text(scenario.get("background", ""))
