"""Construct the one provider-backed environment used by rollout generation and T4."""

from copy import deepcopy

from providers.factory import build_provider, public_provider_config
from prompts.loader import get_prompt

from .appraisal import ModelAppraiser
from .independent_appraisal import (
    ModelInteractionAppraiser,
    ModelStateAppraiser,
)
from .env import StatefulEnvironment
from .online_multimodal import (
    ONLINE_MULTIMODAL_PROFILE,
    build_online_multimodal_profile,
)
from .response_generator import ModelResponseGenerator
from .state_updater import ModelStateUpdater
from .state_transition_contract import (
    STATE_V3_STAGE_ORDER,
    validate_state_transition_environment_config,
    validate_state_v3_scenario,
)


class ModelEnvironmentFactory:
    def __init__(
        self,
        scenario,
        provider_config,
        sampling=None,
        *,
        independent_appraisals=False,
        state_appraisal_provider_config=None,
        interaction_appraisal_provider_config=None,
        state_appraisal_sampling=None,
        interaction_appraisal_sampling=None,
        state_appraisal_prompt_id="environment_state_appraisal_v1_per_variable",
        interaction_appraisal_prompt_id="environment_interaction_appraisal_v1",
        response_provider_config=None,
        response_sampling=None,
        appraisal_prompt_id="environment_appraisal_v11",
        response_prompt_id="environment_response_v25",
        response_validation_profile="hard_only",
        state_calibration_profile="sparse_v1",
        state_transition_standard=None,
        state_transition_runtime_revision=None,
        horizon_mode="natural_max_20",
        minimum_natural_turns=1,
        response_opportunity_guidance=True,
        multimodal_trigger_policy=None,
    ):
        self.scenario = deepcopy(scenario)
        self.provider_config = deepcopy(provider_config)
        self.sampling = dict(sampling or {})
        self.independent_appraisals = bool(independent_appraisals)
        self.state_appraisal_provider_config = deepcopy(
            state_appraisal_provider_config or provider_config
        )
        self.interaction_appraisal_provider_config = deepcopy(
            interaction_appraisal_provider_config or provider_config
        )
        self.state_appraisal_sampling = dict(
            self.sampling
            if state_appraisal_sampling is None else state_appraisal_sampling
        )
        self.interaction_appraisal_sampling = dict(
            self.sampling
            if interaction_appraisal_sampling is None
            else interaction_appraisal_sampling
        )
        self.state_appraisal_prompt_id = state_appraisal_prompt_id
        self.interaction_appraisal_prompt_id = interaction_appraisal_prompt_id
        self.response_provider_config = deepcopy(
            response_provider_config or provider_config
        )
        self.response_sampling = dict(
            self.sampling if response_sampling is None else response_sampling
        )
        self.appraisal_prompt_id = appraisal_prompt_id
        self.response_prompt_id = response_prompt_id
        self.response_validation_profile = response_validation_profile
        self.state_calibration_profile = state_calibration_profile
        self.state_transition_standard = state_transition_standard
        self.state_transition_runtime_revision = state_transition_runtime_revision
        self.horizon_mode = horizon_mode
        if (
            not isinstance(minimum_natural_turns, int)
            or isinstance(minimum_natural_turns, bool)
            or not 1 <= minimum_natural_turns <= 20
        ):
            raise ValueError("minimum_natural_turns must be between 1 and 20")
        self.minimum_natural_turns = minimum_natural_turns
        self.response_opportunity_guidance = bool(response_opportunity_guidance)
        self.multimodal_trigger_policy = deepcopy(multimodal_trigger_policy or {})
        validate_state_transition_environment_config({
            "state_transition_standard": self.state_transition_standard,
            "state_transition_runtime_revision": (
                self.state_transition_runtime_revision
            ),
            "appraisal_prompt_id": self.appraisal_prompt_id,
            "response_prompt_id": self.response_prompt_id,
            "state_calibration_profile": self.state_calibration_profile,
            "horizon_mode": self.horizon_mode,
            "minimum_natural_turns": self.minimum_natural_turns,
        })
        if self.state_transition_standard is not None:
            validate_state_v3_scenario(self.scenario)
        self.online_multimodal_profile = None
        if (
            self.multimodal_trigger_policy.get("profile")
            == ONLINE_MULTIMODAL_PROFILE
        ):
            profile = build_online_multimodal_profile(
                self.scenario,
                self.multimodal_trigger_policy.get("event_assets", {}),
            )
            self.online_multimodal_profile = {
                key: deepcopy(value)
                for key, value in profile.items()
                if key != "triggers"
            }

    @property
    def provenance(self):
        return {
            "environment": public_provider_config(self.provider_config),
            "response_opportunity_guidance": self.response_opportunity_guidance,
            "sampling": dict(self.sampling),
            "appraisal_provider": public_provider_config(self.provider_config),
            "appraisal_sampling": dict(self.sampling),
            "appraisal_mode": (
                "independent_parallel" if self.independent_appraisals
                else "combined"
            ),
            "state_appraisal_provider": public_provider_config(
                self.state_appraisal_provider_config
            ) if self.independent_appraisals else None,
            "interaction_appraisal_provider": public_provider_config(
                self.interaction_appraisal_provider_config
            ) if self.independent_appraisals else None,
            "state_appraisal_sampling": dict(self.state_appraisal_sampling),
            "interaction_appraisal_sampling": dict(
                self.interaction_appraisal_sampling
            ),
            "state_appraisal_prompt": self.state_appraisal_prompt_id,
            "interaction_appraisal_prompt": self.interaction_appraisal_prompt_id,
            "response_provider": public_provider_config(
                self.response_provider_config
            ),
            "response_sampling": dict(self.response_sampling),
            "appraisal_prompt": self.appraisal_prompt_id,
            "state_update": "deterministic",
            "state_calibration_profile": self.state_calibration_profile,
            "state_transition_standard": self.state_transition_standard,
            "state_transition_runtime_revision": (
                self.state_transition_runtime_revision
            ),
            "state_transition_stage_order": list(STATE_V3_STAGE_ORDER),
            "response_prompt": self.response_prompt_id,
            "response_validation_profile": self.response_validation_profile,
            "horizon_mode": self.horizon_mode,
            "minimum_natural_turns": self.minimum_natural_turns,
            "multimodal_trigger_policy": deepcopy(
                self.multimodal_trigger_policy
            ),
            "online_multimodal_profile": deepcopy(
                self.online_multimodal_profile
            ),
            "llm_calls_per_step": 3 if self.independent_appraisals else 2,
            "llm_stage_count_per_step": 3 if self.independent_appraisals else 2,
            "nominal_llm_calls_per_step_without_retries": 3 if self.independent_appraisals else 2,
            "actual_requests_may_exceed_nominal": True,
            "calls_are_separate": True,
        }

    def __call__(self):
        # Reject retired experiment configurations before constructing providers.
        # A combined prompt ID in independent-mode provenance is not a call stage.
        prompt_ids = (
            (self.state_appraisal_prompt_id, self.interaction_appraisal_prompt_id)
            if self.independent_appraisals else (self.appraisal_prompt_id,)
        )
        for prompt_id in (*prompt_ids, self.response_prompt_id):
            get_prompt(prompt_id)
        if self.independent_appraisals:
            state_provider = build_provider(self.state_appraisal_provider_config)
            interaction_provider = build_provider(
                self.interaction_appraisal_provider_config
            )
            state_updater = ModelStateUpdater(
                self.scenario,
                state_provider,
                self.state_appraisal_sampling,
                state_appraiser=ModelStateAppraiser(
                    self.scenario,
                    state_provider,
                    self.state_appraisal_sampling,
                    prompt_id=self.state_appraisal_prompt_id,
                ),
                interaction_appraiser=ModelInteractionAppraiser(
                    self.scenario,
                    interaction_provider,
                    self.interaction_appraisal_sampling,
                    prompt_id=self.interaction_appraisal_prompt_id,
                ),
                calibration_profile=self.state_calibration_profile,
            )
        else:
            appraisal_provider = build_provider(self.provider_config)
            state_updater = ModelStateUpdater(
                self.scenario,
                appraisal_provider,
                self.sampling,
                appraiser=ModelAppraiser(
                    self.scenario,
                    appraisal_provider,
                    self.sampling,
                    prompt_id=self.appraisal_prompt_id,
                ),
                calibration_profile=self.state_calibration_profile,
            )
        response_provider = build_provider(self.response_provider_config)
        return StatefulEnvironment(
            self.scenario,
            state_updater=state_updater,
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
            response_opportunity_guidance=self.response_opportunity_guidance,
            multimodal_trigger_policy=self.multimodal_trigger_policy,
        )
