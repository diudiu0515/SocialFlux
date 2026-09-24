"""Build private environment prompts from the central prompt catalog."""

from environment.delta_mapper import flatten_state
from prompts.loader import render_prompt


def build_appraisal_prompt(
    *,
    persona,
    background,
    explicit_goal,
    hidden_intention,
    previous_state,
    previous_dynamics,
    memory,
    action,
    evaluated_agent=None,
    longitudinal_context=None,
    interaction_ledger=None,
    prompt_id="environment_appraisal_v11",
):
    return render_prompt(prompt_id, {
        "persona": persona,
        "background": background,
        "explicit_goal": explicit_goal,
        "evaluated_agent": evaluated_agent or {},
        "hidden_intention": hidden_intention,
        "previous_state": previous_state,
        "previous_dynamics": previous_dynamics,
        "state_variable_paths": sorted(flatten_state(previous_state)),
        "dynamics_variable_paths": sorted(flatten_state(previous_dynamics)),
        "memory": memory,
        "longitudinal_context": longitudinal_context or {},
        "interaction_ledger": interaction_ledger or {},
        "action": action,
    }, latest_action_text=str(action.get("text", "")).strip())


def build_response_prompt(context):
    return render_prompt("environment_response_v25", context)
