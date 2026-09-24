#!/usr/bin/env python3
"""Prepare and run batch-local Gate 2 evidence without auto-approving humans."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.quality_gates import audit_environment_gate
from evaluation.timescale_validity import (
    machine_timescale_packet_ready,
    pending_timescale_payload,
    trajectory_timescale_items,
)
from providers.model_routes import ModelRoutes
from scripts.audit_formal_rollout_pool import load_records
from scripts.prepare_human_review_workspace import (
    e1_packet,
    e2_packet,
    pending_e1_e2,
)
from scripts.run_environment_interventions import load_actual_scenarios


ROOT = Path(__file__).resolve().parents[1]

def project_path(path):
    """Resolve CLI paths consistently, independent of the launch directory."""
    path = Path(path).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def stable_sample(items, count):
    return sorted(
        items,
        key=lambda item: hashlib.sha256(
            str(item.get("review_id", "")).encode("utf-8")
        ).hexdigest(),
    )[:count]


def scenario_covered_timescale_payload(trajectories):
    """Select one variable per timescale family for every retained scenario."""
    selected = []
    for trajectory in sorted(
        trajectories,
        key=lambda item: (item.get("scenario_id", ""), item.get("trajectory_id", "")),
    ):
        items = trajectory_timescale_items(trajectory)
        for timescale in ("fast", "medium", "slow", "context_dependent"):
            match = next(
                (
                    item for item in items
                    if item.get("expected_timescale_prior") == timescale
                ),
                None,
            )
            if match is not None:
                selected.append(match)
    if not selected:
        return pending_timescale_payload(trajectories, limit=1)
    base = pending_timescale_payload(
        trajectories,
        limit=sum(len(trajectory_timescale_items(item)) for item in trajectories),
    )
    families = Counter(
        item["expected_timescale_prior"] for item in selected
    )
    base["review_items"] = selected
    base["record"].update({
        "candidate_variable_count": len(selected),
        "timescale_families": dict(sorted(families.items())),
        "non_degenerate": any(
            item.get("changed_turn_count", 0) > 0 for item in selected
        ),
        "coverage_mode": "one_variable_per_timescale_family_per_scenario",
        "covered_scenario_count": len({
            item.get("scenario_id") for item in selected
        }),
    })
    return base


def run(command):
    completed = subprocess.run(command, cwd=ROOT)
    return completed.returncode


def machine_evidence_ready(environment_root):
    requirements = {
        "history_intervention.json": ("matched_checkpoint_count", 10),
        "paraphrase_robustness.json": ("pair_count", 10),
        "local_counterfactual.json": ("checkpoint_count", 10),
        "persona_intervention.json": ("matched_checkpoint_count", 10),
    }
    checks = {}
    ready = True
    for filename, (field, minimum) in requirements.items():
        path = environment_root / filename
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        amount = (payload.get("record") or {}).get(field, 0)
        checks[filename] = {"present": path.exists(), field: amount}
        ready = ready and isinstance(amount, int) and amount >= minimum
    video_path = environment_root / "video_state_consistency.json"
    video = (
        json.loads(video_path.read_text(encoding="utf-8"))
        if video_path.exists() else {}
    )
    video_record = video.get("record", video)
    checks["video_state_consistency.json"] = {
        "present": video_path.exists(),
        "matched_node_count": video_record.get("matched_node_count", 0),
        "generated_video_count": video_record.get("generated_video_count", 0),
        "llm_review_status": video_record.get("llm_review_status"),
        "request_safety_passed": video_record.get("request_safety_passed", False),
    }
    ready = ready and (
        video_record.get("matched_node_count", 0) >= 40
        and video_record.get("generated_video_count", 0) >= 40
        and video_record.get("request_safety_passed") is True
    )

    backbone_path = environment_root / "backbone_sensitivity.json"
    backbone = (
        json.loads(backbone_path.read_text(encoding="utf-8"))
        if backbone_path.exists() else {}
    )
    records = backbone.get("records", [])
    replay_errors = sum(len(item.get("replay_errors", [])) for item in records)
    checks["backbone_sensitivity.json"] = {
        "present": backbone_path.exists(),
        "matched_checkpoint_count": len(records),
        "replay_error_count": replay_errors,
    }
    ready = ready and len(records) >= 10 and replay_errors == 0

    timescale_path = environment_root / "timescale_validity.json"
    timescale = (
        json.loads(timescale_path.read_text(encoding="utf-8"))
        if timescale_path.exists() else {}
    )
    timescale_record = timescale.get("record", timescale)
    checks["timescale_validity.json"] = {
        "present": timescale_path.exists(),
        "candidate_variable_count": timescale_record.get(
            "candidate_variable_count", 0
        ),
        "matched_variable_count": timescale_record.get(
            "matched_variable_count", 0
        ),
        "timescale_families": timescale_record.get("timescale_families", {}),
    }
    ready = ready and machine_timescale_packet_ready(timescale)
    return ready, checks


def non_video_machine_evidence_ready(checks):
    count_fields = {
        "history_intervention.json": "matched_checkpoint_count",
        "paraphrase_robustness.json": "pair_count",
        "local_counterfactual.json": "checkpoint_count",
        "persona_intervention.json": "matched_checkpoint_count",
    }
    if not all(
        checks.get(name, {}).get("present")
        and checks[name].get(field, 0) >= 10
        for name, field in count_fields.items()
    ):
        return False
    backbone = checks.get("backbone_sensitivity.json", {})
    backbone_ready = (
        backbone.get("present")
        and backbone.get("matched_checkpoint_count", 0) >= 10
        and backbone.get("replay_error_count", 1) == 0
    )
    timescale = checks.get("timescale_validity.json", {})
    timescale_ready = machine_timescale_packet_ready({"record": timescale})
    return backbone_ready and timescale_ready


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument("--scenario-root", type=Path, required=True)
    parser.add_argument("--rollout-root", type=Path, required=True)
    parser.add_argument("--rollout-config", type=Path, required=True)
    parser.add_argument("--scenario-limit", type=int, default=10)
    parser.add_argument(
        "--all-scenarios",
        action="store_true",
        help=(
            "cover every trajectory supplied in rollout-root; E1 keeps up to "
            "two transitions per scenario, E2 one trajectory per scenario, "
            "and E9 one variable per timescale family per scenario"
        ),
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help=(
            "materialize deterministic E1/E2 human-review packets and a pending "
            "manifest without constructing providers or making API requests"
        ),
    )
    parser.add_argument(
        "--allow-pending-video",
        action="store_true",
        help=(
            "return success once E3-E7 machine experiments are complete even "
            "when E8 is still awaiting the separately configured video API"
        ),
    )
    parser.add_argument(
        "--gpt-routes",
        type=Path,
        default=Path("configs/gpt50_experiment/model_routes.astra.json"),
    )
    parser.add_argument(
        "--claude-routes",
        type=Path,
        default=Path("configs/claude150_v1/model_routes.chat.pool2.json"),
    )
    args = parser.parse_args(argv)
    batch = project_path(args.batch_root)
    scenario_root = project_path(args.scenario_root)
    rollout_root = project_path(args.rollout_root)
    rollout_config = project_path(args.rollout_config)
    gpt_routes = project_path(args.gpt_routes)
    claude_routes = project_path(args.claude_routes)
    environment_root = batch / "gate2"
    environment_root.mkdir(parents=True, exist_ok=True)

    scenarios_list = load_actual_scenarios(scenario_root)
    scenarios = {item["scenario_id"]: item for item in scenarios_list}
    trajectories = load_records(rollout_root)
    if not trajectories:
        raise ValueError("Gate 2 requires at least one completed rollout")

    e1_candidates = e1_packet(trajectories, scenarios)
    e2_candidates = e2_packet(trajectories)
    e1 = (
        e1_candidates
        if args.all_scenarios
        else stable_sample(e1_candidates, 40)
    )
    e2 = (
        e2_candidates
        if args.all_scenarios
        else stable_sample(e2_candidates, 20)
    )
    pending_e1_e2(environment_root, e1, e2)
    timescale_path = environment_root / "timescale_validity.json"
    existing_timescale = (
        json.loads(timescale_path.read_text(encoding="utf-8"))
        if timescale_path.exists() else {}
    )
    timescale_payload = existing_timescale
    if timescale_payload.get("record", timescale_payload).get(
        "human_attestation"
    ) is not True:
        timescale_payload = (
            scenario_covered_timescale_payload(trajectories)
            if args.all_scenarios
            else pending_timescale_payload(trajectories, limit=40)
        )
        atomic(timescale_path, timescale_payload)
    e9_review_items = int(
        timescale_payload.get("record", timescale_payload).get(
            "candidate_variable_count", len(timescale_payload.get("review_items", []))
        ) or 0
    )

    if args.prepare_only:
        machine_ready, machine_checks = machine_evidence_ready(environment_root)
        manifest = {
            "format": "socialflux_batch_gate2_manifest_v1",
            "updated_at_utc": now(),
            "batch_root": str(batch),
            "scenario_count": len(scenarios_list),
            "rollout_count": len(trajectories),
            "mode": "prepare_only",
            "coverage_mode": (
                "all_scenarios" if args.all_scenarios else "stable_sample"
            ),
            "ordering_policy": (
                "generation_continues_while_human_gate2_is_pending"
            ),
            "e1_review_items": len(e1),
            "e2_review_items": len(e2),
            "e9_review_items": e9_review_items,
            "automatic_returncodes": {
                "e3_e4_e5": None,
                "e6": None,
                "e9": 0,
            },
            "machine_evidence_ready": machine_ready,
            "machine_checks": machine_checks,
            "gate2": {
                "status": "pending_machine_and_human_evidence",
                "human_status": "pending",
            },
            "network_requests_performed": 0,
        }
        atomic(environment_root / "manifest.json", manifest)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return

    gpt = ModelRoutes.load(gpt_routes).provider_config("appraisal")
    claude = ModelRoutes.load(claude_routes).provider_config("appraisal")
    backbone_config = environment_root / "backbone_config.runtime.json"
    atomic(backbone_config, {
        "format": "socialflux_backbone_sensitivity_config_v1",
        "backbones": [
            {
                "model_family": "openai",
                "provider": gpt,
                "sampling": {"temperature": 0, "seed": 73101},
            },
            {
                "model_family": "claude",
                "provider": claude,
                "sampling": {"temperature": 0, "seed": 73102},
            },
        ],
    })

    _, existing_checks = machine_evidence_ready(environment_root)
    existing_non_video_ready = non_video_machine_evidence_ready(existing_checks)
    intervention_command = [
        sys.executable,
        str(ROOT / "scripts" / "run_environment_interventions.py"),
        "--raw-root", str(rollout_root),
        "--scenario-root", str(scenario_root),
        "--rollout-config", str(rollout_config),
        "--output-root", str(environment_root),
        "--history-evidence", str(environment_root / "history_dependence.json"),
        "--existing-intervention-root", str(environment_root / "existing"),
        "--resume",
    ]
    backbone_command = [
        sys.executable,
        str(ROOT / "scripts" / "run_backbone_sensitivity.py"),
        "--raw-root", str(rollout_root),
        "--scenario-root", str(scenario_root),
        "--config", str(backbone_config),
        "--output", str(environment_root / "backbone_sensitivity.json"),
    ]
    if not args.all_scenarios:
        intervention_command.extend(
            ["--scenario-limit", str(args.scenario_limit)]
        )
        backbone_command.extend(
            ["--scenario-limit", str(args.scenario_limit)]
        )
    intervention_rc = (
        0 if existing_non_video_ready else run(intervention_command)
    )
    backbone_rc = (
        0 if existing_non_video_ready else run(backbone_command)
    )

    machine_ready, machine_checks = machine_evidence_ready(environment_root)
    non_video_ready = non_video_machine_evidence_ready(machine_checks)
    gate = audit_environment_gate(scenarios_list, environment_root)
    manifest = {
        "format": "socialflux_batch_gate2_manifest_v1",
        "updated_at_utc": now(),
        "batch_root": str(batch),
        "scenario_count": len(scenarios_list),
        "rollout_count": len(trajectories),
        "mode": "full_machine_evidence",
        "coverage_mode": (
            "all_scenarios" if args.all_scenarios else "stable_sample"
        ),
        "ordering_policy": "generation_continues_while_human_gate2_is_pending",
        "e1_review_items": len(e1),
        "e2_review_items": len(e2),
        "e9_review_items": e9_review_items,
        "automatic_returncodes": {
            "e3_e4_e5": intervention_rc,
            "e6": backbone_rc,
            "e9": 0,
        },
        "machine_evidence_ready": machine_ready,
        "non_video_machine_evidence_ready": non_video_ready,
        "execution_status": (
            "machine_evidence_ready" if machine_ready
            else "awaiting_video_api" if non_video_ready
            else "environment_experiments_incomplete"
        ),
        "machine_checks": machine_checks,
        "gate2": gate,
        "human_review_required": True,
        "video_api_requests_performed": 0,
    }
    atomic(environment_root / "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if not machine_ready and not (args.allow_pending_video and non_video_ready):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
