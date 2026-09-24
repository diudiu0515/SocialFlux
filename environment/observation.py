"""Build the only public observation exposed to rollout and T4 policies."""

from copy import deepcopy

from .interaction_ledger import initial_ledger, public_progress_view
from .longitudinal import initialize_longitudinal_session, public_longitudinal_view
from .public_situation import build_public_situation


PUBLIC_OBSERVATION_FIELDS = (
    "scenario_id",
    "role",
    "target_character",
    "background",
    "public_situation",
    "explicit_goal",
    "conversation_progress",
    "longitudinal_context",
    "history",
    "current_response",
    "observable_cues",
    "observable_expression",
    "media",
    "turn_id",
    "status",
)

PUBLIC_EVALUATED_PERSONA_FIELDS = (
    "name",
    "role",
    "core_values",
    "temperament",
    "communication_style",
    "decision_style",
    "conflict_style",
    "boundaries",
)

PUBLIC_EVALUATED_ROLE_FIELDS = (
    "character_id", "name", "role", "explicit_goal",
)


def build_public_evaluated_role(evaluated):
    """Whitelist evaluated-agent information visible across the interaction."""
    if not isinstance(evaluated, dict):
        return {}
    role = {
        key: deepcopy(evaluated[key])
        for key in PUBLIC_EVALUATED_ROLE_FIELDS
        if key in evaluated
    }
    own_persona = evaluated.get("persona")
    if isinstance(own_persona, dict):
        role["persona"] = {
            key: deepcopy(own_persona[key])
            for key in PUBLIC_EVALUATED_PERSONA_FIELDS
            if key in own_persona
        }
    return role


PRIVATE_AUTHOR_FIELDS = (
    "environment_agent.hidden_intention",
    "environment_agent.persona stable personality",
    "evaluated_agent_role.hidden_intention (author-side only, if present)",
    "initial_state/current state",
    "initial_dynamics/current dynamics",
    "appraisal and state deltas",
    "video trigger conditions",
    "future branches",
)


def build_policy_observation(scenario, session):
    """Return a defensive copy of policy-visible information only."""
    agent = scenario["environment_agent"]
    persona = agent.get("persona", {})
    role = build_public_evaluated_role(
        scenario.get("evaluated_agent_role", {})
    )
    return {
        "scenario_id": scenario["scenario_id"],
        "role": role,
        "target_character": {
            "character_id": f"{scenario['scenario_id']}_ENVIRONMENT_AGENT",
            "name": persona.get("name", "environment agent"),
            "role": persona.get("role", "environment agent"),
        },
        "background": scenario.get("background", ""),
        "public_situation": build_public_situation(scenario),
        "explicit_goal": role.get("explicit_goal", ""),
        "conversation_progress": public_progress_view(
            session.get("interaction_ledger", {})
        ),
        "longitudinal_context": public_longitudinal_view(session),
        "history": deepcopy(session.get("history", [])),
        "current_response": session.get("current_response", ""),
        "observable_cues": deepcopy(session.get("observable_cues", [])),
        "observable_expression": deepcopy(session.get("observable_expression", {})),
        "media": deepcopy(session.get("media", [])),
        "turn_id": session.get("turn_id", 0),
        "status": session.get("status", "active"),
    }


def build_initial_policy_observation(scenario):
    """Build the exact turn-zero payload used by the website prompt preview."""
    default_expression = deepcopy(
        scenario.get("observable_expression", {}).get("default", {})
    )
    session = {
        "history": [],
        "current_response": scenario.get("opening_response", ""),
        "observable_cues": deepcopy(default_expression.get("behavioral_cues", [])),
        "observable_expression": default_expression,
        "media": [],
        "turn_id": 0,
        "status": "active",
        "interaction_ledger": initial_ledger(
            scenario.get("background", ""),
            scenario.get("evaluated_agent_role", {}).get("explicit_goal", ""),
            scenario.get("narrative_design", {}).get("meaningful_choice_space", []),
        ),
    }
    session.update(initialize_longitudinal_session(scenario, "prompt-preview"))
    return build_policy_observation(scenario, session)
