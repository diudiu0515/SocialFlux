"""Free-form model policy for both rollout generation and online T4."""

from prompts.loader import render_prompt
from providers.text import complete_distinct_text


class ModelPolicy:
    def __init__(self, policy_id, provider, prompt_id="task_t4_action_v2", sampling=None):
        self.policy_id = policy_id
        self.provider = provider
        self.prompt_id = prompt_id
        self.sampling = dict(sampling or {})

    def reset(self):
        reset = getattr(self.provider, "reset", None)
        if reset:
            reset()

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
        prior_actions = [
            item.get("text", "")
            for item in observation.get("history", [])
            if item.get("role") == "evaluated_agent"
        ]
        text = complete_distinct_text(
            self.provider,
            [{"role": "user", "content": prompt}],
            self.sampling,
            prior_actions,
            context="model policy action",
            max_attempts=12,
        )
        return {"text": text}
