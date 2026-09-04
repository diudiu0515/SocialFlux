"""Persona- and history-conditioned appraisal for arbitrary free-form actions."""

from copy import deepcopy

from providers.structured import complete_json

from .prompts import build_appraisal_prompt


def _validate_appraisal(result):
    if set(result) != {"appraisal", "evidence_turn_ids"}:
        raise ValueError("model appraiser must return appraisal and evidence_turn_ids")
    if not isinstance(result["appraisal"], dict) or not isinstance(result["evidence_turn_ids"], list):
        raise ValueError("model appraisal has an invalid shape")
    return result


class ModelAppraiser:
    def __init__(self, scenario, provider, sampling=None):
        self.scenario = deepcopy(scenario)
        self.provider = provider
        self.sampling = dict(sampling or {})

    @property
    def provenance(self):
        return {
            **getattr(self.provider, "provenance", {}),
            "prompt_id": "environment_appraisal_v2",
            "sampling": dict(self.sampling),
        }

    def appraise(self, *, action, previous_state, previous_dynamics, memory):
        agent = self.scenario["environment_agent"]
        prompt = build_appraisal_prompt(
            persona=agent["persona"],
            background=self.scenario["background"],
            explicit_goal=agent["explicit_goal"],
            hidden_intention=agent["hidden_intention"],
            previous_state=previous_state,
            previous_dynamics=previous_dynamics,
            memory=memory,
            action=action,
        )
        return complete_json(
            self.provider,
            [{"role": "user", "content": prompt}],
            self.sampling,
            _validate_appraisal,
            context="model appraiser",
        )
