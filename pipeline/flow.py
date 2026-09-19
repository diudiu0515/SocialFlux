"""Explicit stage graph and cheap preflight for the active pipeline."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from evaluation.review_configuration import load_review_config
from evaluation.t4_configuration import load_t4_config
from providers.model_routes import ModelRoutes
from rollout.configuration import load_rollout_config
from tasks.T2.configuration import T2_REQUIRED_ROUTES, load_t2_config

from .constants import (
    MODEL_ROUTES,
    REVIEW_CONFIG,
    ROLLOUT_CONFIG,
    SCENARIO_ROOT,
    T2_CONFIG,
    T4_CONFIG,
)
from .runtime import (
    assert_fable_providers,
    assert_fable_rollout_config,
    assert_fable_t4_config,
)
from .scenarios import load_scenario_records


class Stage(str, Enum):
    GATE_1 = "gate1"
    ROLLOUT = "rollout"
    GATE_2 = "gate2"
    GATE_3 = "gate3"
    TASKS = "tasks"
    T4 = "t4"
    GATE_4 = "gate4"


PIPELINE_STAGES = tuple(Stage)


@dataclass(frozen=True)
class PipelinePreflight:
    scenario_root: Path = SCENARIO_ROOT
    rollout_config: Path = ROLLOUT_CONFIG
    t4_config: Path = T4_CONFIG
    review_config: Path = REVIEW_CONFIG
    t2_config: Path = T2_CONFIG
    model_routes: Path = MODEL_ROUTES

    def run(self):
        records = load_scenario_records(self.scenario_root)
        config = load_rollout_config(self.rollout_config)
        assert_fable_rollout_config(config)
        t4 = load_t4_config(self.t4_config)
        assert_fable_t4_config(t4)
        reviews = load_review_config(self.review_config)
        assert_fable_providers(
            [profile["provider"] for profile in reviews["profiles"].values()],
            context="active review",
        )
        _, _, _, t2_routes = load_t2_config(Path("."), self.t2_config)
        assert_fable_providers(
            [t2_routes.provider_config(name) for name in T2_REQUIRED_ROUTES],
            context="active T2",
        )
        routes = ModelRoutes.load(self.model_routes)
        hashes = {
            routes.sha256,
            config["model_routes_provenance"]["sha256"],
            t4["model_routes_provenance"]["sha256"],
            reviews["model_routes_provenance"]["sha256"],
            t2_routes.sha256,
        }
        if len(hashes) != 1:
            raise ValueError("active configurations do not share one route-table hash")
        return {
            "scenario_count": len(records),
            "rollout_slots": len(records) * len(config["policies"]),
            "stages": [stage.value for stage in PIPELINE_STAGES],
            "model": config["model_assignment"]["model"],
            "t4_model": t4["evaluated_model"]["provider"]["model"],
            "route_table_sha256": routes.sha256,
            "active_configs": [
                str(self.rollout_config),
                str(self.review_config),
                str(self.t2_config),
                str(self.t4_config),
            ],
        }
