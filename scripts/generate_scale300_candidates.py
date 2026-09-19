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
from providers.structured import StructuredOutputError, complete_json
from schemas.validate import (
    QUALITY_CHECKS,
    STATE_CONTRACT_VERSION,
    validate_blueprint,
    validate_initial_state_proposal,
    validate_quality_report,
    validate_scenario,
    validate_v2_dynamics,
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
    "state_contract_version",
    "environment_agent",
    "evaluated_agent_role",
    "selected_state_variables",
    "target_state_ids",
    "multimodal_event_concepts",
    "suggested_horizon",
}
BLUEPRINT_CORE_FIELDS = {
    "scenario_id",
    "title",
    "mechanism",
    "source",
    "narrative_design",
    "background",
}
BLUEPRINT_RUNTIME_FIELDS = BLUEPRINT_FIELDS - BLUEPRINT_CORE_FIELDS
INITIAL_STATE_CORE_FIELDS = {
    "initial_state",
    "initial_dynamics",
    "max_turns",
    "t3_delayed_horizon",
    "sampling_plan",
    "rationale",
    "status",
}
INITIAL_PRESENTATION_FIELDS = {
    "observable_expression",
    "media_generation",
    "video_triggers",
    "trigger_reachability",
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
    if value["source_type"] not in {"narrative-derived", "synthetic-script"}:
        raise ValueError("direct authoring requires a supported source type")
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
    if value.get("state_contract_version") != STATE_CONTRACT_VERSION:
        raise ValueError(
            f"blueprint state_contract_version must be {STATE_CONTRACT_VERSION}"
        )
    source = value["source"]
    if source.get("type") != brief["source_type"]:
        raise ValueError("blueprint changed source_type")
    if source.get("provenance_id") != brief["provenance_id"]:
        raise ValueError("blueprint changed provenance_id")
    if value["evaluated_agent_role"].get("character_id") != "EVALUATED_AGENT":
        raise ValueError("evaluated character_id must be EVALUATED_AGENT")
    persona = value["environment_agent"].get("persona")
    if not isinstance(persona, dict):
        raise ValueError("environment persona must be an object")
    if not all(
        isinstance(persona.get(key), str) and persona[key].strip()
        for key in ("name", "role")
    ):
        raise ValueError("environment persona requires text name and role")
    if value.get("suggested_horizon") != 20:
        raise ValueError("blueprint suggested_horizon must be 20")
    return value


def _blueprint_core_validator(value, brief):
    if not isinstance(value, dict) or set(value) != BLUEPRINT_CORE_FIELDS:
        raise ValueError(
            f"blueprint core fields mismatch: expected {sorted(BLUEPRINT_CORE_FIELDS)}"
        )
    if value["scenario_id"] != brief["scenario_id"]:
        raise ValueError("blueprint core changed scenario_id")
    for field in ("title", "mechanism", "background"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ValueError(f"blueprint core {field} must be non-empty text")
    source = value["source"]
    if not isinstance(source, dict):
        raise ValueError("blueprint core source must be an object")
    if source.get("type") != brief["source_type"]:
        raise ValueError("blueprint core changed source_type")
    if source.get("provenance_id") != brief["provenance_id"]:
        raise ValueError("blueprint core changed provenance_id")
    if source.get("surface_text_policy") != "original_surface_text":
        raise ValueError("blueprint core source must preserve original surface text")
    if not isinstance(source.get("redistribution_status"), str):
        raise ValueError("blueprint core requires redistribution_status")
    narrative = value["narrative_design"]
    required = {
        "relationship_structure",
        "power_structure",
        "goal_conflict",
        "information_asymmetry",
        "relevant_history",
        "meaningful_choice_space",
    }
    if not isinstance(narrative, dict) or set(narrative) != required:
        raise ValueError("blueprint core narrative_design fields mismatch")
    for field in (
        "relationship_structure", "power_structure", "goal_conflict",
        "information_asymmetry",
    ):
        if not isinstance(narrative[field], str) or not narrative[field].strip():
            raise ValueError(f"blueprint core narrative_design.{field} must be text")
    for field, minimum, maximum in (
        ("relevant_history", 1, 5),
        ("meaningful_choice_space", 3, 6),
    ):
        items = narrative[field]
        if (
            not isinstance(items, list)
            or not minimum <= len(items) <= maximum
            or any(not isinstance(item, str) or not item.strip() for item in items)
        ):
            raise ValueError(
                f"blueprint core narrative_design.{field} must contain "
                f"{minimum}-{maximum} non-empty text items"
            )
    return value


def _blueprint_runtime_validator(value, core, brief):
    if not isinstance(value, dict) or set(value) != BLUEPRINT_RUNTIME_FIELDS:
        raise ValueError(
            "blueprint runtime fields mismatch: expected "
            f"{sorted(BLUEPRINT_RUNTIME_FIELDS)}"
        )
    return _blueprint_validator({**core, **value}, brief)


def _assert_bounded_values(value, label):
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{label} must be a non-empty object")
    for key, item in value.items():
        path = f"{label}.{key}"
        if isinstance(item, dict):
            _assert_bounded_values(item, path)
        elif (
            not isinstance(item, (int, float))
            or isinstance(item, bool)
            or not 0 <= item <= 10
        ):
            raise ValueError(f"{path} must be numeric in [0, 10]")


def _initial_state_core_validator(value, blueprint):
    if not isinstance(value, dict) or set(value) != INITIAL_STATE_CORE_FIELDS:
        raise ValueError("initial-state core fields mismatch")
    if value["status"] != "candidate_pending_human_freeze":
        raise ValueError("initial-state core must remain pending human freeze")
    if value["max_turns"] != 20:
        raise ValueError("initial-state core max_turns must be 20")
    if not isinstance(value["t3_delayed_horizon"], int) or not (
        5 <= value["t3_delayed_horizon"] <= 10
    ):
        raise ValueError("initial-state core t3 horizon must be in [5, 10]")
    _assert_bounded_values(value["initial_state"], "initial_state")
    _assert_bounded_values(value["initial_dynamics"], "initial_dynamics")
    validate_v2_dynamics(value["initial_dynamics"])
    selected = blueprint["selected_state_variables"]
    if set(value["initial_state"]) != set(selected):
        raise ValueError("initial-state families do not match selected variables")
    for family, variables in selected.items():
        if set(value["initial_state"][family]) != set(variables):
            raise ValueError(
                f"initial-state variables do not match selected family {family}"
            )
    if not isinstance(value["sampling_plan"], dict):
        raise ValueError("initial-state core sampling_plan must be an object")
    if not isinstance(value["rationale"], dict) or not value["rationale"]:
        raise ValueError("initial-state core rationale must be non-empty")
    return value


def _initial_presentation_validator(value, state_core, blueprint):
    if not isinstance(value, dict) or set(value) != INITIAL_PRESENTATION_FIELDS:
        raise ValueError("initial presentation fields mismatch")
    proposal = {**state_core, **value}
    validate_initial_state_proposal(proposal, blueprint)
    return proposal


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
        "normalization": "model_direct_candidate_pending_human_gate1",
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
    values = {}
    for name, provider in providers.items():
        metrics = deepcopy(getattr(provider, "metrics", {}))
        if not metrics:
            metrics = {"request_count": int(getattr(provider, "_call_index", 0) or 0)}
        values[name] = metrics
    return values


def _run_stage(stage, callback, output, providers):
    try:
        return callback()
    except Exception as exc:
        failure = {
            "format": "socialflux_direct_scenario_authoring_failure_v1",
            "status": "failed",
            "stage": stage,
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
            "recorded_at_utc": _now(),
            "provider_metrics": _metrics(providers),
        }
        if isinstance(exc, StructuredOutputError):
            failure["structured_diagnostics"] = deepcopy(exc.diagnostics)
        _atomic_json(Path(output) / "run_failure.json", failure)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--brief", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-routes", type=Path, default=DEFAULT_ROUTES)
    parser.add_argument("--seed", type=int, default=510001)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--expected-model", default="claude-fable-5")
    parser.add_argument(
        "--continue-after-machine-quality",
        action="store_true",
        help=(
            "Continue normalizing a schema-valid candidate when the machine "
            "quality screen recommends rejection. The screen remains recorded "
            "and human Gate 1 remains pending."
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="reuse each validated stage artifact and continue from the first missing stage",
    )
    parser.add_argument(
        "--rebuild-private-layer",
        action="store_true",
        help=(
            "reuse source, quality, and blueprint core, but regenerate stable Persona, "
            "state vocabulary, S0/D0, and presentation under the current contract"
        ),
    )
    args = parser.parse_args(argv)

    if args.max_attempts < 1:
        raise ValueError("--max-attempts must be positive")
    if args.rebuild_private_layer and not args.resume:
        raise ValueError("--rebuild-private-layer requires --resume")
    if args.output.exists() and any(args.output.iterdir()) and not args.resume:
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
        args.expected_model
    }:
        raise ValueError(
            f"direct authoring requires {args.expected_model} for every role"
        )
    providers = {
        name: build_provider(config)
        for name, config in route_configs.items()
    }
    args.output.mkdir(parents=True, exist_ok=True)
    started = _now()

    source_path = args.output / "source.md"
    if args.resume and source_path.exists():
        source_text = source_path.read_text(encoding="utf-8").strip()
        if not source_text:
            raise ValueError("saved source.md is empty")
    else:
        source_text = _run_stage("scenario_authoring", lambda: providers["scenario_authoring"].complete(
            [{
                "role": "user",
                "content": render_prompt("scenario_candidate_script_v1", brief),
            }],
            temperature=0.75,
            top_p=0.92,
            seed=args.seed,
        ).strip(), args.output, providers)
        source_path.write_text(source_text + "\n", encoding="utf-8")

    quality_path = args.output / "source_quality.json"
    if args.resume and quality_path.exists():
        quality = _quality_validator(
            json.loads(quality_path.read_text(encoding="utf-8")),
            brief["source_type"],
        )
    else:
        quality = _run_stage("quality_review", lambda: complete_json(
            providers["quality_review"],
            [{
                "role": "user",
                "content": render_prompt("scenario_candidate_quality_gate_v1", {
                    "source_type": brief["source_type"],
                    "provenance_id": brief["provenance_id"],
                    "source_material": source_text,
                }),
            }],
            {"temperature": 0.1, "top_p": 0.9, "seed": args.seed + 1},
            lambda value: _quality_validator(value, brief["source_type"]),
            context=f"scenario source quality {brief['scenario_id']}",
            max_attempts=args.max_attempts,
        ), args.output, providers)
        _atomic_json(quality_path, quality)
    machine_pass = (
        quality["recommendation"] == "pass"
        and set(quality["checks"]) == QUALITY_CHECKS
        and set(quality["checks"].values()) == {"pass"}
    )
    if not machine_pass and not args.continue_after_machine_quality:
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

    blueprint_path = args.output / "blueprint.json"
    if args.resume and blueprint_path.exists() and not args.rebuild_private_layer:
        blueprint = _blueprint_validator(
            json.loads(blueprint_path.read_text(encoding="utf-8")), brief
        )
    else:
        core_path = args.output / "blueprint_core.json"
        if args.resume and core_path.exists():
            core = _blueprint_core_validator(
                json.loads(core_path.read_text(encoding="utf-8")), brief
            )
        else:
            core = _run_stage("blueprint_core", lambda: complete_json(
                providers["scenario_normalization"],
                [{
                    "role": "user",
                    "content": render_prompt("scenario_candidate_core_v1", {
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
                {
                    "temperature": 0.3,
                    "top_p": 0.9,
                    "seed": args.seed + 2,
                    "max_tokens": 1800,
                },
                lambda value: _blueprint_core_validator(value, brief),
                context=f"scenario blueprint core {brief['scenario_id']}",
                max_attempts=args.max_attempts,
            ), args.output, providers)
            _atomic_json(core_path, core)

        runtime_path = args.output / "blueprint_runtime.json"
        if args.resume and runtime_path.exists() and not args.rebuild_private_layer:
            runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
            blueprint = _blueprint_runtime_validator(runtime, core, brief)
        else:
            runtime = _run_stage("blueprint_runtime", lambda: complete_json(
                providers["scenario_normalization"],
                [{
                    "role": "user",
                    "content": render_prompt("scenario_candidate_runtime_design_v1", {
                        "blueprint_core": core,
                        "construction_brief": brief,
                        "source_material": source_text,
                        "human_gate1": "pending",
                    }),
                }],
                {
                    "temperature": 0.3,
                    "top_p": 0.9,
                    "seed": args.seed + 3,
                    "max_tokens": 1800,
                },
                lambda value: (
                    _blueprint_runtime_validator(value, core, brief)
                    and value
                ),
                context=f"scenario blueprint runtime {brief['scenario_id']}",
                max_attempts=args.max_attempts,
            ), args.output, providers)
            _atomic_json(runtime_path, runtime)
            blueprint = _blueprint_runtime_validator(runtime, core, brief)
        _atomic_json(blueprint_path, blueprint)

    proposal_path = args.output / "initial_state_proposal.json"
    if args.resume and proposal_path.exists() and not args.rebuild_private_layer:
        proposal = validate_initial_state_proposal(
            json.loads(proposal_path.read_text(encoding="utf-8")), blueprint
        )
    else:
        state_core_path = args.output / "initial_state_core.json"
        if args.resume and state_core_path.exists() and not args.rebuild_private_layer:
            state_core = _initial_state_core_validator(
                json.loads(state_core_path.read_text(encoding="utf-8")), blueprint
            )
        else:
            state_core = _run_stage("initial_state_core", lambda: complete_json(
                providers["scenario_initialization"],
                [{
                    "role": "user",
                    "content": render_prompt(
                        "scenario_candidate_state_values_v1", blueprint
                    ),
                }],
                {
                    "temperature": 0.25,
                    "top_p": 0.9,
                    "seed": args.seed + 4,
                    "max_tokens": 1600,
                },
                lambda value: _initial_state_core_validator(value, blueprint),
                context=f"scenario state values {brief['scenario_id']}",
                max_attempts=args.max_attempts,
            ), args.output, providers)
            _atomic_json(state_core_path, state_core)

        presentation_path = args.output / "initial_presentation.json"
        if args.resume and presentation_path.exists() and not args.rebuild_private_layer:
            presentation = json.loads(
                presentation_path.read_text(encoding="utf-8")
            )
            proposal = _initial_presentation_validator(
                presentation, state_core, blueprint
            )
        else:
            presentation = _run_stage("initial_presentation", lambda: complete_json(
                providers["scenario_initialization"],
                [{
                    "role": "user",
                    "content": render_prompt(
                        "scenario_candidate_expression_triggers_v1",
                        {"blueprint": blueprint, "state_values": state_core},
                    ),
                }],
                {
                    "temperature": 0.25,
                    "top_p": 0.9,
                    "seed": args.seed + 5,
                    "max_tokens": 1200,
                },
                lambda value: (
                    _initial_presentation_validator(
                        value, state_core, blueprint
                    )
                    and value
                ),
                context=f"scenario expression triggers {brief['scenario_id']}",
                max_attempts=args.max_attempts,
            ), args.output, providers)
            _atomic_json(presentation_path, presentation)
            proposal = _initial_presentation_validator(
                presentation, state_core, blueprint
            )
        _atomic_json(proposal_path, proposal)

    scenario = _assemble_candidate(blueprint, proposal, quality)
    scenario_dir = args.output / "scenarios" / "scenario_001"
    scenario_path = scenario_dir / "scenario_001.json"
    _atomic_json(scenario_path, scenario)
    write_document(scenario_path)

    manifest = {
        "format": "socialflux_direct_scenario_authoring_run_v1",
        "status": "candidate_generated_pending_human_gate1",
        "scenario_id": brief["scenario_id"],
        "authoring_model": args.expected_model,
        "started_at_utc": started,
        "finished_at_utc": _now(),
        "model_routes_sha256": routes.sha256,
        "prompts": {
            prompt_id: prompt_manifest()["prompts"][prompt_id]
            for prompt_id in (
                "scenario_candidate_script_v1",
                "scenario_candidate_quality_gate_v1",
                "scenario_candidate_core_v1",
                "scenario_candidate_runtime_design_v1",
                "scenario_candidate_state_values_v1",
                "scenario_candidate_expression_triggers_v1",
            )
        },
        "providers": {
            name: public_provider_config(config)
            for name, config in route_configs.items()
        },
        "provider_metrics": _metrics(providers),
        "machine_quality": quality,
        "machine_quality_passed": machine_pass,
        "admission_mode": (
            "human_postfilter"
            if args.continue_after_machine_quality
            else "machine_quality_precheck"
        ),
        "scenario_file": str(scenario_path),
        "human_gate1": "pending",
        "resumed": args.resume,
    }
    _atomic_json(args.output / "run_manifest.json", manifest)
    (args.output / "run_failure.json").unlink(missing_ok=True)
    print(json.dumps({
        "status": manifest["status"],
        "scenario_id": brief["scenario_id"],
        "scenario_file": str(scenario_path),
        "provider_metrics": manifest["provider_metrics"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
