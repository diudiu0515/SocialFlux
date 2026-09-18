#!/usr/bin/env python3
"""Build a compact Scale150 generation/framework report without human claims."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "configs/scale150_v1/design_matrix.json"
OUTPUT = ROOT / "build/scale150_v1/review.json"
MARKDOWN = ROOT / "build/scale150_v1/review.md"
ROLLOUT_ROOTS = (
    ("qwen32_all", ROOT / "build/scale150_v1/rollouts_v2"),
    ("hybrid_pre_request_fix", ROOT / "build/scale150_v1/rollouts_hybrid"),
    ("hybrid_pre_schema_fix", ROOT / "build/scale150_v1/rollouts_hybrid_v2"),
    ("hybrid_frozen", ROOT / "build/scale150_v1/rollouts_hybrid_v3"),
    ("content_v2", ROOT / "build/scale150_v1/rollouts_content_v2"),
)
TARGET_COUNT = 150
REPORT_LABEL = "Scale150"
REPORT_FORMAT = "socialflux_scale150_review_v1"
MODEL_REVIEW_FILES = (
    ROOT / "build/scale150_v1/model_semantic_reviews.codex.json",
)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def nonzero(value):
    if isinstance(value, dict):
        return any(nonzero(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(nonzero(item) for item in value)
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value != 0


def artifact_for(root, shard, ordinal, attempt):
    scenario_dir = root / f"shard{shard}" / f"scenario_{ordinal:03d}"
    filename = attempt.get("trajectory_file") or attempt.get("partial_trajectory_file")
    if not filename:
        return None
    status = attempt.get("status")
    subdir = {
        "generation_error": "rejected",
        "short_natural_trajectory": "short_trajectories",
        "budget_truncated": "budget_truncated",
        "machine_rejected": "rejected",
    }.get(status)
    candidates = [scenario_dir / filename]
    if subdir:
        candidates.insert(0, scenario_dir / subdir / filename)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    matches = list(scenario_dir.rglob(filename))
    return matches[0] if len(matches) == 1 else None


def framework_audit(trajectory):
    turns = trajectory.get("turns", [])
    required = {
        "policy_action", "appraisal", "calibration", "state_before",
        "state_delta", "numeric_state_delta", "state_after", "dynamics_before",
        "dynamics_delta", "numeric_dynamics_delta", "dynamics_after",
        "interaction_ledger_before", "interaction_ledger_after",
        "environment_response", "environment_response_ledger_events",
    }
    chain_ok = bool(turns) and all(
        turns[index].get("state_before")
        == turns[index - 1].get("state_after_public_events", turns[index - 1].get("state_after"))
        and turns[index].get("dynamics_before")
        == turns[index - 1].get("dynamics_after_public_events", turns[index - 1].get("dynamics_after"))
        for index in range(1, len(turns))
    )
    requests = trajectory.get("actual_request_counts", {})
    return {
        "turn_count": len(turns),
        "contiguous_turn_ids": bool(turns) and [item.get("turn_id") for item in turns]
        == [f"t{index}" for index in range(1, len(turns) + 1)],
        "every_turn_has_appraisal_update_response_and_ledger": bool(turns) and all(
            required <= set(item) and bool(item.get("environment_response"))
            for item in turns
        ),
        "cross_turn_state_and_dynamics_chain": chain_ok,
        "environment_llm_stages_per_turn": requests.get("environment_stage_count_per_turn"),
        "separate_stage_request_counts_present": bool(turns) and all(
            int(requests.get(key, 0)) >= len(turns)
            for key in ("appraisal", "response")
        ),
        "changed_turn_count": sum(
            nonzero(item.get("numeric_state_delta", {}))
            or nonzero(item.get("numeric_dynamics_delta", {}))
            for item in turns
        ),
        "unchanged_turn_count": sum(
            not nonzero(item.get("numeric_state_delta", {}))
            and not nonzero(item.get("numeric_dynamics_delta", {}))
            for item in turns
        ),
    }


def main():
    matrix = read(MATRIX)
    rows = {item["scenario_id"]: item for item in matrix["scenarios"]}
    semantic_reviews = {}
    for review_path in MODEL_REVIEW_FILES:
        if not review_path.is_file():
            continue
        semantic_reviews.update({
            item.get("trajectory_id"): item
            for item in read(review_path).get("records", [])
            if item.get("trajectory_id")
        })
    current_fingerprints = {}
    for scenario_id, row in rows.items():
        path = (
            MATRIX.parent / "scenarios" / f"scenario_{int(row['ordinal']):03d}"
            / f"scenario_{int(row['ordinal']):03d}.json"
        )
        current_fingerprints[scenario_id] = hashlib.sha256(
            json.dumps(
                read(path), ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
    histories = {scenario_id: [] for scenario_id in rows}
    shard_summaries = {}
    for stack, root in ROLLOUT_ROOTS:
        for shard in range(1, 5):
            progress_path = root / f"shard{shard}" / "progress.json"
            if not progress_path.is_file():
                continue
            progress = read(progress_path)
            shard_summaries[f"{stack}.shard{shard}"] = {
                "status": progress.get("status"),
                "attempt_count": len(progress.get("attempts", [])),
                "accepted_count": progress.get("completed_slot_count", 0),
                "expected_count": progress.get("expected_slot_count", 0),
                "quality_fingerprint": progress.get("quality_fingerprint"),
            }
            for attempt in progress.get("attempts", []):
                scenario_id = attempt.get("scenario_id")
                if scenario_id not in histories:
                    continue
                path = artifact_for(root, shard, int(rows[scenario_id]["ordinal"]), attempt)
                trajectory = read(path) if path else None
                item = {
                    "stack": stack,
                    "shard": shard,
                    "status": attempt.get("status"),
                    "attempt": attempt.get("attempt"),
                    "trajectory_id": attempt.get("trajectory_id") or attempt.get("partial_trajectory_id"),
                    "artifact_path": str(path.relative_to(ROOT)) if path else None,
                    "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path else None,
                    "turn_count": len(trajectory.get("turns", [])) if trajectory else attempt.get("completed_turns_before_error", 0),
                    "ending": trajectory.get("ending") if trajectory else None,
                    "actual_request_counts": trajectory.get("actual_request_counts", {}) if trajectory else {},
                    "machine_precheck": attempt.get("precheck"),
                    "error": attempt.get("error"),
                    "scenario_fingerprint": attempt.get("scenario_fingerprint"),
                    "scenario_version_matches_current": (
                        attempt.get("scenario_fingerprint")
                        == current_fingerprints[scenario_id]
                    ),
                    "framework": framework_audit(trajectory) if trajectory else None,
                }
                histories[scenario_id].append(item)
    candidates = []
    latest_status = Counter()
    requests = Counter()
    for scenario_id, row in sorted(rows.items(), key=lambda pair: pair[1]["ordinal"]):
        history = histories[scenario_id]
        current_history = [item for item in history if item["scenario_version_matches_current"]]
        latest = current_history[-1] if current_history else None
        status = latest["status"] if latest else "pending_generation"
        latest_status[status] += 1
        if latest:
            for key in ("policy", "appraisal", "response", "total"):
                requests[key] += int(latest["actual_request_counts"].get(key, 0))
        candidates.append({
            **row,
            "generation_status": status,
            "latest_attempt": latest,
            "attempt_history": history,
            "current_attempt_history": current_history,
            "machine_precheck": (latest or {}).get("machine_precheck"),
            "model_semantic_review": semantic_reviews.get(
                (latest or {}).get("trajectory_id"), {"decision": "pending"}
            ),
            "human_gate1": "pending",
            "human_gate3": "pending",
            "task_gate4": "not_constructed_before_gate3_selection",
        })
    historically_generated = sum(bool(item["attempt_history"]) for item in candidates)
    generated = sum(bool(item["current_attempt_history"]) for item in candidates)
    payload = {
        "format": REPORT_FORMAT,
        "status": "generated_pending_machine_model_and_human_review" if generated == TARGET_COUNT else "generation_in_progress",
        "configuration_count": len(candidates),
        "generated_scenario_count": generated,
        "historically_generated_scenario_count": historically_generated,
        "pending_scenario_count": len(candidates) - generated,
        "latest_generation_status_counts": dict(sorted(latest_status.items())),
        "actual_request_counts_latest_attempts": dict(requests),
        "model_semantic_review_counts": dict(Counter(
            item["model_semantic_review"].get("decision", "pending")
            for item in candidates
        )),
        "architecture": ["structured_appraisal_llm", "deterministic_python_update", "response_generation_llm"],
        "gate_status": {
            "gate1": f"{TARGET_COUNT}_unsigned_review_packets_ready_human_pending",
            "gate2": "matched_environment_validity_review_pending",
            "gate3": "machine_precheck_incremental_model_and_human_review_pending",
            "gate4": "blocked_until_gate3_selection_and_task_construction",
        },
        "human_review_warning": "Machine/model checks are not human acceptance. Every short, truncated, and failed attempt is retained in attempt_history.",
        "shards": shard_summaries,
        "candidates": candidates,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        f"# SocialFlux {REPORT_LABEL} 实时审核汇总", "",
        f"- 配置：{len(candidates)}", f"- 当前版本已有生成证据：{generated}",
        f"- 历史任一版本已有生成证据：{historically_generated}",
        f"- 最新状态：{dict(sorted(latest_status.items()))}",
        "- 模型/机器检查不是人工验收。", "",
        "| # | Scenario | 轮数 | 最新状态 | 尝试数 | Gate1 | Gate3 | Gate4 |",
        "|---:|---|---:|---|---:|---|---|---|",
    ]
    for item in candidates:
        latest = item["latest_attempt"] or {}
        lines.append(
            f"| {item['ordinal']} | {item['scenario_id']} · {item['title']} | "
            f"{latest.get('turn_count', 0)} | {item['generation_status']} | "
            f"{len(item['attempt_history'])}（当前 {len(item['current_attempt_history'])}） | pending human | pending model/human | not constructed |"
        )
    MARKDOWN.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "configured": len(candidates),
        "generated": generated,
        "historically_generated": historically_generated,
        "pending": len(candidates) - generated,
        "latest_status": dict(latest_status),
        "requests": dict(requests),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
