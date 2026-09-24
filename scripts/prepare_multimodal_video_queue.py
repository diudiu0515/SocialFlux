#!/usr/bin/env python3
"""Prepare offline important-node video API requests without network calls."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas.validate import validate_scenario, validate_trajectory
from environment.video_requests import (
    TALKING_HEAD_PROMPT_ID,
    build_video_request,
)
from scripts.audit_formal_rollout_pool import load_records
from scripts.run_environment_interventions import load_actual_scenarios


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "multimodal_generation.json"


def now():
    return datetime.now(timezone.utc).isoformat()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def flatten_numeric(value, prefix=""):
    result = {}
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else key
            result.update(flatten_numeric(item, path))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        result[prefix] = value
    return result


def importance(turn, turn_count):
    state = flatten_numeric(turn.get("numeric_state_delta", {}))
    dynamics = flatten_numeric(turn.get("numeric_dynamics_delta", {}))
    magnitude = sum(abs(value) for value in (*state.values(), *dynamics.values()))
    reasons = []
    score = float(magnitude)
    if magnitude:
        reasons.append("state_or_dynamics_change")
    if turn.get("trigger_events"):
        score += 4.0
        reasons.append("state_triggered_expression")
    claims = turn.get("response_consequential_claims") or []
    if claims:
        score += 3.0
        reasons.append("consequential_claim")
    ledger = turn.get("environment_response_ledger_events") or []
    consequential = {
        "commitment", "refusal", "boundary", "disclosure", "decision",
        "concession", "request",
    }
    if any(item.get("event_type") in consequential for item in ledger):
        score += 2.0
        reasons.append("socially_consequential_event")
    turn_id = int(str(turn.get("turn_id", "t0")).lstrip("t") or 0)
    if turn_id >= max(2, round(turn_count * 0.6)):
        score += 1.0
        reasons.append("history_bearing_late_checkpoint")
    return round(score, 4), reasons or ["coverage_checkpoint"]


def select_important_turns(trajectory, count, min_gap):
    turns = list(trajectory.get("turns", []))
    ranked = sorted(
        (
            (importance(turn, len(turns))[0], index, turn)
            for index, turn in enumerate(turns)
        ),
        key=lambda item: (-item[0], item[1]),
    )
    selected = []
    for score, index, turn in ranked:
        if any(abs(index - old_index) < min_gap for _, old_index, _ in selected):
            continue
        selected.append((score, index, turn))
        if len(selected) == count:
            break
    if len(selected) < min(count, len(turns)):
        for score, index, turn in ranked:
            if any(index == old_index for _, old_index, _ in selected):
                continue
            selected.append((score, index, turn))
            if len(selected) == min(count, len(turns)):
                break
    return sorted(selected, key=lambda item: item[1])


def observable_behavior(scenario, turn):
    value = turn.get("response_observable_behavior")
    if isinstance(value, dict) and any(value.values()):
        return value
    value = turn.get("observable_expression")
    if isinstance(value, dict) and any(value.values()):
        return value
    return scenario.get("observable_expression", {}).get("default", {})



def stable_review_sample(records, count):
    best_by_scenario = {}
    for record in records:
        current = best_by_scenario.get(record["scenario_id"])
        if current is None or record["importance_score"] > current["importance_score"]:
            best_by_scenario[record["scenario_id"]] = record
    ranked = sorted(
        best_by_scenario.values(),
        key=lambda item: hashlib.sha256(
            item["request_id"].encode("utf-8")
        ).hexdigest(),
    )
    return ranked[:count]


def prepare(args):
    config = load(args.config)
    if config.get("format") != "socialflux_multimodal_generation_v1":
        raise ValueError("invalid multimodal generation config format")
    if config.get("prompt_id") != TALKING_HEAD_PROMPT_ID:
        raise ValueError("multimodal config prompt_id mismatch")
    offline = config["offline"]
    nodes_per_trajectory = int(
        args.nodes_per_trajectory or offline["important_nodes_per_trajectory"]
    )
    videos_per_node = int(args.videos_per_node or offline["videos_per_node"])
    min_turn_gap = int(args.min_turn_gap or offline["min_turn_gap"])
    duration = float(args.duration_seconds) if args.duration_seconds else None
    if not 1 <= nodes_per_trajectory <= 8:
        raise ValueError("important nodes per trajectory must be in 1..8")
    if not 1 <= videos_per_node <= 3:
        raise ValueError("videos per node must be in 1..3")
    if min_turn_gap < 1:
        raise ValueError("min turn gap must be positive")

    scenarios_list = load_actual_scenarios(args.scenario_root)
    for scenario in scenarios_list:
        validate_scenario(scenario)
    scenarios = {item["scenario_id"]: item for item in scenarios_list}
    trajectories = load_records(args.rollout_root)
    for trajectory in trajectories:
        validate_trajectory(trajectory)
    if args.expected_count and len(trajectories) != args.expected_count:
        raise ValueError(
            f"expected {args.expected_count} trajectories, found {len(trajectories)}"
        )

    output = args.output or args.batch_root / "multimodal"
    requests_root = output / "requests"
    records = []
    for trajectory in sorted(trajectories, key=lambda item: item["scenario_id"]):
        scenario = scenarios[trajectory["scenario_id"]]
        selected = select_important_turns(
            trajectory, nodes_per_trajectory, min_turn_gap
        )
        for score, _, turn in selected:
            expression = observable_behavior(scenario, turn)
            response = str(turn.get("environment_response", "")).strip()
            if not response:
                raise ValueError(
                    f"empty environment response at {trajectory['trajectory_id']} "
                    f"{turn.get('turn_id')}"
                )
            _, reasons = importance(turn, len(trajectory["turns"]))
            for variant in range(1, videos_per_node + 1):
                request_id = (
                    f"{trajectory['scenario_id']}--{trajectory['trajectory_id']}--"
                    f"{turn['turn_id']}--v{variant}"
                )
                safe_name = hashlib.sha256(request_id.encode()).hexdigest()[:20]
                request_file = requests_root / f"{safe_name}.json"
                video_file = output / "assets" / f"{safe_name}.mp4"
                request = build_video_request(
                    scenario,
                    response,
                    expression,
                    duration_seconds=duration,
                    variant=variant,
                )
                atomic(request_file, request)
                records.append({
                    "request_id": request_id,
                    "scenario_id": trajectory["scenario_id"],
                    "trajectory_id": trajectory["trajectory_id"],
                    "turn_id": turn["turn_id"],
                    "variant": variant,
                    "importance_score": score,
                    "importance_reasons": reasons,
                    "request_file": str(request_file.relative_to(args.batch_root)),
                    "video_file": str(video_file.relative_to(args.batch_root)),
                    "status": "request_ready",
                    "public_action": turn.get("policy_action", {}).get("text", ""),
                    "public_response": response,
                    "observable_expression": expression,
                    "private_consistency_reference": {
                        "numeric_state_delta": turn.get("numeric_state_delta", {}),
                        "numeric_dynamics_delta": turn.get(
                            "numeric_dynamics_delta", {}
                        ),
                        "trigger_events": turn.get("trigger_events", []),
                    },
                })

    manifest = {
        "format": "socialflux_multimodal_video_queue_v1",
        "created_at_utc": now(),
        "batch_root": str(args.batch_root.resolve()),
        "mode": "offline_important_nodes",
        "prompt_id": TALKING_HEAD_PROMPT_ID,
        "network_requests_performed": 0,
        "provider_status": "awaiting_video_api_configuration",
        "trajectory_count": len(trajectories),
        "important_nodes_per_trajectory": nodes_per_trajectory,
        "videos_per_node": videos_per_node,
        "request_count": len(records),
        "requests": records,
    }
    atomic(output / "manifest.json", manifest)

    review_count = int(config["gate2"]["video_review_sample_count"])
    review_records = stable_review_sample(records, review_count)
    gate2 = {
        "format": "socialflux_environment_video_state_consistency_v1",
        "created_at_utc": now(),
        "record": {
            "human_attestation": False,
            "reviewers": [],
            "reviewed_at_utc": "",
            "review_status": "pending_video_api_and_review",
            "llm_review_status": "pending",
            "matched_node_count": len(review_records),
            "generated_video_count": 0,
            "request_safety_passed": all(
                all(value is False for value in load(
                    args.batch_root / item["request_file"]
                )["safety_check"].values())
                for item in review_records
            ),
            "machine_screen_passed": False,
            "passed": False,
        },
        "review_items": [
            {
                **item,
                "ratings": {
                    "state_expression_alignment": None,
                    "persona_consistency": None,
                    "temporal_continuity": None,
                    "lip_sync_and_speech_naturalness": None,
                    "no_private_state_leakage": None,
                    "overall": None,
                },
                "llm_review": "pending",
                "human_review": "pending",
            }
            for item in review_records
        ],
    }
    atomic(args.batch_root / "gate2" / "video_state_consistency.json", gate2)
    print(json.dumps({
        "trajectory_count": len(trajectories),
        "request_count": len(records),
        "gate2_review_items": len(review_records),
        "network_requests_performed": 0,
        "output": str(output),
    }, ensure_ascii=False, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument("--scenario-root", type=Path, required=True)
    parser.add_argument("--rollout-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--nodes-per-trajectory", type=int)
    parser.add_argument("--videos-per-node", type=int)
    parser.add_argument("--min-turn-gap", type=int)
    parser.add_argument("--duration-seconds", type=float)
    args = parser.parse_args(argv)
    prepare(args)


if __name__ == "__main__":
    main()
