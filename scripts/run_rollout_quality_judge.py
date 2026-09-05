#!/usr/bin/env python3
"""Run an independent schema-constrained judge over observable trajectories."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.rollout_gate import HARD_REJECT_REASONS, QUALITY_DIMENSIONS, public_judge_packet
from prompts.loader import render_prompt
from providers.factory import build_provider
from providers.factory import public_provider_config
from providers.structured import complete_json
from scripts.audit_formal_rollout_pool import load_records
from scripts.run_pipeline import load_scenarios


def validate(value, trajectory_id):
    if set(value) != {"trajectory_id", "scores", "hard_reject_reasons", "rationale"}:
        raise ValueError("quality judgment fields mismatch")
    if value["trajectory_id"] != trajectory_id:
        raise ValueError("quality judgment trajectory mismatch")
    if set(value["scores"]) != set(QUALITY_DIMENSIONS):
        raise ValueError("quality judgment score dimensions mismatch")
    if not all(isinstance(item, int) and 1 <= item <= 5 for item in value["scores"].values()):
        raise ValueError("quality scores must be integer 1..5")
    if set(value["hard_reject_reasons"]) - set(HARD_REJECT_REASONS):
        raise ValueError("quality judgment contains unknown hard reject")
    if not str(value["rationale"]).strip():
        raise ValueError("quality judgment rationale is empty")
    return value


def validate_model_family(model, declared_family):
    lowered = str(model).lower()
    aliases = {
        "qwen": ("qwen",),
        "glm": ("glm",),
        "deepseek": ("deepseek",),
        "mistral": ("mistral", "mixtral"),
        "kimi": ("kimi", "moonshot"),
        "claude": ("claude",),
        "openai": ("gpt", "o1", "o3", "o4"),
    }
    markers = aliases.get(declared_family.lower())
    if markers is None or not any(marker in lowered for marker in markers):
        raise ValueError(
            f"declared model family {declared_family!r} does not match model {model!r}"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--provider-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--judge-role", choices=("primary", "secondary"), required=True)
    parser.add_argument("--model-family", required=True)
    parser.add_argument(
        "--trajectory-id-file",
        type=Path,
        help="optional JSON selection emitted by merge_rollout_judgments.py",
    )
    args = parser.parse_args()
    provider_config = json.loads(args.provider_config.read_text(encoding="utf-8"))
    validate_model_family(provider_config["provider"].get("model"), args.model_family)
    provider = build_provider(provider_config["provider"])
    sampling = provider_config.get("sampling", {})
    selected_ids = None
    if args.trajectory_id_file:
        selection = json.loads(args.trajectory_id_file.read_text(encoding="utf-8"))
        selected_ids = set(selection.get("trajectory_ids", []))
        if not selected_ids:
            raise ValueError("trajectory selection is empty")
    records = []
    scenarios = {
        item["scenario_id"]: item for item in load_scenarios("configs/scenarios")
    }
    for trajectory in load_records(args.raw_root):
        trajectory_id = trajectory["trajectory_id"]
        if selected_ids is not None and trajectory_id not in selected_ids:
            continue
        prompt = render_prompt(
            "rollout_quality_judge_v1",
            public_judge_packet(trajectory, scenarios[trajectory["scenario_id"]]),
        )
        records.append(complete_json(
            provider,
            [{"role": "user", "content": prompt}],
            sampling,
            lambda value, trajectory_id=trajectory_id: validate(value, trajectory_id),
            context=f"quality judgment {trajectory_id}",
            max_attempts=5,
        ))
    if selected_ids is not None:
        judged_ids = {item["trajectory_id"] for item in records}
        missing = sorted(selected_ids - judged_ids)
        if missing:
            raise ValueError("selected trajectories were not found: " + ", ".join(missing))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({
            "format": "socialflux_rollout_quality_judgments_v1",
            "judge_role": args.judge_role,
            "model": provider_config["provider"].get("model"),
            "model_family": args.model_family,
            "provider": public_provider_config(provider_config["provider"]),
            "sampling": sampling,
            "records": records,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"judged": len(records), "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
