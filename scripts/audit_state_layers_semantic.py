#!/usr/bin/env python3
"""Run a model-assisted semantic precheck without signing human review."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from scripts.reauthor_state_layers import (
    atomic_json,
    compact_ontology,
    flatten_selected,
    load_json,
    sha256_file,
)


PROMPT_ID = "scenario_state_semantic_audit_v1"
FIELDS = {
    "selection",
    "initial_state",
    "rationale",
    "increase_evidence",
    "decrease_evidence",
    "video_trigger",
}
CODES = {
    "owner_inversion",
    "relationship_direction_inversion",
    "risk_bearer_inversion",
    "factual_role_inversion",
    "construct_mismatch",
    "direction_mismatch",
    "post_update_evidence",
    "unreachable_evidence",
    "redundant_construct",
    "correlated_state_reasoning",
    "trigger_semantic_mismatch",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def validate_audit(value, layer):
    if not isinstance(value, dict) or set(value) != {"decision", "issues"}:
        raise ValueError("semantic audit requires exactly decision and issues")
    if value["decision"] not in {"pass", "revise"}:
        raise ValueError("semantic audit decision must be pass or revise")
    issues = value["issues"]
    if not isinstance(issues, list):
        raise ValueError("semantic audit issues must be a list")
    if (value["decision"] == "pass") != (not issues):
        raise ValueError("pass requires no issues; revise requires issues")
    selected_paths = flatten_selected(layer["selected_state_variables"])
    trigger_ids = {
        item["trigger_id"] for item in layer.get("video_triggers", [])
    }
    for issue in issues:
        if not isinstance(issue, dict) or set(issue) != {
            "path", "field", "code", "reason"
        }:
            raise ValueError("every semantic issue requires path/field/code/reason")
        if issue["field"] not in FIELDS:
            raise ValueError(f"unsupported semantic issue field {issue['field']!r}")
        if issue["code"] not in CODES:
            raise ValueError(f"unsupported semantic issue code {issue['code']!r}")
        if issue["field"] == "video_trigger":
            if issue["path"] not in trigger_ids:
                raise ValueError("trigger issue path must be a trigger_id")
        elif issue["path"] not in selected_paths:
            raise ValueError("state issue path must be a selected family.variable")
        if not isinstance(issue["reason"], str) or not issue["reason"].strip():
            raise ValueError("semantic issue reason must be non-empty")
    return value


def payload_for(source, layer):
    return {
        "review_type": "machine_semantic_precheck_not_human_review",
        "runtime_order": (
            "evaluated action -> appraisal -> calibration -> state update -> "
            "environment response"
        ),
        "state_owner": source["environment_agent"]["persona"]["name"],
        "evaluated_participant": source["evaluated_agent_role"]["persona"]["name"],
        "frozen_scenario": source,
        "approved_ontology": compact_ontology(),
        "candidate_state_layer": layer,
    }


def audit_one(candidate_path, source_root, output_root, routes_path, route, args):
    candidate = load_json(candidate_path)
    scenario_dir = candidate_path.parent.name
    source_path = source_root / scenario_dir / candidate_path.name
    artifact_path = candidate_path.with_name("state_reauthoring.json")
    source = load_json(source_path)
    artifact = load_json(artifact_path)
    layer = artifact["layer"]
    routes = ModelRoutes.load(routes_path)
    route_config = routes.provider_config(route)
    provider = build_provider(route_config)
    diagnostics = []
    audit = complete_json(
        provider,
        [{
            "role": "user",
            "content": render_prompt(PROMPT_ID, payload_for(source, layer)),
        }],
        {
            "temperature": 0,
            "top_p": 0.9,
            "seed": args.seed + int(scenario_dir.rsplit("_", 1)[1]),
            "max_tokens": args.max_tokens,
        },
        lambda value: validate_audit(value, layer),
        context=f"state semantic audit {candidate['scenario_id']}",
        max_attempts=args.max_attempts,
        retry_guidance=(
            "This is a machine precheck, not human review. Do not repair the "
            "candidate. Report every owner, direction, construct, factual-role, "
            "reachability, runtime-order, redundancy, or trigger issue. State "
            "issue paths must be exact selected family.variable values; trigger "
            "paths must be exact trigger_id values. A counterfactual evaluated "
            "action described with 'would' is valid pre-appraisal evidence when "
            "it later occurs; only an environment response after update is "
            "post-update evidence."
        ),
        diagnostics_sink=diagnostics,
    )
    output_path = output_root / scenario_dir / "machine_semantic_audit.json"
    record = {
        "format": "socialflux_state_machine_semantic_audit_v1",
        "created_at_utc": now(),
        "scenario_id": candidate["scenario_id"],
        "audit_kind": "model_semantic_triage_not_gate_or_human_review",
        "source_path": str(source_path),
        "source_sha256": sha256_file(source_path),
        "candidate_path": str(candidate_path),
        "candidate_sha256": sha256_file(candidate_path),
        "state_reauthoring_sha256": sha256_file(artifact_path),
        "prompt": prompt_manifest()["prompts"][PROMPT_ID],
        "model": public_provider_config(route_config),
        "routes_sha256": routes.sha256,
        "human_review": "pending",
        "decision": audit["decision"],
        "issues": deepcopy(audit["issues"]),
        "retry_diagnostics": diagnostics,
    }
    atomic_json(output_path, record)
    return {
        "scenario_id": candidate["scenario_id"],
        "decision": audit["decision"],
        "issue_count": len(audit["issues"]),
        "output": str(output_path),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-routes", type=Path, required=True)
    parser.add_argument("--route", default="scenario_initialization")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--max-tokens", type=int, default=2600)
    parser.add_argument("--seed", type=int, default=39500)
    args = parser.parse_args()

    files = sorted(args.candidates.glob("scenario_*/scenario_*.json"))
    if args.limit is not None:
        files = files[:args.limit]
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                audit_one,
                path,
                args.scenarios,
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
                result = future.result()
                results.append(result)
                print(json.dumps(result, ensure_ascii=False), flush=True)
            except Exception as exc:
                failure = {
                    "candidate": str(path),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                diagnostics = getattr(exc, "diagnostics", None)
                if diagnostics:
                    failure["validation_attempts"] = deepcopy(diagnostics)
                failures.append(failure)
                print(json.dumps(failure, ensure_ascii=False), flush=True)

    manifest = {
        "format": "socialflux_state_machine_semantic_audit_batch_v1",
        "created_at_utc": now(),
        "audit_kind": "model_semantic_triage_not_gate_or_human_review",
        "candidate_root": str(args.candidates),
        "expected": len(files),
        "completed": len(results),
        "failed": len(failures),
        "passed": sum(item["decision"] == "pass" for item in results),
        "revise": sum(item["decision"] == "revise" for item in results),
        "human_review": "pending",
        "prompt": prompt_manifest()["prompts"][PROMPT_ID],
        "results": sorted(results, key=lambda item: item["scenario_id"]),
        "failures": failures,
    }
    atomic_json(args.output / "manifest.json", manifest)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
