#!/usr/bin/env python3
"""Directly author fresh Scale300 candidates with Claude Fable.

This path never reads an older scenario catalog. It creates a narrative,
machine-screens it, normalizes a blueprint, proposes S0/D0, and emits a
schema-valid candidate that remains pending human Gate 1.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prompts.loader import prompt_manifest, render_prompt
from providers.factory import build_provider, public_provider_config
from providers.model_routes import ModelRoutes
from providers.structured import complete_json
from schemas.validate import (
    QUALITY_CHECKS,
    validate_blueprint,
    validate_initial_state_proposal,
    validate_quality_report,
    validate_scenario,
)
from scripts.scenario_docs import write_document


DEFAULT_ROUTES = Path("configs/model_routes.frontier_api.json")
REQUIRED_BRIEF_FIELDS = {
    "scenario_id",
    "source_type",
    "provenance_id",
    "mechanism",
    "relationship_structure",
    "power_structure",
    "goal_conflict",
    "information_asymmetry",
    "history_dependency",
    "coverage_requirements",
}
BLUEPRINT_FIELDS = {
    "scenario_id",
    "title",
    "mechanism",
    "source",
    "narrative_design",
    "background",
    "environment_agent",
    "evaluated_agent_role",
    "selected_state_variables",
    "target_state_ids",
    "multimodal_event_concepts",
    "suggested_horizon",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _validate_brief(value):
    if not isinstance(value, dict) or set(value) != REQUIRED_BRIEF_FIELDS:
        raise ValueError(
            "authoring brief fields mismatch: expected "
            f"{sorted(REQUIRED_BRIEF_FIELDS)}"
        )
    if value["source_type"] != "synthetic-script":
        raise ValueError("direct smoke authoring currently requires synthetic-script")
    for field in REQUIRED_BRIEF_FIELDS - {"history_dependency", "coverage_requirements"}:
        if not isinstance(value[field], str) or not value[field].strip():
            raise ValueError(f"brief {field} must be non-empty text")
    history = value["history_dependency"]
    if not isinstance(history, list) or len(history) < 2 or any(
        not isinstance(item, str) or not item.strip() for item in history
    ):
        raise ValueError("brief history_dependency requires at least two text items")
    if not isinstance(value["coverage_requirements"], dict) or not value[
        "coverage_requirements"
    ]:
        raise ValueError("brief coverage_requirements must be a non-empty object")
    return value


def _quality_validator(value, source_type):
    validate_quality_report(value)
    if value["source_type"] != source_type:
        raise ValueError("quality report changed source_type")
    if value["review_status"] != "pending_human_review":
        raise ValueError("model quality review must remain pending_human_review")
    return value


def _blueprint_validator(value, brief):
    validate_blueprint(value)
    extra = set(value) - BLUEPRINT_FIELDS
    if extra:
        raise ValueError(f"blueprint contains unsupported fields: {sorted(extra)}")
    if value["scenario_id"] != brief["scenario_id"]:
        raise ValueError("blueprint changed scenario_id")
    source = value["source"]
    if source.get("type") != brief["source_type"]:
        raise ValueError("blueprint changed source_type")
    if source.get("provenance_id") != brief["provenance_id"]:
        raise ValueError("blueprint changed provenance_id")
    if value["evaluated_agent_role"].get("character_id") != "EVALUATED_AGENT":
        raise ValueError("evaluated character_id must be EVALUATED_AGENT")
    if value.get("suggested_horizon") != 20:
        raise ValueError("blueprint suggested_horizon must be 20")
    return value


def _assemble_candidate(blueprint, proposal, quality):
    scenario = deepcopy(blueprint)
    scenario.pop("multimodal_event_concepts", None)
    scenario.pop("suggested_horizon", None)
    for key in (
        "initial_state",
        "initial_dynamics",
        "observable_expression",
        "media_generation",
        "video_triggers",
        "max_turns",
        "t3_delayed_horizon",
        "sampling_plan",
    ):
        scenario[key] = deepcopy(proposal[key])
    scenario["construction_status"] = {
        "normalization": "claude_fable5_direct_candidate",
        "initial_state": "candidate_pending_human_freeze",
        "quality_gate": "pending_human_review",
    }
    scenario["quality_gate"] = deepcopy(quality["checks"])
    scenario["initialization_notes"] = {
        "rationale": deepcopy(proposal["rationale"]),
        "trigger_reachability": deepcopy(proposal["trigger_reachability"]),
    }
    validate_scenario(scenario)
    return scenario


def _metrics(providers):
    return {
        name: deepcopy(getattr(provider, "metrics", {}))
        for name, provider in providers.items()
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--brief", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-routes", type=Path, default=DEFAULT_ROUTES)
    parser.add_argument("--seed", type=int, default=510001)
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args(argv)

    if args.max_attempts < 1:
        raise ValueError("--max-attempts must be positive")
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError("output directory is not empty; use a new versioned path")

    brief = _validate_brief(json.loads(args.brief.read_text(encoding="utf-8")))
    routes = ModelRoutes.load(args.model_routes).require([
        "scenario_authoring",
        "quality_review",
        "scenario_normalization",
        "scenario_initialization",
    ])
    route_configs = {
        name: routes.provider_config(name)
        for name in (
            "scenario_authoring",
            "quality_review",
            "scenario_normalization",
            "scenario_initialization",
        )
    }
    if {item.get("model") for item in route_configs.values()} != {
        "claude-fable-5"
    }:
        raise ValueError("direct authoring requires claude-fable-5 for every role")
    providers = {
        name: build_provider(config)
        for name, config in route_configs.items()
    }
    args.output.mkdir(parents=True, exist_ok=True)
    started = _now()

    source_text = providers["scenario_authoring"].complete(
        [{
            "role": "user",
            "content": render_prompt("scenario_script_generation_v1", brief),
        }],
        temperature=0.75,
        top_p=0.92,
        seed=args.seed,
    ).strip()
    source_path = args.output / "source.md"
    source_path.write_text(source_text + "\n", encoding="utf-8")

    quality = complete_json(
        providers["quality_review"],
        [{
            "role": "user",
            "content": render_prompt("scenario_quality_gate_v1", {
                "source_type": brief["source_type"],
                "provenance_id": brief["provenance_id"],
                "source_material": source_text,
            }),
        }],
        {"temperature": 0.1, "top_p": 0.9, "seed": args.seed + 1},
        lambda value: _quality_validator(value, brief["source_type"]),
        context=f"scenario source quality {brief['scenario_id']}",
        max_attempts=args.max_attempts,
    )
    _atomic_json(args.output / "source_quality.json", quality)
    machine_pass = (
        quality["recommendation"] == "pass"
        and set(quality["checks"]) == QUALITY_CHECKS
        and set(quality["checks"].values()) == {"pass"}
    )
    if not machine_pass:
        _atomic_json(args.output / "run_manifest.json", {
            "format": "socialflux_direct_scenario_authoring_run_v1",
            "status": "stopped_at_machine_quality",
            "scenario_id": brief["scenario_id"],
            "started_at_utc": started,
            "finished_at_utc": _now(),
            "model_routes_sha256": routes.sha256,
            "provider_metrics": _metrics(providers),
            "human_gate1": "pending",
        })
        print(json.dumps({
            "status": "stopped_at_machine_quality",
            "recommendation": quality["recommendation"],
            "checks": quality["checks"],
        }, ensure_ascii=False))
        raise SystemExit(2)

    blueprint = complete_json(
        providers["scenario_normalization"],
        [{
            "role": "user",
            "content": render_prompt("scenario_candidate_normalization_v1", {
                "requested_identity": {
                    "scenario_id": brief["scenario_id"],
                    "source_type": brief["source_type"],
                    "provenance_id": brief["provenance_id"],
                },
                "construction_brief": brief,
                "machine_quality_evidence": quality,
                "source_material": source_text,
                "human_gate1": "pending",
            }),
        }],
        {"temperature": 0.35, "top_p": 0.9, "seed": args.seed + 2},
        lambda value: _blueprint_validator(value, brief),
        context=f"scenario blueprint {brief['scenario_id']}",
        max_attempts=args.max_attempts,
    )
    _atomic_json(args.output / "blueprint.json", blueprint)

    proposal = complete_json(
        providers["scenario_initialization"],
        [{
            "role": "user",
            "content": render_prompt(
                "scenario_candidate_initialization_v1", blueprint
            ),
        }],
        {"temperature": 0.3, "top_p": 0.9, "seed": args.seed + 3},
        lambda value: validate_initial_state_proposal(value, blueprint),
        context=f"scenario initialization {brief['scenario_id']}",
        max_attempts=args.max_attempts,
    )
    _atomic_json(args.output / "initial_state_proposal.json", proposal)

    scenario = _assemble_candidate(blueprint, proposal, quality)
    scenario_dir = args.output / "scenarios" / "scenario_001"
    scenario_path = scenario_dir / "scenario_001.json"
    _atomic_json(scenario_path, scenario)
    write_document(scenario_path)

    manifest = {
        "format": "socialflux_direct_scenario_authoring_run_v1",
        "status": "candidate_generated_pending_human_gate1",
        "scenario_id": brief["scenario_id"],
        "started_at_utc": started,
        "finished_at_utc": _now(),
        "model_routes_sha256": routes.sha256,
        "prompts": {
            prompt_id: prompt_manifest()["prompts"][prompt_id]
            for prompt_id in (
                "scenario_script_generation_v1",
                "scenario_quality_gate_v1",
                "scenario_candidate_normalization_v1",
                "scenario_candidate_initialization_v1",
            )
        },
        "providers": {
            name: public_provider_config(config)
            for name, config in route_configs.items()
        },
        "provider_metrics": _metrics(providers),
        "machine_quality": quality,
        "scenario_file": str(scenario_path),
        "human_gate1": "pending",
    }
    _atomic_json(args.output / "run_manifest.json", manifest)
    print(json.dumps({
        "status": manifest["status"],
        "scenario_id": brief["scenario_id"],
        "scenario_file": str(scenario_path),
        "provider_metrics": manifest["provider_metrics"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
