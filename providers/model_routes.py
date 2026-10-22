"""Versioned model-role routing for SocialFlux runs.

Business modules request a precise semantic role such as appraisal, t2_answer,
or t3_action_authoring.
This module is the only owner of the mapping from those
roles to serializable provider configs.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path


ROUTE_FORMAT = "socialflux_model_routes_v1"


class ModelRoutes:
    def __init__(self, document, *, source_path=None):
        if document.get("format") != ROUTE_FORMAT:
            raise ValueError(f"model route format must be {ROUTE_FORMAT}")
        routes = document.get("routes")
        if not isinstance(routes, dict) or not routes:
            raise ValueError("model route document requires non-empty routes")
        defaults = document.get("provider_defaults", {})
        if not isinstance(defaults, dict):
            raise ValueError("model route provider_defaults must be an object")
        if "api_key" in defaults:
            raise ValueError(
                "model route provider_defaults must use a secret reference"
            )
        self._routes = {
            name: {**deepcopy(defaults), **deepcopy(config)}
            for name, config in routes.items()
        }
        self.source_path = Path(source_path).resolve() if source_path else None
        for name, config in self._routes.items():
            self._validate(name, config)

    @classmethod
    def load(cls, path):
        path = Path(path).resolve()
        document = json.loads(path.read_text(encoding="utf-8"))
        return cls(document, source_path=path)

    @staticmethod
    def _validate(name, config):
        if not isinstance(config, dict):
            raise ValueError(f"model route {name} must be an object")
        if not config.get("provider") or not config.get("model"):
            raise ValueError(f"model route {name} requires provider and model")
        if "api_key" in config or "api_keys" in config:
            raise ValueError(
                f"model route {name} must use api_key_env; inline secrets are forbidden"
            )
        if config.get("provider") == "failover":
            candidates = config.get("candidates")
            if not isinstance(candidates, list) or not candidates:
                raise ValueError(
                    f"model route {name} failover requires non-empty candidates"
                )
            for index, candidate in enumerate(candidates):
                ModelRoutes._validate(f"{name}.candidate[{index}]", candidate)
            return
        endpoint_sources = [
            bool(config.get("endpoint")),
            bool(config.get("endpoint_env")),
        ]
        if sum(endpoint_sources) != 1:
            raise ValueError(
                f"model route {name} requires exactly one of endpoint or endpoint_env"
            )

    def provider_config(self, name):
        try:
            return deepcopy(self._routes[name])
        except KeyError as exc:
            raise ValueError(f"unknown model route: {name}") from exc

    def build_provider(self, name):
        from .factory import build_provider

        return build_provider(self.provider_config(name))

    def require(self, names):
        missing = sorted(set(names) - set(self._routes))
        if missing:
            raise ValueError(f"missing model routes: {missing}")
        return self


    def resolve(self, reference):
        if not isinstance(reference, dict):
            raise ValueError("provider reference must be an object")
        route_name = reference.get("model_route")
        if route_name is None:
            return deepcopy(reference)
        unsupported = set(reference) - {"model_route", "overrides"}
        if unsupported:
            raise ValueError(
                f"provider route reference has unsupported fields: {sorted(unsupported)}"
            )
        overrides = reference.get("overrides", {})
        if not isinstance(overrides, dict):
            raise ValueError("provider route overrides must be an object")
        return {**self.provider_config(route_name), **deepcopy(overrides)}

    @property
    def sha256(self):
        payload = json.dumps(
            self._routes,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @property
    def route_names(self):
        return tuple(sorted(self._routes))
