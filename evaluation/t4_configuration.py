"""Canonical configuration loading for online T4 evaluation."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from providers.factory import public_provider_config
from providers.model_assignment import (
    SINGLE_MODEL_STRATEGY,
    validate_single_model_assignment,
)
from providers.model_routes import ModelRoutes

from .t4_evaluation import T4_MAX_TURNS


T4_CONFIG_FORMAT = "socialflux_t4_evaluation_v2"
T4_ACTION_PROMPT = "task_t4_action_v21"
T4_JUDGE_PROMPT = "t4_judge_v2"
T4_OBSERVATION_CONDITIONS = {"text_only", "text_video"}
T4_ROLE_PARTITION_STRATEGY = (
    "gpt_policy_judge_with_claude_reference_environment"
)


def _resolve_routes(config, config_path):
    route_reference = config.get("model_routes")
    if not route_reference:
        raise ValueError("T4 config requires model_routes")
    route_path = Path(route_reference)
    if not route_path.is_absolute():
        route_path = Path(config_path).resolve().parent / route_path
    routes = ModelRoutes.load(route_path)

    bindings = {}
    for owner_name, field, binding in (
        ("evaluated_model", "provider", "evaluated_model.policy"),
        ("environment", "provider", "environment.appraisal"),
        ("environment", "response_provider", "environment.response"),
        ("judge", "provider", "judge.t4"),
    ):
        reference = config[owner_name].get(field)
        if not isinstance(reference, dict) or "model_route" not in reference:
            raise ValueError(f"T4 {owner_name}.{field} must use model_route")
        bindings[binding] = reference["model_route"]
        config[owner_name][field] = routes.resolve(reference)

    config["model_routes_provenance"] = {
        "path": str(route_path.resolve()),
        "sha256": routes.sha256,
        "bindings": bindings,
    }
    return config


def _validate_model_assignment(config):
    assignment = config.get("model_assignment")
    if not isinstance(assignment, dict):
        raise ValueError("T4 requires explicit model_assignment")
    providers = {
        "evaluated_model": config["evaluated_model"]["provider"],
        "environment_appraisal": config["environment"]["provider"],
        "environment_response": config["environment"]["response_provider"],
        "judge": config["judge"]["provider"],
    }
    if assignment.get("strategy") == SINGLE_MODEL_STRATEGY:
        validate_single_model_assignment(
            assignment,
            list(providers.values()),
            require_explicit=True,
            has_versioned_routes=bool(config.get("model_routes_provenance")),
        )
        return

    expected = {
        "strategy",
        "evaluated_model",
        "environment_model",
        "judge_model",
        "independent_calls",
    }
    if set(assignment) != expected:
        raise ValueError(
            "role-partitioned T4 model_assignment fields mismatch"
        )
    if assignment["strategy"] != T4_ROLE_PARTITION_STRATEGY:
        raise ValueError("unsupported T4 model_assignment.strategy")
    if assignment["independent_calls"] is not True:
        raise ValueError("T4 roles require independent calls")
    if providers["evaluated_model"].get("model") != assignment["evaluated_model"]:
        raise ValueError("T4 evaluated model assignment mismatch")
    if providers["judge"].get("model") != assignment["judge_model"]:
        raise ValueError("T4 judge model assignment mismatch")
    if {
        providers["environment_appraisal"].get("model"),
        providers["environment_response"].get("model"),
    } != {assignment["environment_model"]}:
        raise ValueError("T4 environment model assignment mismatch")


def load_t4_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("format") != T4_CONFIG_FORMAT:
        raise ValueError(f"T4 config format must be {T4_CONFIG_FORMAT}")
    if config.get("max_turns") != T4_MAX_TURNS:
        raise ValueError(f"T4 max_turns must be exactly {T4_MAX_TURNS}")
    for key in ("environment", "evaluated_model", "judge"):
        if not isinstance(config.get(key), dict):
            raise ValueError(f"T4 config missing {key}")
    if config["evaluated_model"].get("prompt_id") != T4_ACTION_PROMPT:
        raise ValueError(f"T4 evaluated model must use {T4_ACTION_PROMPT}")
    if config["judge"].get("prompt_id") != T4_JUDGE_PROMPT:
        raise ValueError(f"T4 judge must use {T4_JUDGE_PROMPT}")
    if (
        config["environment"].get("state_calibration_profile")
        == "evidence_balanced_v2"
        and config["environment"].get("appraisal_prompt_id")
        != "environment_appraisal_v12"
    ):
        raise ValueError(
            "evidence_balanced_v2 requires environment_appraisal_v12"
        )
    condition = config["evaluated_model"].get(
        "observation_condition", "text_only"
    )
    if condition not in T4_OBSERVATION_CONDITIONS:
        raise ValueError(
            "T4 evaluated model observation_condition is invalid"
        )
    if (
        condition == "text_video"
        and config["evaluated_model"].get("media_input_format")
        != "openai_video_url"
    ):
        raise ValueError("T4 text_video requires openai_video_url input format")

    config = _resolve_routes(config, path)
    _validate_model_assignment(config)
    return config


def public_t4_config(config):
    return {
        "format": config["format"],
        "max_turns": config["max_turns"],
        "model_assignment": deepcopy(config["model_assignment"]),
        "model_routes": deepcopy(config["model_routes_provenance"]),
        "evaluated_model": {
            "provider": public_provider_config(config["evaluated_model"]["provider"]),
            "prompt_id": config["evaluated_model"]["prompt_id"],
            "sampling": deepcopy(config["evaluated_model"].get("sampling", {})),
            "observation_condition": config["evaluated_model"].get(
                "observation_condition", "text_only"
            ),
            "media_input_format": config["evaluated_model"].get(
                "media_input_format"
            ),
        },
        "environment": {
            "appraisal_prompt_id": config["environment"].get(
                "appraisal_prompt_id"
            ),
            "state_calibration_profile": config["environment"].get(
                "state_calibration_profile", "sparse_v1"
            ),
            "response_prompt_id": config["environment"].get(
                "response_prompt_id"
            ),
            "response_validation_profile": config["environment"].get(
                "response_validation_profile"
            ),
            "appraisal_provider": public_provider_config(
                config["environment"]["provider"]
            ),
            "response_provider": public_provider_config(
                config["environment"]["response_provider"]
            ),
            "appraisal_sampling": deepcopy(
                config["environment"].get("sampling", {})
            ),
            "response_sampling": deepcopy(
                config["environment"].get("response_sampling", {})
            ),
            "multimodal_trigger_policy": deepcopy(
                config["environment"].get("multimodal_trigger_policy", {})
            ),
        },
        "judge": {
            "provider": public_provider_config(config["judge"]["provider"]),
            "prompt_id": config["judge"]["prompt_id"],
            "sampling": deepcopy(config["judge"].get("sampling", {})),
        },
    }
