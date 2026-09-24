"""Construct the one provider-backed environment used by rollout generation and T4."""

from copy import deepcopy

from providers.factory import build_provider, public_provider_config

from .appraisal import ModelAppraiser
from .env import StatefulEnvironment
from .response_generator import ModelResponseGenerator
from .state_updater import ModelStateUpdater


class ModelEnvironmentFactory:
    def __init__(
        self,
        scenario,
        provider_config,
        sampling=None,
        *,
        response_provider_config=None,
        response_sampling=None,
        appraisal_prompt_id="environment_appraisal_v11",
        response_prompt_id="environment_response_v25",
        response_validation_profile="hard_only",
        horizon_mode="natural_max_20",
        minimum_natural_turns=1,
        multimodal_trigger_policy=None,
    ):
        self.scenario = deepcopy(scenario)
        self.provider_config = deepcopy(provider_config)
        self.sampling = dict(sampling or {})
        self.response_provider_config = deepcopy(
            response_provider_config or provider_config
        )
        self.response_sampling = dict(
            self.sampling if response_sampling is None else response_sampling
        )
        self.appraisal_prompt_id = appraisal_prompt_id
        self.response_prompt_id = response_prompt_id
        self.response_validation_profile = response_validation_profile
        self.horizon_mode = horizon_mode
        if (
            not isinstance(minimum_natural_turns, int)
            or isinstance(minimum_natural_turns, bool)
            or not 1 <= minimum_natural_turns <= 20
        ):
            raise ValueError("minimum_natural_turns must be between 1 and 20")
        self.minimum_natural_turns = minimum_natural_turns
        self.multimodal_trigger_policy = deepcopy(multimodal_trigger_policy or {})

    @property
    def provenance(self):
        return {
            "environment": public_provider_config(self.provider_config),
            "sampling": dict(self.sampling),
            "appraisal_provider": public_provider_config(self.provider_config),
            "appraisal_sampling": dict(self.sampling),
            "response_provider": public_provider_config(
                self.response_provider_config
            ),
            "response_sampling": dict(self.response_sampling),
            "appraisal_prompt": self.appraisal_prompt_id,
            "state_update": "deterministic_social_delta_calibrator_v1",
            "response_prompt": self.response_prompt_id,
            "response_validation_profile": self.response_validation_profile,
            "horizon_mode": self.horizon_mode,
            "minimum_natural_turns": self.minimum_natural_turns,
            "multimodal_trigger_policy": deepcopy(
                self.multimodal_trigger_policy
            ),
            "llm_calls_per_step": 2,
            "llm_stage_count_per_step": 2,
            "nominal_llm_calls_per_step_without_retries": 2,
            "actual_requests_may_exceed_nominal": True,
            "calls_are_separate": True,
        }

    def __call__(self):
        appraisal_provider = build_provider(self.provider_config)
        response_provider = build_provider(self.response_provider_config)
        return StatefulEnvironment(
            self.scenario,
            state_updater=ModelStateUpdater(
                self.scenario,
                appraisal_provider,
                self.sampling,
                appraiser=ModelAppraiser(
                    self.scenario,
                    appraisal_provider,
                    self.sampling,
                    prompt_id=self.appraisal_prompt_id,
                ),
            ),
            response_generator=ModelResponseGenerator(
                response_provider,
                self.response_sampling,
                prompt_id=self.response_prompt_id,
                validation_profile=self.response_validation_profile,
                horizon_mode=self.horizon_mode,
                minimum_natural_turns=self.minimum_natural_turns,
            ),
            provenance=self.provenance,
            minimum_natural_turns=self.minimum_natural_turns,
            multimodal_trigger_policy=self.multimodal_trigger_policy,
        )
