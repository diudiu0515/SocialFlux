#!/usr/bin/env python3
"""Narrative-first scenario sourcing with explicit review gates."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prompts.loader import render_prompt
from providers.factory import build_provider
from schemas.validate import (
    validate_blueprint,
    validate_initial_state_proposal,
    validate_quality_report,
    validate_scenario,
)


def _provider(path):
    return build_provider(json.loads(Path(path).read_text(encoding="utf-8")))


def _complete(provider, prompt_id, payload, sampling):
    return provider.complete(
        [{"role": "user", "content": render_prompt(prompt_id, payload)}],
        **sampling,
    )


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def generate_script(args):
    brief = json.loads(args.input.read_text(encoding="utf-8"))
    text = _complete(_provider(args.provider_config), "scenario_script_generation_v1", brief, {
        "temperature": args.temperature,
        "seed": args.seed,
    })
    _write(args.output, text.strip() + "\n")


def quality_check(args):
    payload = {
        "source_type": args.source_type,
        "provenance_id": args.provenance_id,
        "source_material": args.input.read_text(encoding="utf-8"),
    }
    report = json.loads(_complete(
        _provider(args.provider_config),
        "scenario_quality_gate_v1",
        payload,
        {"temperature": 0, "seed": args.seed},
    ))
    validate_quality_report(report)
    if report["review_status"] != "pending_human_review":
        raise ValueError("model quality report must remain pending_human_review")
    _write(args.output, json.dumps(report, ensure_ascii=False, indent=2) + "\n")


def normalize(args):
    quality = json.loads(args.quality_report.read_text(encoding="utf-8"))
    validate_quality_report(quality)
    if quality["review_status"] != "approved":
        raise ValueError("source quality report requires real reviewer approval")
    if quality["recommendation"] != "pass" or set(quality["checks"].values()) != {"pass"}:
        raise ValueError("all source quality checks must pass before normalization")
    payload = {
        "source_type": args.source_type,
        "provenance_id": args.provenance_id,
        "approved_quality_report": quality,
        "approved_source": args.input.read_text(encoding="utf-8"),
    }
    blueprint = json.loads(_complete(
        _provider(args.provider_config),
        "scenario_normalization_v1",
        payload,
        {"temperature": args.temperature, "seed": args.seed},
    ))
    validate_blueprint(blueprint)
    if blueprint["source"]["type"] != args.source_type:
        raise ValueError("normalized source type does not match the approved source")
    _write(args.output, json.dumps(blueprint, ensure_ascii=False, indent=2) + "\n")


def initialize(args):
    blueprint = json.loads(args.input.read_text(encoding="utf-8"))
    validate_blueprint(blueprint)
    proposal = json.loads(_complete(
        _provider(args.provider_config),
        "initial_state_configuration_v1",
        blueprint,
        {"temperature": args.temperature, "seed": args.seed},
    ))
    validate_initial_state_proposal(proposal, blueprint)
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
        scenario[key] = proposal[key]
    scenario["initialization_notes"] = {
        "rationale": proposal["rationale"],
        "trigger_reachability": proposal["trigger_reachability"],
    }
    scenario["construction_status"] = {
        "normalization": "model_normalized_pending_human_review",
        "initial_state": "candidate_pending_human_freeze",
        "quality_gate": "approved",
    }
    scenario["quality_gate"] = {
        key: "pass"
        for key in (
            "social_plausibility",
            "real_tradeoff",
            "longitudinal_necessity",
            "nontrivial_strategy_space",
            "character_motivation_coherence",
            "information_asymmetry",
            "t1_suitability",
            "t2_suitability",
            "t3_suitability",
            "t4_adaptation_opportunity",
            "no_universal_script",
        )
    }
    validate_scenario(scenario)
    _write(args.output, json.dumps(scenario, ensure_ascii=False, indent=2) + "\n")


def _add_source_args(parser):
    parser.add_argument(
        "--source-type",
        choices=("narrative-derived", "synthetic-script"),
        required=True,
    )
    parser.add_argument("--provenance-id", required=True)


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--input", type=Path, required=True)
    common.add_argument("--provider-config", type=Path, required=True)
    common.add_argument("--output", type=Path, required=True)
    common.add_argument("--temperature", type=float, default=0.7)
    common.add_argument("--seed", type=int, default=0)

    script_parser = subparsers.add_parser("generate-script", parents=[common])
    script_parser.set_defaults(func=generate_script)

    gate_parser = subparsers.add_parser("quality-check", parents=[common])
    _add_source_args(gate_parser)
    gate_parser.set_defaults(func=quality_check)

    normalize_parser = subparsers.add_parser("normalize", parents=[common])
    _add_source_args(normalize_parser)
    normalize_parser.add_argument("--quality-report", type=Path, required=True)
    normalize_parser.set_defaults(func=normalize)

    init_parser = subparsers.add_parser("initialize", parents=[common])
    init_parser.set_defaults(func=initialize)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
