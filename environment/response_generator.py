"""Model-generated, state-conditioned environment responses."""

from prompts.loader import render_prompt
from providers.text import complete_distinct_text


class ResponseGenerator:
    def generate(self, context):
        raise NotImplementedError


class ModelResponseGenerator(ResponseGenerator):
    def __init__(self, provider, sampling=None):
        self.provider = provider
        self.sampling = dict(sampling or {})

    @property
    def provenance(self):
        return {
            **getattr(self.provider, "provenance", {}),
            "prompt_id": "environment_response_v3",
            "sampling": dict(self.sampling),
        }

    def generate(self, context):
        prompt = render_prompt("environment_response_v3", context)
        prior_responses = [
            item.get("text", "")
            for item in context.get("history", [])
            if item.get("role") == "environment_agent"
        ]
        return complete_distinct_text(
            self.provider,
            [{"role": "user", "content": prompt}],
            self.sampling,
            prior_responses,
            context="environment response",
            max_attempts=12,
        )
