#!/usr/bin/env python3
"""Apply gate.md quality/diversity/provenance constraints to a raw pool."""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.rollout_gate import (
    audit_pool_contract,
    audit_rollout,
    content_sha256,
    select_diverse_trajectories,
)
from evaluation.review_registry import load_review_registry
from evaluation.quality_gates import audit_environment_gate, audit_scenario_gate
from rollout.manifest import write_manifest
from scripts.run_pipeline import load_scenario_records


def load_records(root):
    trajectories = []
    root = Path(root)
    nested = any((path / "rollouts").is_dir() for path in root.glob("scenario_*"))
    rollout_dirs = sorted(
        path / "rollouts" if nested else path
        for path in root.glob("scenario_*")
        if (path / "rollouts" if nested else path).is_dir()
    )
    paths = []
    for rollout_dir in rollout_dirs:
        manifest_path = rollout_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            paths.extend(
                rollout_dir / f"{trajectory_id}.json"
                for trajectory_id in manifest.get("trajectory_ids", [])
            )
        else:
            paths.extend(
                path for path in rollout_dir.glob("*.json")
                if path.name not in {"manifest.json", "quality_report.json"}
            )
    seen = set()
    for path in paths:
        if not path.exists():
            raise ValueError(f"rollout manifest references missing trajectory {path}")
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("trajectory_id") and value.get("turns"):
            if value["trajectory_id"] in seen:
                raise ValueError(f"duplicate trajectory ID {value['trajectory_id']}")
            trajectories.append(value)
            seen.add(value["trajectory_id"])
    return trajectories


def load_index(path, key):
    if path is None or not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    items = value if isinstance(value, list) else value.get("records", [])
    return {item[key]: item for item in items}


def validate_formal_judgment_bundle(path):
    if path is None or not path.exists():
        return False, "formal pool requires a completed primary/secondary judge merge"
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("format") != "socialflux_dual_judge_merge_v1":
        return False, "formal judgments must be socialflux_dual_judge_merge_v1"
    if value.get("complete") is not True:
        return False, "formal dual-judge bundle is incomplete"
    primary = value.get("primary_judge", {})
    secondary = value.get("secondary_judge", {})
    if (
        not primary.get("model")
        or not secondary.get("model")
        or primary.get("model") == secondary.get("model")
        or primary.get("model_family") == secondary.get("model_family")
    ):
        return False, "formal judges must use different models and model families"
    return True, "completed cross-family primary/secondary protocol"


def assert_formal_scenarios(scenario_records, review_registry):
    if review_registry is None:
        raise ValueError(
            "formal pool blocked: --review-registry with human-signed records is required"
        )
    failures = []
    for scenario_path, scenario in scenario_records:
        result = audit_scenario_gate(scenario, scenario_path, review_registry)
        if not result["passed"]:
            failed = [
                key for key, value in result["checks"].items()
                if value["status"] != "pass"
            ]
            failures.append(f"{scenario['scenario_id']}: {','.join(failed)}")
    if failures:
        raise ValueError(
            "formal pool blocked: scenario quality/S0-D0 lack valid bound human approval: "
            + "; ".join(failures)
        )


def materialize_selected(root, selected, audits, report):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    by_id = {item["trajectory_id"]: item for item in audits}
    for scenario_id, trajectories in selected.items():
        destination = root / scenario_id.replace("IA_PIPE_", "scenario_").lower()
        destination.mkdir(parents=True, exist_ok=True)
        for old in destination.glob("*.json"):
            old.unlink()
        for trajectory in trajectories:
            path = destination / f"{trajectory['trajectory_id']}.json"
            path.write_text(
                json.dumps(trajectory, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        write_manifest(
            destination / "manifest.json",
            trajectories,
            {
                "origin": "free_form_model_interaction",
                "pool_stage": "formal_selected",
                "selection_report_sha256": content_sha256(report),
                "quality_audits": [
                    by_id[item["trajectory_id"]] for item in trajectories
                ],
            },
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--judgments", type=Path)
    parser.add_argument("--history-evidence", type=Path)
    parser.add_argument(
        "--environment-evidence",
        type=Path,
        help="Gate 2 E1-E6 evidence directory (required for formal)",
    )
    parser.add_argument(
        "--review-registry",
        type=Path,
        help="human-signed registry bound to exact scenario files (required for formal)",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--selected-root", type=Path)
    parser.add_argument("--stage", choices=("development", "formal"), default="development")
    parser.add_argument("--minimum", type=int, default=4)
    parser.add_argument("--maximum", type=int, default=6)
    args = parser.parse_args()

    scenario_records = load_scenario_records("configs/scenarios")
    scenarios = [scenario for _, scenario in scenario_records]
    if args.stage == "formal":
        registry = (
            load_review_registry(args.review_registry)
            if args.review_registry is not None
            else None
        )
        assert_formal_scenarios(scenario_records, registry)
        environment_gate = audit_environment_gate(scenarios, args.environment_evidence)
        if not environment_gate["passed"]:
            raise ValueError("formal pool blocked: Gate 2 environment validity has not passed")
    else:
        environment_gate = None
    judge_protocol_passed, judge_protocol_reason = (
        validate_formal_judgment_bundle(args.judgments)
        if args.stage == "formal"
        else (True, "development stage does not require dual judges")
    )
    trajectories = load_records(args.raw_root)
    judgments = load_index(args.judgments, "trajectory_id")
    history = load_index(args.history_evidence, "trajectory_id")
    audits = [
        audit_rollout(
            trajectory,
            judgments.get(trajectory["trajectory_id"]),
            history.get(trajectory["trajectory_id"]),
        )
        for trajectory in trajectories
    ]
    grouped = defaultdict(list)
    for trajectory in trajectories:
        grouped[trajectory["scenario_id"]].append(trajectory)
    selections = {
        scenario_id: select_diverse_trajectories(
            items,
            [audit for audit in audits if audit["scenario_id"] == scenario_id],
            args.minimum,
            args.maximum,
        )
        for scenario_id, items in sorted(grouped.items())
    }
    selected = {
        scenario_id: result["selected"]
        for scenario_id, result in selections.items()
    }
    contract = audit_pool_contract(trajectories, selected)
    report = {
        "format": "socialflux_formal_rollout_gate_v1",
        "stage": args.stage,
        "raw_trajectory_count": len(trajectories),
        "passed_quality_count": sum(item["passed"] for item in audits),
        "selected_trajectory_count": sum(len(items) for items in selected.values()),
        "pool_contract": contract,
        "environment_gate": environment_gate,
        "judge_protocol": {
            "passed": judge_protocol_passed,
            "reason": judge_protocol_reason,
        },
        "all_scenarios_selection_passed": (
            len(selections) == len(scenarios)
            and all(item["passed"] for item in selections.values())
        ),
        "research_ready": (
            args.stage == "formal"
            and judge_protocol_passed
            and environment_gate is not None
            and environment_gate["passed"]
            and contract["passed"]
            and len(selections) == len(scenarios)
            and all(item["passed"] for item in selections.values())
        ),
        "selections": {
            key: {name: value for name, value in result.items() if name != "selected"}
            for key, result in selections.items()
        },
        "trajectory_audits": audits,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.selected_root and report["research_ready"]:
        materialize_selected(args.selected_root, selected, audits, report)
    print(json.dumps({
        "output": str(args.output),
        "stage": args.stage,
        "raw": len(trajectories),
        "quality_passed": report["passed_quality_count"],
        "selected": report["selected_trajectory_count"],
        "pool_contract_passed": contract["passed"],
        "research_ready": report["research_ready"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
