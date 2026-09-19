#!/usr/bin/env python3
"""Generate a fresh 150-scenario Claude-Fable catalog for human post-filtering.

This entry point never reads an existing scenario, rollout, task package, or
Qwen artifact. Claude first designs versioned construction briefs with the
fixed prompt, then the existing fixed direct-authoring prompts create each
canonical scenario candidate.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prompts.loader import prompt_manifest, render_prompt
from providers.factory import build_provider, public_provider_config
from providers.model_routes import ModelRoutes
from providers.structured import complete_json
from schemas.validate import validate_scenario
from scripts.generate_scale300_candidates import (
    REQUIRED_BRIEF_FIELDS,
    _validate_brief,
)
from scripts.scenario_docs import write_catalog, write_document


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROUTES = ROOT / "configs" / "claude150_v1" / "model_routes.json"
DEFAULT_OUTPUT = ROOT / "data" / "claude150_v1"
BATCH_SIZE = 5
TOTAL_COUNT = 150
NARRATIVE_COUNT = 45
BRIEF_FORMAT = "socialflux_claude150_brief_batch_v1"
RUN_FORMAT = "socialflux_claude150_scenario_run_v1"


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
        "scenario_id": f"CF150_{ordinal:03d}",
        "source_type": source_type,
        "provenance_id": f"claude-fable5-{family}-{ordinal:03d}",
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


def brief_signature(brief):
    coverage = brief["coverage_requirements"]
    return {
        "scenario_id": brief["scenario_id"],
        "source_type": brief["source_type"],
        "mechanism": brief["mechanism"],
        "relationship_structure": brief["relationship_structure"],
        "power_structure": brief["power_structure"],
        "domain": coverage["domain"],
        "source_work": deepcopy(coverage.get("source_work")),
    }


def brief_path(output, ordinal):
    return Path(output) / "briefs" / f"scenario_{ordinal:03d}.json"


def scenario_path(output, ordinal):
    name = f"scenario_{ordinal:03d}"
    return Path(output) / "scenarios" / name / f"{name}.json"


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def generate_briefs(args, routes):
    route_config = routes.provider_config("scenario_brief_design")
    if route_config.get("model") != "claude-fable-5":
        raise ValueError("brief design requires claude-fable-5")
    provider = build_provider(route_config)
    output = args.output.resolve()
    generated = []
    for start in range(1, args.count + 1, args.batch_size):
        ordinals = list(range(start, min(start + args.batch_size, args.count + 1)))
        requested = [requested_identity(ordinal) for ordinal in ordinals]
        batch_number = (start - 1) // args.batch_size + 1
        batch_path = output / "brief_batches" / f"batch_{batch_number:03d}.json"
        saved_paths = [brief_path(output, ordinal) for ordinal in ordinals]
        if args.resume and batch_path.exists() and all(path.exists() for path in saved_paths):
            saved = load_json(batch_path)
            briefs = validate_brief_batch({"briefs": saved["briefs"]}, requested)
        else:
            payload = {
                "batch_format": BRIEF_FORMAT,
                "requested": requested,
                "source_ratio": {
                    "narrative_derived": NARRATIVE_COUNT,
                    "synthetic_script": TOTAL_COUNT - NARRATIVE_COUNT,
                    "total": TOTAL_COUNT,
                },
                "prior_signatures": [brief_signature(item) for item in generated],
                "parent_catalog": None,
                "forbidden_inputs": [
                    "old scenarios",
                    "old rollouts",
                    "old tasks",
                    "Qwen outputs",
                ],
            }
            value = complete_json(
                provider,
                [{
                    "role": "user",
                    "content": render_prompt("scenario_brief_batch_v1", payload),
                }],
                {
                    "temperature": 0.75,
                    "top_p": 0.92,
                    "seed": args.seed + batch_number,
                },
                lambda item: (
                    validate_brief_batch(item, requested)
                    and item
                ),
                context=f"Claude150 brief batch {batch_number}",
                max_attempts=args.max_attempts,
                retry_guidance=(
                    "Return exactly the requested identities and source types. "
                    "Narrative-derived records require source_work and adaptation_policy; "
                    "synthetic records require origin_policy and no source_work."
                ),
            )
            briefs = value["briefs"]
            atomic_json(batch_path, {
                "format": BRIEF_FORMAT,
                "batch_number": batch_number,
                "ordinals": ordinals,
                "briefs": briefs,
                "model_provenance": public_provider_config(route_config),
                "prompt": prompt_manifest()["prompts"]["scenario_brief_batch_v1"],
                "human_review": "pending",
            })
            for ordinal, brief in zip(ordinals, briefs):
                atomic_json(brief_path(output, ordinal), brief)
        generated.extend(briefs)
        print(json.dumps({
            "stage": "briefs",
            "completed": len(generated),
            "expected": args.count,
            "batch": batch_number,
        }, ensure_ascii=False), flush=True)
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
    atomic_json(output / "brief_manifest.json", {
        "format": "socialflux_claude150_brief_manifest_v1",
        "created_at_utc": now(),
        "brief_count": len(generated),
        "source_counts": counts,
        "target_full_batch_ratio": "45 narrative-derived : 105 synthetic-script",
        "authoring_model": "claude-fable-5",
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
    scenario = load_json(target)
    validate_scenario(scenario)
    if scenario.get("state_contract_version") != "socialflux_state_v2":
        return False
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
        "--expected-model", "claude-fable-5",
        "--continue-after-machine-quality",
    ]
    if args.resume and run_dir.exists():
        command.extend(("--resume", "--rebuild-private-layer"))
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
        "format": "socialflux_claude150_gate1_review_v1",
        "instructions": (
            "Review every fresh Claude-Fable candidate. Machine checks are "
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
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--workers", type=int, default=4)
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
    if not 1 <= args.batch_size <= 10:
        parser.error("batch-size must be in 1..10")
    if not 1 <= args.workers <= 8:
        parser.error("workers must be in 1..8")
    if args.briefs_only and args.scenarios_only:
        parser.error("briefs-only and scenarios-only are mutually exclusive")
    args.output = args.output.resolve()
    if args.output.exists() and any(args.output.iterdir()) and not args.resume:
        raise ValueError("output is not empty; use --resume or a new versioned path")
    args.output.mkdir(parents=True, exist_ok=True)
    routes = ModelRoutes.load(args.model_routes).require([
        "scenario_brief_design",
        "scenario_authoring",
        "quality_review",
        "scenario_normalization",
        "scenario_initialization",
    ])
    if {
        routes.provider_config(name)["model"]
        for name in (
            "scenario_brief_design",
            "scenario_authoring",
            "quality_review",
            "scenario_normalization",
            "scenario_initialization",
        )
    } != {"claude-fable-5"}:
        raise ValueError("every scenario stage must use claude-fable-5")
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
        "model": "claude-fable-5",
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
