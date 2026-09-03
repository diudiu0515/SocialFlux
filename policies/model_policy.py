"""Free-form model policy for both rollout generation and online T4."""

from prompts.loader import render_prompt


class ModelPolicy:
    def __init__(self, policy_id, provider, prompt_id="task_t4_action_v1", sampling=None):
        self.policy_id = policy_id
        self.provider = provider
        self.prompt_id = prompt_id
        self.sampling = dict(sampling or {})

    @property
    def provenance(self):
        return {
            "policy_id": self.policy_id,
            **getattr(self.provider, "provenance", {}),
            "prompt_id": self.prompt_id,
            "sampling": dict(self.sampling),
        }

    def generate(self, observation):
        prompt = render_prompt(self.prompt_id, observation)
        text = self.provider.complete(
            [{"role": "user", "content": prompt}],
            **self.sampling,
        ).strip()
        if not text:
            raise ValueError("model policy returned an empty action")
        return {"text": text}
