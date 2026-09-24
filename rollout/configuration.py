"""Canonical rollout configuration loading and model-route resolution."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from providers.factory import public_provider_config
from providers.model_assignment import validate_single_model_assignment
from providers.model_routes import ModelRoutes


ROLLOUT_FORMAT = "socialflux_rollout_pool_v1"
def _resolve_model_routes(config, config_path):
    route_reference = config.get("model_routes")
    if route_reference is None:
        return config
    route_path = Path(route_reference)
    if not route_path.is_absolute():
        route_path = Path(config_path).resolve().parent / route_path
    routes = ModelRoutes.load(route_path)
    bindings = {}

    def resolve(owner, field, binding_key):
        reference = owner.get(field)
        if not isinstance(reference, dict) or "model_route" not in reference:
            return
        bindings[binding_key] = reference["model_route"]
        owner[field] = routes.resolve(reference)

    environment = config["environment"]
    resolve(environment, "provider", "environment.appraisal")
    resolve(environment, "response_provider", "environment.response")
    resolve(config["construction"], "provider", "construction.t2_branch")
    for policy in config.get("policies", []):
        reference = policy.get("provider")
        if isinstance(reference, dict) and "model_route" in reference:
            key = f"policy:{policy.get('policy_id')}"
            bindings[key] = reference["model_route"]
            policy["provider"] = routes.resolve(reference)

    config["model_routes_provenance"] = {
        "path": str(route_path),
        "sha256": routes.sha256,
        "bindings": bindings,
    }
    return config


def _validate_model_assignment(config):
    formal = config.get("pool_stage", "development") in {
        "formal_raw",
        "formal_selected",
    }
    providers = [
        config["environment"]["provider"],
        config["environment"].get(
            "response_provider", config["environment"]["provider"]
        ),
        config["construction"]["provider"],
        *(item["provider"] for item in config["policies"]),
    ]
    validate_single_model_assignment(
        config.get("model_assignment"),
        providers,
        require_explicit=formal,
        has_versioned_routes=bool(config.get("model_routes_provenance")),
    )


def _validate_limits(config):
    limits = config.get("pilot_limits")
    if limits is None:
        return
    allowed = {"rollout_turns", "t1", "t2", "t3", "t3_horizon"}
    if not isinstance(limits, dict) or set(limits) - allowed:
        raise ValueError("pilot_limits contains unsupported fields")
    for key in ("rollout_turns", "t1", "t2", "t3"):
        if key in limits and (
            not isinstance(limits[key], int) or limits[key] < 1
        ):
            raise ValueError(f"pilot_limits.{key} must be a positive integer")
    if limits.get("rollout_turns", 20) != 20:
        raise ValueError("pilot_limits.rollout_turns must be exactly 20")
    horizon = limits.get("t3_horizon", 5)
    if not isinstance(horizon, int) or not 5 <= horizon <= 10:
        raise ValueError("pilot_limits.t3_horizon must be between 5 and 10")


def _validate_task_selection(config):
    if config.get("t2_pairing", "all") not in {"all", "within_source_model"}:
        raise ValueError("t2_pairing must be all or within_source_model")
    selection = config.get("task_source_selection", {})
    if not selection:
        return
    if (
        selection.get("strategy")
        != "quality_gate_then_task_specific_weighted_ranking"
    ):
        raise ValueError("unsupported task_source_selection.strategy")
    if selection.get("model_quota") is not False:
        raise ValueError("task source selection must not impose a model quota")
    if (
        not isinstance(selection.get("t1_sources"), int)
        or selection["t1_sources"] < 1
    ):
        raise ValueError(
            "task_source_selection.t1_sources must be a positive integer"
        )


def _validate_policy_pool(config):
    policies = config.get("policies", [])
    total_runs = sum(item.get("runs", 1) for item in policies)
    single_first_pass = config.get("candidate_strategy") == "single_first_pass"
    if single_first_pass and total_runs != 1:
        raise ValueError("single_first_pass requires exactly one logical rollout")
    if total_runs < 2 and not single_first_pass:
        raise ValueError("trajectory search requires at least two policy samples")
    identities = {
        (
            item.get("policy_id"),
            item.get("provider", {}).get("model"),
            json.dumps(item.get("sampling", {}), sort_keys=True),
        )
        for item in policies
    }
    if (
        len(identities) < 2
        and not any(item.get("runs", 1) >= 2 for item in policies)
        and not single_first_pass
    ):
        raise ValueError("rollout policy specs must differ by identity and/or sampling")

    pool_stage = config.get("pool_stage", "development")
    if pool_stage not in {"development", "formal_raw", "formal_selected"}:
        raise ValueError("pool_stage must be development, formal_raw or formal_selected")
    if pool_stage not in {"formal_raw", "formal_selected"}:
        return
    if total_runs < 3 and not single_first_pass:
        raise ValueError("formal rollout requires at least 3 raw trajectories per scenario")
    if any(
        item.get("source_type") not in {"local", "api"}
        or not item.get("model_family")
        for item in policies
    ):
        raise ValueError("formal policy specs require source_type and model_family")


def _validate_horizon_contract(config):
    environment_minimum = config["environment"].get(
        "minimum_natural_turns", 1
    )
    if (
        not isinstance(environment_minimum, int)
        or isinstance(environment_minimum, bool)
        or not 1 <= environment_minimum <= 20
    ):
        raise ValueError(
            "environment.minimum_natural_turns must be between 1 and 20"
        )
    for policy in config.get("policies", []):
        policy_minimum = policy.get("minimum_natural_turns", 1)
        if (
            not isinstance(policy_minimum, int)
            or isinstance(policy_minimum, bool)
            or not 1 <= policy_minimum <= 20
        ):
            raise ValueError(
                "policy.minimum_natural_turns must be between 1 and 20"
            )
        if environment_minimum > 1:
            if policy_minimum != environment_minimum:
                raise ValueError(
                    "offline policy and environment minimum natural turns "
                    "must match"
                )
            if policy.get("prompt_id") != "task_rollout_action_v1":
                raise ValueError(
                    "minimum-depth offline rollout requires "
                    "task_rollout_action_v1"
                )


def load_rollout_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("format") != ROLLOUT_FORMAT:
        raise ValueError(f"rollout config format must be {ROLLOUT_FORMAT}")
    if "environment" not in config or "provider" not in config["environment"]:
        raise ValueError("rollout config requires one canonical environment provider")
    if "construction" not in config or "provider" not in config["construction"]:
        raise ValueError("rollout config requires a construction provider for T2/T3")
    config = _resolve_model_routes(config, path)
    _validate_policy_pool(config)
    _validate_horizon_contract(config)
    _validate_limits(config)
    _validate_task_selection(config)
    _validate_model_assignment(config)
    return config


def public_rollout_config(config):
    environment = config["environment"]
    return {
        "format": config["format"],
        "model_routes": deepcopy(config.get("model_routes_provenance")),
        "model_assignment": deepcopy(config.get("model_assignment")),
        "development_role_assignment": deepcopy(
            config.get("development_role_assignment")
        ),
        "environment": {
            "appraisal_provider": public_provider_config(environment["provider"]),
            "response_provider": public_provider_config(
                environment.get("response_provider", environment["provider"])
            ),
            "appraisal_sampling": deepcopy(environment.get("sampling", {})),
            "response_sampling": deepcopy(environment.get("response_sampling", {})),
            "multimodal_trigger_policy": deepcopy(
                environment.get("multimodal_trigger_policy", {})
            ),
            "minimum_natural_turns": environment.get(
                "minimum_natural_turns", 1
            ),
        },
        "construction": {
            "provider": public_provider_config(config["construction"]["provider"]),
            "sampling": deepcopy(config["construction"].get("sampling", {})),
        },
        "policies": [
            {
                "policy_id": item["policy_id"],
                "provider": public_provider_config(item["provider"]),
                "sampling": deepcopy(item.get("sampling", {})),
                "runs": item.get("runs", 1),
                "source_type": item.get("source_type", "unknown"),
                "model_family": item.get("model_family", "unknown"),
                "minimum_natural_turns": item.get(
                    "minimum_natural_turns", 1
                ),
            }
            for item in config["policies"]
        ],
        "pilot_limits": deepcopy(config.get("pilot_limits")),
        "t2_pairing": config.get("t2_pairing", "all"),
        "task_source_selection": deepcopy(config.get("task_source_selection", {})),
        "pool_stage": config.get("pool_stage", "development"),
    }
