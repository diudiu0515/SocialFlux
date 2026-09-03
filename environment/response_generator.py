"""Model-generated, state-conditioned environment responses."""

from prompts.loader import render_prompt


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
            "prompt_id": "environment_response_v2",
            "sampling": dict(self.sampling),
        }

    def generate(self, context):
        prompt = render_prompt("environment_response_v2", context)
        response = self.provider.complete(
            [{"role": "user", "content": prompt}],
            **self.sampling,
        ).strip()
        if not response:
            raise ValueError("environment response model returned empty text")
        return response
