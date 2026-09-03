"""Construct the one provider-backed environment used by rollout generation and T4."""

from copy import deepcopy

from providers.factory import build_provider, public_provider_config

from .env import StatefulEnvironment
from .response_generator import ModelResponseGenerator
from .state_updater import ModelStateUpdater


class ModelEnvironmentFactory:
    def __init__(self, scenario, provider_config, sampling=None):
        self.scenario = deepcopy(scenario)
        self.provider_config = deepcopy(provider_config)
        self.sampling = dict(sampling or {})

    @property
    def provenance(self):
        return {
            "environment": public_provider_config(self.provider_config),
            "sampling": dict(self.sampling),
            "appraisal_prompt": "environment_appraisal_v2",
            "state_update_prompt": "state_update_v2",
            "response_prompt": "environment_response_v3",
        }

    def __call__(self):
        provider = build_provider(self.provider_config)
        return StatefulEnvironment(
            self.scenario,
            state_updater=ModelStateUpdater(self.scenario, provider, self.sampling),
            response_generator=ModelResponseGenerator(provider, self.sampling),
            provenance=self.provenance,
        )
