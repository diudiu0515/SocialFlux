'''State-conditioned environment response generation.'''

from prompts.loader import render_prompt


class ResponseGenerator:
    def generate(self, context):
        raise NotImplementedError


class TemplateResponseGenerator(ResponseGenerator):
    def __init__(self, scenario):
        self.scenario = scenario

    def generate(self, context):
        action = context['action']
        action_id = action.get('action_id') if isinstance(action, dict) else 'default'
        templates = self.scenario.get('response_templates', {})
        template = templates.get(action_id) or templates.get('default') or '我听到了。我们继续把这件事具体化。'
        return template.format(action_id=action_id, turn_id=context['turn_id'], memory_summary=context['memory'].get('memory_summary', ''))


class ModelResponseGenerator(ResponseGenerator):
    def __init__(self, provider):
        self.provider = provider

    def generate(self, context):
        prompt = render_prompt('environment_response_v1', context)
        return self.provider.complete([{'role': 'user', 'content': prompt}])
