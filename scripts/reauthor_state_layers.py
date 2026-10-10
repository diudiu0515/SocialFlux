#!/usr/bin/env python3
"""Reauthor scenario state layers while keeping the public scenario frozen."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from environment.state_ontology import (
    EVIDENCE_FEATURE_COMPATIBILITY,
    FAMILY_RULES,
    STATE_ONTOLOGY_VERSION,
    STATE_VARIABLE_ONTOLOGY,
    VARIABLE_RULES,
)
from environment.state_transition_contract import validate_state_v3_scenario
from prompts.loader import prompt_manifest, render_prompt
from providers.factory import build_provider, public_provider_config
from providers.model_routes import ModelRoutes
from providers.structured import complete_json
from schemas.validate import STATE_VARIABLE_ONTOLOGY as APPROVED_STATE_VARIABLES
from schemas.validate import validate_scenario
from scripts.scenario_docs import assert_document_current, write_document


PROMPT_ID = "scenario_state_reauthoring_v1"
FAMILIES = (
    "emotion",
    "behavioral_disposition",
    "relationship",
    "consequence_risk",
)
FAMILY_RANGES = {
    "emotion": (3, 4),
    "behavioral_disposition": (2, 3),
    "relationship": (2, 3),
    "consequence_risk": (2, 3),
}


def now():
    return datetime.now(timezone.utc).isoformat()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def is_provider_overload(error):
    """Recognize a transient provider overload through wrapped exceptions."""
    current = error
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if getattr(current, "status", None) == 429:
            return True
        message = str(current).casefold()
        if "http 429" in message or "overloaded" in message:
            return True
        current = current.__cause__ or current.__context__
    return False


def failure_record(path, error):
    failure = {
        "scenario": str(path),
        "error_type": type(error).__name__,
        "error": str(error),
    }
    diagnostics = getattr(error, "diagnostics", None)
    if diagnostics:
        failure["validation_attempts"] = deepcopy(diagnostics)
    last_error = getattr(error, "last_error", None)
    if last_error is not None:
        failure["last_validation_error"] = {
            "error_type": type(last_error).__name__,
            "error": str(last_error),
        }
    return failure


def flatten_selected(selected):
    return {
        f"{family}.{variable}"
        for family, variables in selected.items()
        for variable in variables
    }


def flatten_numeric(values):
    result = {}
    for family, variables in values.items():
        for variable, value in variables.items():
            result[f"{family}.{variable}"] = value
    return result


def compact_ontology():
    result = {}
    for path, entry in STATE_VARIABLE_ONTOLOGY.items():
        family = path.split(".", 1)[0]
        result[path] = {
            **deepcopy(entry),
            "timescale": VARIABLE_RULES.get(path, {}).get(
                "timescale", FAMILY_RULES[family]["timescale"]
            ),
            "evidence_features": sorted(
                EVIDENCE_FEATURE_COMPATIBILITY[path]
            ),
        }
    return result


def scenario_payload(scenario):
    return {
        "scenario": {
            key: deepcopy(scenario.get(key))
            for key in (
                "scenario_id",
                "title",
                "mechanism",
                "background",
                "narrative_design",
                "environment_agent",
                "evaluated_agent_role",
                "initial_state",
                "initial_dynamics",
            )
        },
        "ownership_rule": (
            "All mutable state belongs to environment_agent, never evaluated_agent."
        ),
        "approved_ontology": compact_ontology(),
    }


def validate_layer(value, scenario):
    expected = {
        "ontology_version",
        "selected_state_variables",
        "target_state_ids",
        "initial_state",
        "rationale",
        "transition_evidence_plan",
        "video_triggers",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"state layer must contain exactly {sorted(expected)}")
    if value["ontology_version"] != STATE_ONTOLOGY_VERSION:
        raise ValueError("state layer changed ontology_version")

    selected = value["selected_state_variables"]
    if not isinstance(selected, dict) or set(selected) != set(FAMILIES):
        raise ValueError("selected_state_variables must use exactly four families")
    for family in FAMILIES:
        variables = selected[family]
        minimum, maximum = FAMILY_RANGES[family]
        if (
            not isinstance(variables, list)
            or not minimum <= len(variables) <= maximum
            or len(variables) != len(set(variables))
        ):
            raise ValueError(
                f"{family} must select {minimum}-{maximum} unique variables"
            )
        unknown = set(variables) - APPROVED_STATE_VARIABLES[family]
        if unknown:
            raise ValueError(f"{family} has unknown variables: {sorted(unknown)}")
    paths = flatten_selected(selected)
    if not 9 <= len(paths) <= 13:
        raise ValueError("state layer must select 9-13 variables")

    targets = value["target_state_ids"]
    if (
        not isinstance(targets, list)
        or not 6 <= len(targets) <= 9
        or len(targets) != len(set(targets))
        or not set(targets).issubset(paths)
    ):
        raise ValueError("target_state_ids must be 6-9 unique selected paths")
    target_families = {path.split(".", 1)[0] for path in targets}
    if target_families != set(FAMILIES):
        raise ValueError("target_state_ids must cover all four families")

    initial = value["initial_state"]
    if not isinstance(initial, dict) or set(initial) != set(FAMILIES):
        raise ValueError("initial_state family shape mismatch")
    for family, variables in selected.items():
        if not isinstance(initial.get(family), dict):
            raise ValueError(f"initial_state.{family} must be an object")
        if set(initial[family]) != set(variables):
            raise ValueError(f"initial_state.{family} variable shape mismatch")
    flat_initial = flatten_numeric(initial)
    if any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not 1 <= item <= 9
        for item in flat_initial.values()
    ):
        raise ValueError("initial state values must be numeric in [1, 9]")
    if len(set(flat_initial.values())) < 4:
        raise ValueError("initial state needs at least four distinct levels")

    name = scenario["environment_agent"]["persona"]["name"]
    evaluated_role = scenario["evaluated_agent_role"]
    evaluated_name = (
        (evaluated_role.get("persona") or {}).get("name")
        or evaluated_role["name"]
    )
    rationale = value["rationale"]
    if not isinstance(rationale, dict) or set(rationale) != set(FAMILIES):
        raise ValueError("rationale family shape mismatch")
    for family, variables in selected.items():
        if not isinstance(rationale.get(family), dict):
            raise ValueError(f"rationale.{family} must be an object")
        if set(rationale[family]) != set(variables):
            raise ValueError(f"rationale.{family} variable shape mismatch")
        for variable, text in rationale[family].items():
            path = f"{family}.{variable}"
            expected_prefix = (
                f"{name}'s {path} is initialized at "
                f"{initial[family][variable]} because "
            )
            if not isinstance(text, str) or not text.strip().startswith(
                expected_prefix
            ):
                raise ValueError(
                    f"rationale for {path} must begin with {expected_prefix!r}"
                )
            relationship_clause = f"because {name} believes {evaluated_name}"
            if family == "relationship" and relationship_clause not in text:
                raise ValueError(
                    f"relationship rationale for {path} must contain "
                    f"{relationship_clause!r}"
                )

    plan = value["transition_evidence_plan"]
    if not isinstance(plan, dict) or set(plan) != paths:
        raise ValueError("transition_evidence_plan must cover every selected path")
    for path, item in plan.items():
        if not isinstance(item, dict) or set(item) != {
            "increase_evidence", "decrease_evidence"
        }:
            raise ValueError(f"invalid transition evidence plan for {path}")
        if any(
            not isinstance(text, str) or not text.strip()
            for text in item.values()
        ):
            raise ValueError(f"transition evidence for {path} must be non-empty")
        for direction in ("increase", "decrease"):
            text = item[f"{direction}_evidence"].strip()
            expected_prefix = f"{evaluated_name} would "
            causal_marker = (
                f", causing {name}'s {path} to {direction} because "
            )
            if not text.startswith(expected_prefix) or causal_marker not in text:
                raise ValueError(
                    f"{direction} evidence for {path} must start with "
                    f"{expected_prefix!r} and contain {causal_marker!r}"
                )
        if item["increase_evidence"].strip() == item["decrease_evidence"].strip():
            raise ValueError(f"transition evidence directions collapse for {path}")

    candidate = assemble_scenario(scenario, value)
    validate_scenario(candidate)
    validate_state_v3_scenario(candidate)
    return value


def preserved_dynamics_rationale(scenario):
    old = (scenario.get("initialization_notes") or {}).get("rationale") or {}
    nested = None
    for key in ("initial_dynamics", "dynamics"):
        if isinstance(old.get(key), dict):
            nested = old[key]
            break
    result = {}
    for variable in scenario.get("initial_dynamics", {}):
        text = None
        if isinstance(nested, dict):
            text = nested.get(variable)
        if text is None:
            text = old.get(variable)
        result[variable] = (
            text if isinstance(text, str) and text.strip()
            else "Preserved from the frozen scenario dynamics seed."
        )
    return result


def assemble_scenario(scenario, layer):
    result = deepcopy(scenario)
    result["selected_state_variables"] = deepcopy(
        layer["selected_state_variables"]
    )
    result["target_state_ids"] = list(layer["target_state_ids"])
    result["initial_state"] = deepcopy(layer["initial_state"])
    result["video_triggers"] = deepcopy(layer["video_triggers"])
    result["state_ontology_version"] = layer["ontology_version"]
    result["initialization_notes"] = {
        "rationale": {
            **deepcopy(layer["rationale"]),
            "initial_dynamics": preserved_dynamics_rationale(scenario),
        },
        "state_transition_plan": deepcopy(layer["transition_evidence_plan"]),
        "trigger_reachability": [
            f"{item['trigger_id']} is metadata-only and pending human review."
            for item in layer["video_triggers"]
        ],
    }
    status = deepcopy(result.get("construction_status") or {})
    status["initial_state"] = "candidate_pending_human_freeze"
    result["construction_status"] = status
    return result


def output_paths(output_root, source_path):
    scenario_dir = output_root / source_path.parent.name
    return (
        scenario_dir / source_path.name,
        scenario_dir / "state_reauthoring.json",
    )


def reusable(output_path, artifact_path, source_path, prompt_entry):
    if not output_path.exists() or not artifact_path.exists():
        return False
    artifact = load_json(artifact_path)
    if (
        artifact.get("source_sha256") != sha256_file(source_path)
        or artifact.get("prompt") != prompt_entry
        or artifact.get("human_review") != "pending"
    ):
        return False
    try:
        candidate = load_json(output_path)
        validate_scenario(candidate)
        validate_state_v3_scenario(candidate)
    except (KeyError, TypeError, ValueError):
        return False
    try:
        assert_document_current(output_path)
    except ValueError:
        write_document(output_path)
    return True


def reauthor_one(source_path, output_root, routes_path, route_name, args):
    scenario = load_json(source_path)
    prompt_entry = prompt_manifest()["prompts"][PROMPT_ID]
    output_path, artifact_path = output_paths(output_root, source_path)
    if args.resume and reusable(
        output_path, artifact_path, source_path, prompt_entry
    ):
        return {"scenario_id": scenario["scenario_id"], "status": "reused"}

    routes = ModelRoutes.load(routes_path)
    route_config = routes.provider_config(route_name)
    provider = build_provider(route_config)
    payload = scenario_payload(scenario)
    layer = complete_json(
        provider,
        [{
            "role": "user",
            "content": render_prompt(PROMPT_ID, payload),
        }],
        {
            "temperature": args.temperature,
            "top_p": 0.9,
            "seed": args.seed + int(source_path.parent.name.rsplit("_", 1)[1]),
            "max_tokens": args.max_tokens,
        },
        lambda item: validate_layer(item, scenario),
        context=f"state reauthoring {scenario['scenario_id']}",
        max_attempts=args.max_attempts,
        retry_guidance=(
            "Keep state ownership on environment_agent. Use 9-13 approved "
            "variables with 3-4 emotions. selected_state_variables family lists "
            "must contain leaf names only, never family.variable paths. Begin "
            "every rationale with the complete "
            "exact environment_agent.persona.name. The bidirectional plan keyset "
            "must equal every selected path, not only targets, and must use only "
            "pre-update evidence. Use the exact '<evaluated> would <one action>, "
            "causing <environment>\'s <path> to increase/decrease because <reason "
            "about environment state>' form. Use the exact owner/path/value "
            "rationale prefix, and for relationship explain '<environment> "
            "believes <evaluated>'; never invert owner, other party, or person at risk. "
            "Select at least one turn_to_episode relationship variable and at "
            "least one cross_turn_slow relationship variable. "
            "Every trigger observable_expression must be an object such as "
            "{\"cue\":\"...\"}; state_change change_conditions must map exact "
            "numeric paths to operator/threshold objects. Threshold/crossing "
            "conditions must be inactive at S0."
        ),
    )
    candidate = assemble_scenario(scenario, layer)
    validate_scenario(candidate)
    atomic_json(output_path, candidate)
    document_path = write_document(output_path)
    atomic_json(artifact_path, {
        "format": "socialflux_state_reauthoring_v1",
        "scenario_id": scenario["scenario_id"],
        "created_at_utc": now(),
        "source_path": str(source_path),
        "source_sha256": sha256_file(source_path),
        "output_path": str(output_path),
        "output_sha256": sha256_file(output_path),
        "documentation_path": str(document_path),
        "documentation_sha256": sha256_file(document_path),
        "model": public_provider_config(route_config),
        "routes_sha256": routes.sha256,
        "prompt": prompt_entry,
        "state_ontology_version": STATE_ONTOLOGY_VERSION,
        "human_review": "pending",
        "layer": layer,
    })
    return {"scenario_id": scenario["scenario_id"], "status": "generated"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-routes", type=Path, required=True)
    parser.add_argument("--route", default="scenario_initialization")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=4200)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=39000)
    parser.add_argument(
        "--stop-on-provider-overload",
        action="store_true",
        help=(
            "with one worker, stop the batch after the first persistent HTTP "
            "429/overloaded error; already written artifacts remain reusable"
        ),
    )
    args = parser.parse_args()
    if args.stop_on_provider_overload and args.workers != 1:
        parser.error("--stop-on-provider-overload requires --workers 1")

    files = sorted(args.scenarios.glob("scenario_*/scenario_*.json"))
    if args.limit is not None:
        files = files[:args.limit]
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    failures = []

    if args.stop_on_provider_overload:
        for path in files:
            try:
                item = reauthor_one(
                    path,
                    args.output,
                    args.model_routes,
                    args.route,
                    args,
                )
                results.append(item)
                print(json.dumps(item, ensure_ascii=False), flush=True)
            except Exception as exc:
                failure = failure_record(path, exc)
                failures.append(failure)
                print(json.dumps(failure, ensure_ascii=False), flush=True)
                if is_provider_overload(exc):
                    break
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(
                    reauthor_one,
                    path,
                    args.output,
                    args.model_routes,
                    args.route,
                    args,
                ): path
                for path in files
            }
            for future in as_completed(futures):
                path = futures[future]
                try:
                    item = future.result()
                    results.append(item)
                    print(json.dumps(item, ensure_ascii=False), flush=True)
                except Exception as exc:
                    failure = failure_record(path, exc)
                    failures.append(failure)
                    print(json.dumps(failure, ensure_ascii=False), flush=True)

    available_artifact_count = sum(
        output_path.is_file() and artifact_path.is_file()
        for path in files
        for output_path, artifact_path in [output_paths(args.output, path)]
    )

    manifest = {
        "format": "socialflux_state_reauthoring_batch_v1",
        "created_at_utc": now(),
        "source_root": str(args.scenarios),
        "output_root": str(args.output),
        "expected": len(files),
        "completed": available_artifact_count,
        "failed": len(failures),
        "run_completed_count": len(results),
        "unprocessed_count": max(
            0, len(files) - available_artifact_count - len(failures)
        ),
        "state_ontology_version": STATE_ONTOLOGY_VERSION,
        "prompt": prompt_manifest()["prompts"][PROMPT_ID],
        "human_review": "pending",
        "results": sorted(results, key=lambda item: item["scenario_id"]),
        "failures": failures,
    }
    atomic_json(args.output / "manifest.json", manifest)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
