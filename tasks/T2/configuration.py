"""Canonical configuration loading for source-adapted T2 construction."""

from __future__ import annotations

from pathlib import Path

from providers.model_assignment import validate_single_model_assignment
from providers.model_routes import ModelRoutes
from tasks.T2.runtime import load


T2_CONFIG_FORMAT = "socialflux_t2_source_adaptation_config_v2"
T2_REQUIRED_ROUTES = (
    "appraisal",
    "response",
    "t2_spec_authoring",
    "t2_branch_authoring",
    "t2_pair_review",
    "t2_answer",
    "t2_answer_review",
)


def load_t2_config(root, config_path):
    root = Path(root).resolve()
    config_path = Path(config_path).resolve()
    config = load(config_path)
    if config.get("format") != T2_CONFIG_FORMAT:
        raise ValueError(f"T2 config format must be {T2_CONFIG_FORMAT}")

    route_path = (root / config["model_routes"]).resolve()
    routes = ModelRoutes.load(route_path).require(T2_REQUIRED_ROUTES)
    validate_single_model_assignment(
        config.get("model_assignment"),
        [routes.provider_config(name) for name in T2_REQUIRED_ROUTES],
        require_explicit=True,
        has_versioned_routes=True,
    )

    pair_source = (root / config["pair_spec_source"]).resolve()
    pair_document = load(pair_source)
    specs = pair_document.get("pairs")
    if not isinstance(specs, list) or not specs:
        raise ValueError("T2 pair spec source requires non-empty pairs")
    return config, specs, pair_source, routes
