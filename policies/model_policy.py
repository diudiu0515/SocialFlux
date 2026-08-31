'''Adapter from the unified policy interface to a model provider.'''

from prompts.loader import render_prompt


class ModelPolicy:
    def __init__(self, policy_id, provider, prompt_id='policy_action_v1'):
        self.policy_id = policy_id
        self.provider = provider
        self.prompt_id = prompt_id

    def generate(self, observation):
        prompt = render_prompt(self.prompt_id, observation)
        text = self.provider.complete([{'role': 'user', 'content': prompt}])
        return {'action_id': 'model_action', 'text': text}
