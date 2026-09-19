#!/usr/bin/env python3
"""Generate the formal 50-scenario GPT design-audit batch for human Gate 1.

This entry point never reads an existing scenario, rollout, task package, or
Qwen artifact. GPT first designs versioned construction briefs with the
fixed prompt, then the existing fixed direct-authoring prompts create each
canonical scenario candidate.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.model_routes import ModelRoutes
from schemas.validate import validate_scenario
from scripts.generate_scale300_candidates import (
    REQUIRED_BRIEF_FIELDS,
    _validate_brief,
)
from scripts.scenario_docs import write_catalog, write_document


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROUTES = ROOT / "configs" / "gpt50_experiment" / "model_routes.astra.json"
DEFAULT_OUTPUT = ROOT / "data" / "gpt50" / "experiment" / "scenario"
TOTAL_COUNT = 50
NARRATIVE_COUNT = 15
RUN_FORMAT = "socialflux_gpt50_scenario_run_v1"


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_type_for_ordinal(ordinal):
    """Interleave an exact 3:7 narrative/synthetic allocation."""
    if not 1 <= ordinal <= TOTAL_COUNT:
        raise ValueError(f"ordinal must be in 1..{TOTAL_COUNT}")
    return "narrative-derived" if (ordinal - 1) % 10 < 3 else "synthetic-script"


def requested_identity(ordinal):
    source_type = source_type_for_ordinal(ordinal)
    family = "screen" if source_type == "narrative-derived" else "synthetic"
    return {
        "scenario_id": f"GPT50_{ordinal:03d}",
        "source_type": source_type,
        "provenance_id": f"gpt6-astra-{family}-{ordinal:03d}",
        "ordinal": ordinal,
    }


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")


def validate_brief_batch(value, requested):
    if not isinstance(value, dict) or set(value) != {"briefs"}:
        raise ValueError("brief batch must contain exactly the briefs key")
    briefs = value["briefs"]
    if not isinstance(briefs, list) or len(briefs) != len(requested):
        raise ValueError("brief batch count mismatch")
    for brief, identity in zip(briefs, requested):
        _validate_brief(brief)
        for key in ("scenario_id", "source_type", "provenance_id"):
            if brief[key] != identity[key]:
                raise ValueError(f"brief changed requested {key}")
        coverage = brief["coverage_requirements"]
        for key in (
            "domain",
            "opening_condition",
            "choice_space",
            "longitudinal_need",
            "originality_boundary",
        ):
            _text(coverage.get(key), f"coverage_requirements.{key}")
        if brief["source_type"] == "narrative-derived":
            work = coverage.get("source_work")
            if not isinstance(work, dict) or set(work) != {"title", "medium"}:
                raise ValueError("narrative brief requires exact source_work")
            _text(work["title"], "source_work.title")
            if work["medium"] not in {"film", "television"}:
                raise ValueError("source_work.medium must be film or television")
            if coverage.get("adaptation_policy") != (
                "structural_abstraction_only_original_surface_text"
            ):
                raise ValueError("narrative brief adaptation policy mismatch")
        else:
            if "source_work" in coverage:
                raise ValueError("synthetic brief must not name a source work")
            if coverage.get("origin_policy") != (
                "fully_original_synthetic_scenario"
            ):
                raise ValueError("synthetic brief origin policy mismatch")
    return briefs


def brief_path(output, ordinal):
    return Path(output) / "briefs" / f"scenario_{ordinal:03d}.json"


def scenario_path(output, ordinal):
    name = f"scenario_{ordinal:03d}"
    return Path(output) / "scenarios" / name / f"{name}.json"


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


DEFAULT_DESIGN_MATRIX = (
    ROOT / "configs" / "gpt50_experiment" / "scenario_matrix.json"
)


def load_design_matrix(path=DEFAULT_DESIGN_MATRIX):
    value = load_json(path)
    if set(value) != {"format", "source_works", "power_patterns", "contexts"}:
        raise ValueError("GPT50 design matrix fields mismatch")
    if value["format"] != "socialflux_gpt50_design_matrix_v1":
        raise ValueError("unsupported GPT50 design matrix format")
    works = value["source_works"]
    patterns = value["power_patterns"]
    contexts = value["contexts"]
    if len(works) != NARRATIVE_COUNT or len(contexts) != TOTAL_COUNT:
        raise ValueError("GPT50 design matrix population mismatch")
    if not patterns:
        raise ValueError("GPT50 design matrix requires power patterns")
    context_fields = {
        "domain", "relationship_structure", "goal_conflict",
        "information_asymmetry", "history_anchor", "verification_node",
    }
    for work in works:
        if (
            not isinstance(work, dict)
            or set(work) != {"title", "medium"}
            or not isinstance(work["title"], str)
            or not work["title"].strip()
            or work["medium"] not in {"film", "television"}
        ):
            raise ValueError("invalid GPT50 source work")
    for pattern in patterns:
        if not isinstance(pattern, dict) or set(pattern) != {
            "mechanism", "power_structure"
        }:
            raise ValueError("invalid GPT50 power pattern")
        _text(pattern["mechanism"], "power_patterns.mechanism")
        _text(pattern["power_structure"], "power_patterns.power_structure")
    for context in contexts:
        if not isinstance(context, dict) or set(context) != context_fields:
            raise ValueError("invalid GPT50 context fields")
        for key in context_fields:
            _text(context[key], f"contexts.{key}")
    domains = [item["domain"] for item in contexts]
    if len(domains) != len(set(domains)):
        raise ValueError("GPT50 context domains must be unique")
    return value


_DESIGN_MATRIX = load_design_matrix()
SOURCE_WORKS = tuple(
    (item["title"], item["medium"])
    for item in _DESIGN_MATRIX["source_works"]
)
POWER_PATTERNS = tuple(
    (item["mechanism"], item["power_structure"])
    for item in _DESIGN_MATRIX["power_patterns"]
)
CURATED_CONTEXTS = tuple(
    (
        item["domain"], item["relationship_structure"],
        item["goal_conflict"], item["information_asymmetry"],
        item["history_anchor"], item["verification_node"],
    )
    for item in _DESIGN_MATRIX["contexts"]
)

def curated_brief(ordinal):
    identity = requested_identity(ordinal)
    domain, relationship, conflict, asymmetry, history, verification = CURATED_CONTEXTS[ordinal - 1]
    mechanism, power = POWER_PATTERNS[(ordinal - 1) % len(POWER_PATTERNS)]
    coverage = {
        "domain": domain,
        "opening_condition": (
            f"Open at the decision deadline: {conflict}. The first exchange must "
            "contain a concrete request, not background exposition alone."
        ),
        "choice_space": (
            "Preserve at least three materially different paths: immediate action, "
            "bounded delay with verification, and a negotiated partial commitment."
        ),
        "longitudinal_need": (
            f"Keep the interaction open until this independently observable node: {verification}."
        ),
        "originality_boundary": (
            "All characters, organizations, facts, stakes, event sequences, and dialogue "
            "must be newly invented for this scenario."
        ),
        "state_variable_shape": (
            "selected_state_variables must map each family to a non-empty JSON array "
            "of variable IDs; never use a scalar string or a description object."
        ),
    }
    if identity["source_type"] == "narrative-derived":
        source_index = sum(
            source_type_for_ordinal(item) == "narrative-derived"
            for item in range(1, ordinal + 1)
        ) - 1
        title, medium = SOURCE_WORKS[source_index]
        coverage.update({
            "source_work": {"title": title, "medium": medium},
            "adaptation_policy": "structural_abstraction_only_original_surface_text",
        })
    else:
        coverage["origin_policy"] = "fully_original_synthetic_scenario"
    brief = {
        "scenario_id": identity["scenario_id"],
        "source_type": identity["source_type"],
        "provenance_id": identity["provenance_id"],
        "mechanism": mechanism,
        "relationship_structure": relationship,
        "power_structure": power,
        "goal_conflict": conflict,
        "information_asymmetry": asymmetry,
        "history_dependency": [history, verification],
        "coverage_requirements": coverage,
    }
    return _validate_brief(brief)


def generate_briefs(args, routes):
    del routes
    output = args.output.resolve()
    generated = [curated_brief(ordinal) for ordinal in range(1, args.count + 1)]
    for ordinal, brief in enumerate(generated, start=1):
        atomic_json(brief_path(output, ordinal), brief)
    counts = {
        source: sum(item["source_type"] == source for item in generated)
        for source in ("narrative-derived", "synthetic-script")
    }
    expected_narrative = sum(
        source_type_for_ordinal(ordinal) == "narrative-derived"
        for ordinal in range(1, args.count + 1)
    )
    if counts["narrative-derived"] != expected_narrative:
        raise ValueError("brief source allocation drifted")
    domains = [item["coverage_requirements"]["domain"] for item in generated]
    if len(domains) != len(set(domains)):
        raise ValueError("curated brief domains must be unique")
    atomic_json(output / "brief_manifest.json", {
        "format": "socialflux_gpt50_brief_manifest_v1",
        "created_at_utc": now(),
        "brief_count": len(generated),
        "source_counts": counts,
        "target_full_batch_ratio": "15 narrative-derived : 35 synthetic-script",
        "design_source": "versioned_deterministic_coverage_matrix",
        "design_matrix": {
            "path": str(DEFAULT_DESIGN_MATRIX.relative_to(ROOT)),
            "sha256": sha256_file(DEFAULT_DESIGN_MATRIX),
        },
        "authoring_model": "gpt-6-astra",
        "parent_catalog": None,
        "qwen_inputs": [],
        "human_review": "pending",
        "briefs": [
            {
                "ordinal": ordinal,
                "scenario_id": brief["scenario_id"],
                "source_type": brief["source_type"],
                "path": str(brief_path(output, ordinal).relative_to(ROOT)),
                "sha256": sha256_file(brief_path(output, ordinal)),
            }
            for ordinal, brief in enumerate(generated, start=1)
        ],
    })
    print(json.dumps({
        "stage": "briefs",
        "completed": len(generated),
        "expected": args.count,
        "design_source": "versioned_deterministic_coverage_matrix",
    }, ensure_ascii=False), flush=True)
    return generated

def _scenario_complete(output, ordinal, routes_sha256):
    target = scenario_path(output, ordinal)
    run = Path(output) / "authoring" / f"scenario_{ordinal:03d}" / "run_manifest.json"
    if not target.exists() or not run.exists():
        return False
    manifest = load_json(run)
    if (
        manifest.get("status") != "candidate_generated_pending_human_gate1"
        or manifest.get("model_routes_sha256") != routes_sha256
    ):
        return False
    validate_scenario(load_json(target))
    return True


def author_one(args, routes, ordinal):
    output = args.output.resolve()
    target = scenario_path(output, ordinal)
    if args.resume and _scenario_complete(output, ordinal, routes.sha256):
        return {
            "ordinal": ordinal,
            "scenario_id": requested_identity(ordinal)["scenario_id"],
            "status": "resumed",
            "scenario_file": str(target.relative_to(ROOT)),
        }
    run_dir = output / "authoring" / f"scenario_{ordinal:03d}"
    command = [
        sys.executable,
        str(ROOT / "scripts" / "generate_scale300_candidates.py"),
        "--brief", str(brief_path(output, ordinal)),
        "--output", str(run_dir),
        "--model-routes", str(args.model_routes),
        "--seed", str(args.seed + ordinal * 100),
        "--max-attempts", str(args.max_attempts),
        "--expected-model", "gpt-6-astra",
        "--continue-after-machine-quality",
    ]
    if args.resume and run_dir.exists():
        command.append("--resume")
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=args.scenario_timeout,
    )
    if completed.returncode:
        return {
            "ordinal": ordinal,
            "scenario_id": requested_identity(ordinal)["scenario_id"],
            "status": "failed",
            "returncode": completed.returncode,
            "output_tail": completed.stdout[-6000:],
        }
    source = run_dir / "scenarios" / "scenario_001" / "scenario_001.json"
    scenario = load_json(source)
    brief = load_json(brief_path(output, ordinal))
    if scenario["scenario_id"] != brief["scenario_id"]:
        raise ValueError(f"scenario identity mismatch for ordinal {ordinal}")
    if brief["source_type"] == "narrative-derived":
        work = brief["coverage_requirements"]["source_work"]
        scenario["source"]["provenance_note"] = (
            f"High-level social mechanism abstracted from {work['title']} "
            f"({work['medium']}); all characters, settings, facts, stakes, "
            "event sequences, and dialogue are original."
        )
    validate_scenario(scenario)
    atomic_json(target, scenario)
    write_document(target)
    manifest = load_json(run_dir / "run_manifest.json")
    return {
        "ordinal": ordinal,
        "scenario_id": scenario["scenario_id"],
        "status": "completed",
        "scenario_file": str(target.relative_to(ROOT)),
        "scenario_sha256": sha256_file(target),
        "machine_quality_passed": manifest.get("machine_quality_passed"),
        "provider_metrics": manifest.get("provider_metrics", {}),
    }


def write_gate1(output, count):
    records = []
    for ordinal in range(1, count + 1):
        path = scenario_path(output, ordinal)
        scenario = load_json(path)
        records.append({
            "scenario_id": scenario["scenario_id"],
            "ordinal": ordinal,
            "scenario_file": str(path.relative_to(ROOT)),
            "scenario_sha256": sha256_file(path),
            "reviewer": "",
            "reviewed_at_utc": "",
            "decision": "pending",
            "human_attestation": False,
            "attestations": {
                "variables_relevant": False,
                "values_justified": False,
                "no_policy_effect_baked_in": False,
                "initial_triggers_inactive": False,
                "multiple_future_paths_possible": False,
                "source_originalization_verified": False,
            },
            "quality_scores": {
                "social_plausibility": None,
                "character_coherence": None,
                "tradeoff_quality": None,
                "history_necessity": None,
                "interaction_richness": None,
                "t1_t4_suitability": None,
            },
            "notes": "",
        })
    atomic_json(Path(output) / "human_review" / "gate1_scenarios.json", {
        "format": "socialflux_gpt50_gate1_review_v1",
        "instructions": (
            "Review every fresh GPT design-audit candidate. Machine checks are "
            "diagnostic only and cannot set human_attestation."
        ),
        "population_count": count,
        "sample_count": count,
        "sampling": "full_population",
        "records": records,
    })


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model-routes", type=Path, default=DEFAULT_ROUTES)
    parser.add_argument("--count", type=int, default=TOTAL_COUNT)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--seed", type=int, default=915000)
    parser.add_argument("--scenario-timeout", type=int, default=3600)
    parser.add_argument("--briefs-only", action="store_true")
    parser.add_argument("--scenarios-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--allow-route-migration", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.count <= TOTAL_COUNT:
        parser.error(f"count must be in 1..{TOTAL_COUNT}")
    if not 1 <= args.workers <= 8:
        parser.error("workers must be in 1..8")
    if args.briefs_only and args.scenarios_only:
        parser.error("briefs-only and scenarios-only are mutually exclusive")
    args.output = args.output.resolve()
    if args.output.exists() and any(args.output.iterdir()) and not args.resume:
        raise ValueError("output is not empty; use --resume or a new versioned path")
    args.output.mkdir(parents=True, exist_ok=True)
    routes = ModelRoutes.load(args.model_routes).require([
        "scenario_authoring",
        "quality_review",
        "scenario_normalization",
        "scenario_initialization",
    ])
    if {
        routes.provider_config(name)["model"]
        for name in (
                "scenario_authoring",
            "quality_review",
            "scenario_normalization",
            "scenario_initialization",
        )
    } != {"gpt-6-astra"}:
        raise ValueError("every scenario stage must use gpt-6-astra")
    manifest_path = args.output / "run_manifest.json"
    manifest = {
        "format": RUN_FORMAT,
        "created_at_utc": now(),
        "status": "in_progress",
        "expected_count": args.count,
        "full_batch_source_ratio": {
            "narrative_derived": NARRATIVE_COUNT,
            "synthetic_script": TOTAL_COUNT - NARRATIVE_COUNT,
        },
        "model": "gpt-6-astra",
        "model_routes_sha256": routes.sha256,
        "model_route_history": [],
        "parent_catalog": None,
        "qwen_inputs": [],
        "gate_policy": "generate_all_then_human_postfilter",
        "results": [],
    }
    if manifest_path.exists() and args.resume:
        old = load_json(manifest_path)
        old_hash = old.get("model_routes_sha256")
        history = list(old.get("model_route_history") or [])
        if old_hash != routes.sha256:
            if not args.allow_route_migration:
                raise ValueError(
                    "model routes changed; use a new output directory or "
                    "--allow-route-migration"
                )
            history.append({
                "migrated_at_utc": now(),
                "from_sha256": old_hash,
                "to_sha256": routes.sha256,
                "to_path": str(Path(args.model_routes).resolve()),
                "reason": "explicit_endpoint_protocol_migration",
            })
        manifest["model_route_history"] = history
        manifest["created_at_utc"] = old.get("created_at_utc")
    atomic_json(manifest_path, manifest)
    if not args.scenarios_only:
        generate_briefs(args, routes)
    else:
        missing = [
            ordinal for ordinal in range(1, args.count + 1)
            if not brief_path(args.output, ordinal).exists()
        ]
        if missing:
            raise ValueError(f"missing briefs for scenarios-only mode: {missing[:5]}")
    if args.briefs_only:
        manifest["status"] = "briefs_completed"
        manifest["finished_at_utc"] = now()
        atomic_json(manifest_path, manifest)
        return
    results = {}

    def record(result):
        results[result["ordinal"]] = result
        manifest["results"] = [
            results[key] for key in sorted(results)
        ]
        manifest["completed_count"] = sum(
            item["status"] in {"completed", "resumed"}
            for item in results.values()
        )
        manifest["failed_count"] = sum(
            item["status"] == "failed" for item in results.values()
        )
        manifest["updated_at_utc"] = now()
        atomic_json(manifest_path, manifest)
        print(json.dumps({
            "stage": "scenarios",
            "completed": len(results),
            "expected": args.count,
            **result,
        }, ensure_ascii=False), flush=True)

    if args.workers == 1:
        for ordinal in range(1, args.count + 1):
            result = author_one(args, routes, ordinal)
            record(result)
            if result["status"] == "failed":
                break
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(author_one, args, routes, ordinal): ordinal
                for ordinal in range(1, args.count + 1)
            }
            for future in as_completed(futures):
                record(future.result())
    complete = all(
        results[ordinal]["status"] in {"completed", "resumed"}
        for ordinal in range(1, args.count + 1)
    )
    if complete:
        write_catalog(args.output / "scenarios")
        write_gate1(args.output, args.count)
    manifest["status"] = "completed" if complete else "completed_with_failures"
    manifest["finished_at_utc"] = now()
    atomic_json(manifest_path, manifest)
    print(json.dumps({
        "status": manifest["status"],
        "completed": manifest.get("completed_count", 0),
        "failed": manifest.get("failed_count", 0),
        "output": str(args.output),
    }, ensure_ascii=False))
    if not complete:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
