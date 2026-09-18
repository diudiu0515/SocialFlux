"""Model-backed review profiles used by quality-screening entry points."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from providers.factory import public_provider_config
from providers.model_assignment import validate_single_model_assignment
from providers.model_routes import ModelRoutes


REVIEW_CONFIG_FORMAT = "socialflux_review_models_v1"
REVIEW_PROFILES = (
    "rollout_primary",
    "rollout_secondary",
    "instance_quality",
)


def load_review_config(path):
    path = Path(path)
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("format") != REVIEW_CONFIG_FORMAT:
        raise ValueError(f"review config format must be {REVIEW_CONFIG_FORMAT}")
    route_reference = config.get("model_routes")
    if not isinstance(route_reference, str) or not route_reference.strip():
        raise ValueError("review config requires model_routes")
    route_path = Path(route_reference)
    if not route_path.is_absolute():
        route_path = path.resolve().parent / route_path
    routes = ModelRoutes.load(route_path)

    profiles = config.get("profiles")
    if not isinstance(profiles, dict) or set(profiles) != set(REVIEW_PROFILES):
        raise ValueError(f"review profiles must be {list(REVIEW_PROFILES)}")
    bindings = {}
    for name, profile in profiles.items():
        reference = profile.get("provider")
        if not isinstance(reference, dict) or "model_route" not in reference:
            raise ValueError(f"review profile {name} must use model_route")
        bindings[name] = reference["model_route"]
        profile["provider"] = routes.resolve(reference)
        if not isinstance(profile.get("sampling", {}), dict):
            raise ValueError(f"review profile {name} sampling must be an object")

    provenance = {
        "path": str(route_path.resolve()),
        "sha256": routes.sha256,
        "bindings": bindings,
    }
    validate_single_model_assignment(
        config.get("model_assignment"),
        [profile["provider"] for profile in profiles.values()],
        require_explicit=True,
        has_versioned_routes=True,
    )
    config["model_routes_provenance"] = provenance
    return config


def public_review_profile(config, name):
    if name not in REVIEW_PROFILES:
        raise ValueError(f"unknown review profile: {name}")
    profile = config["profiles"][name]
    return {
        "profile": name,
        "provider": public_provider_config(profile["provider"]),
        "sampling": deepcopy(profile.get("sampling", {})),
        "model_assignment": deepcopy(config["model_assignment"]),
        "model_routes": deepcopy(config["model_routes_provenance"]),
    }
