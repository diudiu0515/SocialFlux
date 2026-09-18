#!/usr/bin/env python3
"""Build deterministic R3 naturalness packets and R4 distribution evidence."""

import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.instance_quality import audit_trajectory
from evaluation.rollout_gate import audit_rollout
from evaluation.state_distribution import (
    compare_state_distributions,
    summarize_state_distribution,
)
from scripts.audit_formal_rollout_pool import load_records


_CONSTRAINT = re.compile(r"(?:如果|若|只要|除非|否则|必须|务必|前提是)")
_ESCALATION = re.compile(
    r"(?:调查|处分|诉讼|冻结|听证|委员会|法务|合规|惩罚|永久|自动失效)"
)


def _candidate_turns(trajectory, pattern):
    return [
        {"turn_id": turn["turn_id"], "environment_response": turn["environment_response"]}
        for turn in trajectory.get("turns", [])
        if pattern.search(turn.get("environment_response", ""))
    ]


def _review_record(trajectory):
    structural = audit_trajectory(trajectory)
    gate = audit_rollout(trajectory)
    return {
        "scenario_id": trajectory["scenario_id"],
        "trajectory_id": trajectory["trajectory_id"],
        "turn_count": len(trajectory.get("turns", [])),
        "machine_precheck_passed": not gate["hard_reject_reasons"],
        "hard_reject_reasons": gate["hard_reject_reasons"],
        "structural_diagnostics": structural["diagnostics"],
        "constraint_language_candidates": _candidate_turns(trajectory, _CONSTRAINT),
        "institutional_escalation_candidates": _candidate_turns(trajectory, _ESCALATION),
        "human_review": {
            "status": "pending_human",
            "reviewer": "",
            "addresses_current_turn": None,
            "avoids_repetitive_bargaining": None,
            "avoids_continuous_new_constraints": None,
            "avoids_artificial_escalation": None,
            "commitments_remain_coherent": None,
            "overall_social_naturalness": None,
            "notes": "",
        },
        "observable_dialogue": [
            {
                "turn_id": turn["turn_id"],
                "evaluated_agent": turn["policy_action"]["text"],
                "environment_agent": turn["environment_response"],
            }
            for turn in trajectory.get("turns", [])
        ],
    }


def _rejected_record(path):
    trajectory = json.loads(path.read_text(encoding="utf-8"))
    structural = audit_trajectory(trajectory)
    return {
        "scenario_id": trajectory.get("scenario_id"),
        "trajectory_id": trajectory.get("trajectory_id"),
        "source_file": str(path),
        "failed_checks": [
            key for key, passed in structural["checks"].items() if not passed
        ],
        "structural_diagnostics": structural["diagnostics"],
        "observable_dialogue": [
            {
                "turn_id": turn.get("turn_id"),
                "evaluated_agent": turn.get("policy_action", {}).get("text", ""),
                "environment_agent": turn.get("environment_response", ""),
            }
            for turn in trajectory.get("turns", [])
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollout-root", type=Path, required=True)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    trajectories = load_records(args.rollout_root)
    baseline = summarize_state_distribution(load_records(args.baseline_root))
    current = summarize_state_distribution(trajectories)
    records = [_review_record(item) for item in trajectories]
    rejected_records = [
        _rejected_record(path)
        for path in sorted(args.rollout_root.glob("scenario_*/rejected/*.json"))
    ]
    progress_path = args.rollout_root / "progress.json"
    progress = (
        json.loads(progress_path.read_text(encoding="utf-8"))
        if progress_path.exists() else {}
    )
    failed_attempts = [
        {
            "scenario_id": item.get("scenario_id"),
            "attempt": item.get("attempt"),
            "status": item.get("status"),
            "error": item.get("error", ""),
        }
        for item in progress.get("attempts", [])
        if item.get("status") in {"generation_error", "revalidation_rejected"}
    ]
    payload = {
        "format": "socialflux_environment_stabilization_regression_v1",
        "record": {
            "trajectory_count": len(records),
            "machine_precheck_passed_count": sum(
                item["machine_precheck_passed"] for item in records
            ),
            "rejected_trajectory_count": len(rejected_records),
            "failed_attempt_count": len(failed_attempts),
            "human_attestation": False,
            "review_status": "pending_human",
            "passed": False,
        },
        "state_distribution": compare_state_distributions(baseline, current),
        "records": records,
        "rejected_records": rejected_records,
        "failed_attempts": failed_attempts,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(json.dumps({
        "output": str(args.output),
        **payload["record"],
        "state_distribution_change": payload["state_distribution"]["change"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
