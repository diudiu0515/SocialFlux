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
    ROLLOUTS_PER_SCENARIO,
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


def assert_single_model_rollout_config(
    config, *, expected_model, expected_seed_slots, context,
):
    """Reject model overrides and malformed fixed-slot single-model configs."""
    assignment = config.get("model_assignment") or {}
    if assignment.get("model") != expected_model:
        raise ValueError(f"{context} rollout model must be {expected_model}")
    if assignment.get("independent_calls") is not True:
        raise ValueError(f"{context} roles must remain independent provider calls")
    policies = config.get("policies", [])
    if len(policies) != expected_seed_slots or any(
        item.get("runs", 1) != 1 for item in policies
    ):
        raise ValueError(
            f"{context} rollout requires exactly {expected_seed_slots} "
            "one-run seed slots"
        )
    seeds = [item.get("sampling", {}).get("seed") for item in policies]
    if len(set(seeds)) != expected_seed_slots or any(
        not isinstance(seed, int) for seed in seeds
    ):
        raise ValueError(
            f"{context} rollout requires {expected_seed_slots} distinct integer seeds"
        )
    environment = config["environment"]
    providers = [
        environment["provider"],
        environment["response_provider"],
        config["construction"]["provider"],
        *(item["provider"] for item in policies),
    ]
    models = {provider.get("model") for provider in providers}
    if models != {expected_model}:
        raise ValueError(
            f"{context} resolved models must be {{{expected_model!r}}}, "
            f"got {sorted(str(item) for item in models)}"
        )
    forbidden = [
        item["policy_id"]
        for item in policies
        if item.get("environment_provider_override")
        or item.get("environment_response_provider_override")
    ]
    if forbidden:
        raise ValueError(
            f"{context} rollout forbids per-policy model overrides: {forbidden}"
        )


def assert_fable_rollout_config(config):
    """Reject model overrides and malformed single-rollout production configs."""
    assert_single_model_rollout_config(
        config,
        expected_model=ACTIVE_MODEL,
        expected_seed_slots=ROLLOUTS_PER_SCENARIO,
        context="active Fable",
    )


def assert_development_role_partitioned_rollout_config(config):
    """Validate the explicit GPT-policy/Claude-environment audit boundary."""
    expected = {
        "strategy": "gpt_policy_tasks_with_claude_reference_environment",
        "policy_model": "gpt-6-astra",
        "environment_model": ACTIVE_MODEL,
        "construction_model": "gpt-6-astra",
        "independent_calls": True,
    }
    assignment = config.get("development_role_assignment")
    if assignment != expected:
        raise ValueError(
            "development role partition must explicitly declare GPT policy/tasks "
            "and the Claude reference environment"
        )
    policies = config.get("policies", [])
    if len(policies) != 1 or policies[0].get("runs", 1) != 1:
        raise ValueError("development role partition requires one policy run")
    seed = policies[0].get("sampling", {}).get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("development role partition requires one integer seed")
    environment = config["environment"]
    resolved = {
        "policy_model": policies[0]["provider"].get("model"),
        "environment_model": environment["provider"].get("model"),
        "response_model": environment["response_provider"].get("model"),
        "construction_model": config["construction"]["provider"].get("model"),
    }
    if resolved != {
        "policy_model": expected["policy_model"],
        "environment_model": expected["environment_model"],
        "response_model": expected["environment_model"],
        "construction_model": expected["construction_model"],
    }:
        raise ValueError(f"development role partition mismatch: {resolved}")


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
