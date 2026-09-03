"""Model-assisted local constructions over naturally evolved trajectories."""

import json
from copy import deepcopy

from prompts.loader import render_prompt


class ModelCandidateGenerator:
    def __init__(self, provider, sampling=None):
        self.provider = provider
        self.sampling = dict(sampling or {})

    @property
    def provenance(self):
        return {
            **getattr(self.provider, "provenance", {}),
            "sampling": dict(self.sampling),
        }

    def candidate_actions(self, checkpoint_observation, count=3):
        prompt = render_prompt("counterfactual_action_generation_v1", {
            "count": count,
            "checkpoint": checkpoint_observation,
        })
        raw = self.provider.complete(
            [{"role": "user", "content": prompt}],
            **self.sampling,
        )
        try:
            actions = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("counterfactual action generator returned invalid JSON") from exc
        if (
            not isinstance(actions, list)
            or len(actions) < 2
            or any(not isinstance(item, str) or not item.strip() for item in actions)
        ):
            raise ValueError("counterfactual actions must be a JSON array of non-empty strings")
        unique = list(dict.fromkeys(item.strip() for item in actions))
        if len(unique) < 2:
            raise ValueError("counterfactual actions must contain at least two distinct options")
        return [{"text": item} for item in unique[:count]]

    def shared_observation(self, history_a, history_b):
        prompt = render_prompt("t2_shared_observation_v1", {
            "history_a": deepcopy(history_a),
            "history_b": deepcopy(history_b),
        })
        raw = self.provider.complete(
            [{"role": "user", "content": prompt}],
            **self.sampling,
        )
        try:
            observation = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("T2 shared-observation generator returned invalid JSON") from exc
        required = {"current_response", "observable_cues", "observable_expression", "media"}
        if set(observation) != required:
            raise ValueError("T2 shared observation has an invalid shape")
        return observation
