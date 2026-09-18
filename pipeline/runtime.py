"""One runtime owner for Fable calls and the two-stage environment."""

from copy import deepcopy

from environment.factory import ModelEnvironmentFactory
from policies.model_policy import ModelPolicy
from providers.factory import build_provider

from .constants import (
    ACTIVE_MODEL,
    APPRAISAL_PROMPT,
    POLICY_PROMPT,
    RESPONSE_PROMPT,
    SEEDS_PER_SCENARIO,
)


def assert_fable_providers(provider_configs, *, context):
    models = {
        provider.get("model")
        for provider in provider_configs
        if isinstance(provider, dict)
    }
    if models != {ACTIVE_MODEL}:
        raise ValueError(
            f"{context} is Fable-only; resolved models must be "
            f"{{'{ACTIVE_MODEL}'}}, got {sorted(str(item) for item in models)}"
        )


def assert_fable_rollout_config(config):
    """Reject model overrides and malformed three-seed production configs."""
    assignment = config.get("model_assignment") or {}
    if assignment.get("model") != ACTIVE_MODEL:
        raise ValueError(f"active rollout model must be {ACTIVE_MODEL}")
    if assignment.get("independent_calls") is not True:
        raise ValueError("Fable roles must remain independent provider calls")
    policies = config.get("policies", [])
    if len(policies) != SEEDS_PER_SCENARIO or any(
        item.get("runs", 1) != 1 for item in policies
    ):
        raise ValueError(
            f"active rollout requires exactly {SEEDS_PER_SCENARIO} one-run seed slots"
        )
    seeds = [item.get("sampling", {}).get("seed") for item in policies]
    if len(set(seeds)) != SEEDS_PER_SCENARIO or any(
        not isinstance(seed, int) for seed in seeds
    ):
        raise ValueError("active rollout requires three distinct integer seeds")
    environment = config["environment"]
    assert_fable_providers(
        [
            environment["provider"],
            environment["response_provider"],
            config["construction"]["provider"],
            *(item["provider"] for item in policies),
        ],
        context="active rollout",
    )
    forbidden = [
        item["policy_id"]
        for item in policies
        if item.get("environment_provider_override")
        or item.get("environment_response_provider_override")
    ]
    if forbidden:
        raise ValueError(
            f"active rollout forbids per-policy model overrides: {forbidden}"
        )


def assert_fable_t4_config(config):
    environment = config["environment"]
    assert_fable_providers(
        [
            config["evaluated_model"]["provider"],
            environment["provider"],
            environment["response_provider"],
            config["judge"]["provider"],
        ],
        context="active T4",
    )


def build_environment_factory(scenario, environment):
    """Build the only environment path: appraisal -> Python -> response."""
    return ModelEnvironmentFactory(
        scenario,
        environment["provider"],
        environment.get("sampling", {}),
        response_provider_config=environment["response_provider"],
        response_sampling=environment.get("response_sampling", {}),
        appraisal_prompt_id=environment.get("appraisal_prompt_id", APPRAISAL_PROMPT),
        response_prompt_id=environment.get("response_prompt_id", RESPONSE_PROMPT),
        response_validation_profile=environment.get(
            "response_validation_profile", "hard_only"
        ),
        horizon_mode=environment.get("horizon_mode", "natural_max_20"),
    )


def iter_policy_specs(config):
    for spec in config["policies"]:
        runs = spec.get("runs", 1)
        if not isinstance(runs, int) or runs < 1:
            raise ValueError("policy runs must be a positive integer")
        for run_index in range(runs):
            yield spec, run_index


def build_policy(spec, run_index=0, *, provenance_extra=None):
    sampling = deepcopy(spec.get("sampling", {}))
    if isinstance(sampling.get("seed"), int):
        sampling["seed"] += run_index
    policy_id = spec["policy_id"]
    if spec.get("runs", 1) > 1:
        policy_id = f"{policy_id}__run_{run_index + 1}"
    extra = {
        "source_type": spec.get("source_type", "api"),
        "model_family": spec.get("model_family", "claude"),
    }
    extra.update(provenance_extra or {})
    return ModelPolicy(
        policy_id,
        build_provider(spec["provider"]),
        prompt_id=spec.get("prompt_id", POLICY_PROMPT),
        sampling=sampling,
        provenance_extra=extra,
        validation_profile=spec.get("validation_profile", "hard_only"),
        horizon_mode=spec.get("horizon_mode", "natural_max_20"),
    )
