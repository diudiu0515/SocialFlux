"""Model-assisted local constructions over naturally evolved trajectories."""

from copy import deepcopy

from prompts.loader import render_prompt
from providers.structured import complete_json


def _validate_candidate_actions(actions):
    if (
        not isinstance(actions, list)
        or len(actions) < 2
        or any(not isinstance(item, str) or not item.strip() for item in actions)
    ):
        raise ValueError("counterfactual actions must be a JSON array of non-empty strings")
    unique = list(dict.fromkeys(item.strip() for item in actions))
    if len(unique) < 2:
        raise ValueError("counterfactual actions must contain at least two distinct options")
    return unique


def _response_addresses_character_itself(response, character):
    response = str(response).lstrip(" \t\r\n\"“")
    name = str(character.get("name", "")).strip()
    role = str(character.get("role", "")).strip()
    prefixes = {value for value in (name, role) if value}
    for title in ("总监", "经理", "主任", "老师", "医生", "教授", "老板", "院长", "队长", "校长"):
        if name and title in role:
            prefixes.add(name[0] + title)
    return any(response.startswith(prefix) for prefix in prefixes)


def _validate_shared_observation(observation, target_character):
    required = {"current_response", "observable_cues", "observable_expression", "media"}
    if not isinstance(observation, dict) or set(observation) != required:
        raise ValueError("T2 shared observation has an invalid shape")
    if _response_addresses_character_itself(observation["current_response"], target_character):
        raise ValueError("T2 shared response addresses the target character itself")
    return observation


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
        unique = complete_json(
            self.provider,
            [{"role": "user", "content": prompt}],
            self.sampling,
            _validate_candidate_actions,
            context="counterfactual action generator",
        )
        return [{"text": item} for item in unique[:count]]

    def shared_observation(
        self,
        history_a,
        history_b,
        target_character=None,
        evaluated_character=None,
    ):
        prompt = render_prompt("t2_shared_observation_v3", {
            "target_character": deepcopy(target_character or {}),
            "evaluated_character": deepcopy(evaluated_character or {}),
            "history_a": deepcopy(history_a),
            "history_b": deepcopy(history_b),
        })
        return complete_json(
            self.provider,
            [{"role": "user", "content": prompt}],
            self.sampling,
            lambda observation: _validate_shared_observation(
                observation, target_character or {}
            ),
            context="T2 shared-observation generator",
            max_attempts=5,
        )
