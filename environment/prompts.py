'''Build private environment prompts from the central prompt catalog.'''

from prompts.loader import render_prompt


def build_appraisal_prompt(*, persona, background, explicit_goal, hidden_intention, previous_state, previous_dynamics, memory, action):
    payload = {'persona': persona, 'background': background, 'explicit_goal': explicit_goal, 'hidden_intention': hidden_intention, 'previous_state': previous_state, 'previous_dynamics': previous_dynamics, 'memory': memory, 'action': action}
    return render_prompt('environment_appraisal_v1', payload)


def build_response_prompt(context):
    return render_prompt('environment_response_v1', context)
