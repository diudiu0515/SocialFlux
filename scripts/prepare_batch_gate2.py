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
from evaluation.timescale_validity import machine_timescale_packet_ready, pending_timescale_payload
from providers.model_routes import ModelRoutes
from rollout.configuration import load_rollout_config
from scripts.audit_formal_rollout_pool import load_records
from scripts.prepare_human_review_workspace import (
    e1_packet,
    e2_packet,
    pending_e1_e2,
)
from scripts.run_environment_interventions import load_actual_scenarios
from shared.artifacts import atomic_json as atomic


ROOT = Path(__file__).resolve().parents[1]

def project_path(path):
    """Resolve CLI paths consistently, independent of the launch directory."""
    path = Path(path).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def now():
    return datetime.now(timezone.utc).isoformat()


def evidence_reference(path):
    path = Path(path)
    payload = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def stable_sample(items, count):
    return sorted(
        items,
        key=lambda item: hashlib.sha256(
            str(item.get("review_id", "")).encode("utf-8")
        ).hexdigest(),
    )[:count]


def cohort_summary(trajectories):
    source_statuses = Counter(
        item.get("gate2_audit_input", {}).get(
            "source_status", "accepted_or_unspecified"
        )
        for item in trajectories
    )
    turn_counts = Counter(len(item.get("turns", [])) for item in trajectories)
    exact_twenty = sum(len(item.get("turns", [])) == 20 for item in trajectories)
    natural_main_window = sum(
        10 <= len(item.get("turns", [])) <= 20
        and (item.get("ending") or {}).get("reason") == "natural_completion"
        and (item.get("ending") or {}).get("turn_id")
        == len(item.get("turns", []))
        for item in trajectories
    )
    accepted = sum(
        item.get("gate2_audit_input", {}).get(
            "source_status", "accepted"
        ) == "accepted"
        for item in trajectories
    )
    return {
        "source_status_counts": dict(sorted(source_statuses.items())),
        "turn_count_distribution": {
            str(key): value for key, value in sorted(turn_counts.items())
        },
        "accepted_under_batch_contract": accepted,
        "exact_20_turn_count": exact_twenty,
        "exact_20_turn_fraction": round(
            exact_twenty / len(trajectories), 4
        ) if trajectories else 0.0,
        "natural_10_to_20_turn_count": natural_main_window,
        "natural_10_to_20_turn_fraction": round(
            natural_main_window / len(trajectories), 4
        ) if trajectories else 0.0,
        "formal_natural_10_to_20_ready": (
            bool(trajectories) and natural_main_window == len(trajectories)
        ),
    }


def run(command):
    completed = subprocess.run(command, cwd=ROOT)
    return completed.returncode


def machine_evidence_ready(environment_root, expected_trajectories=None):
    expected_scenario_ids = None
    expected_trajectory_ids = None
    if expected_trajectories is not None:
        expected_scenario_ids = {
            item.get("scenario_id") for item in expected_trajectories
        }
        expected_trajectory_ids = {
            item.get("trajectory_id") for item in expected_trajectories
        }
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
        record = payload.get("record") or {}
        provenance = payload.get("provenance") or {}
        input_cohort = provenance.get("input_cohort") or {}
        cohort_matches = True
        if expected_scenario_ids is not None:
            cohort_matches = (
                provenance.get("experiment_version")
                == "gate2_interventions_v2"
                and set(input_cohort.get("scenario_ids", []))
                == expected_scenario_ids
                and set(input_cohort.get("trajectory_ids", []))
                == expected_trajectory_ids
                and {
                    item.get("scenario_id")
                    for item in payload.get("records", [])
                } == expected_scenario_ids
                and {
                    item.get("source_trajectory_id")
                    for item in payload.get("records", [])
                } == expected_trajectory_ids
            )
        amount = record.get(field, 0)
        machine_screen_passed = record.get("machine_screen_passed") is True
        checks[filename] = {
            "present": path.exists(),
            field: amount,
            "machine_coverage_ready": (
                isinstance(amount, int) and amount >= minimum
            ),
            "machine_screen_passed": machine_screen_passed,
            "cohort_matches": cohort_matches,
        }
        ready = (
            ready
            and isinstance(amount, int)
            and amount >= minimum
            and machine_screen_passed
            and cohort_matches
        )
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
    backbone_record = backbone.get("record", {})
    backbone_cohort_matches = True
    if expected_scenario_ids is not None:
        backbone_cohort_matches = (
            backbone.get("experiment_version")
            == "gate2_backbone_sensitivity_v2"
            and set(backbone.get("input_scenario_ids", []))
            == expected_scenario_ids
            and set(backbone.get("input_trajectory_ids", []))
            == expected_trajectory_ids
            and {item.get("scenario_id") for item in records}
            == expected_scenario_ids
            and {item.get("source_trajectory_id") for item in records}
            == expected_trajectory_ids
        )
    replay_errors = sum(len(item.get("replay_errors", [])) for item in records)
    checks["backbone_sensitivity.json"] = {
        "present": backbone_path.exists(),
        "matched_checkpoint_count": len(records),
        "replay_error_count": replay_errors,
        "successful_matched_checkpoint_count": backbone_record.get(
            "successful_matched_checkpoint_count", 0
        ),
        "machine_screen_passed": backbone_record.get("passed") is True,
        "cohort_matches": backbone_cohort_matches,
    }
    ready = (
        ready and len(records) >= 10 and replay_errors == 0
        and backbone_record.get("passed") is True
        and backbone_cohort_matches
    )

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
        and checks[name].get("machine_screen_passed") is True
        and checks[name].get("cohort_matches", True) is True
        for name, field in count_fields.items()
    ):
        return False
    backbone = checks.get("backbone_sensitivity.json", {})
    backbone_ready = (
        backbone.get("present")
        and backbone.get("matched_checkpoint_count", 0) >= 10
        and backbone.get("replay_error_count", 1) == 0
        and backbone.get("machine_screen_passed") is True
        and backbone.get("cohort_matches", True) is True
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
            "run E3-E7 over every supplied trajectory; formal E1/E2/E9 human "
            "packets still obey their stable sample bounds"
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
    parser.add_argument(
        "--state-transition-audit",
        type=Path,
        help="offline state-transition audit to bind into the manifest",
    )
    parser.add_argument(
        "--state-transition-review",
        type=Path,
        help="pending human state-ontology packet to bind into the manifest",
    )
    args = parser.parse_args(argv)
    batch = project_path(args.batch_root)
    scenario_root = project_path(args.scenario_root)
    rollout_root = project_path(args.rollout_root)
    rollout_config = project_path(args.rollout_config)
    gpt_routes = project_path(args.gpt_routes)
    claude_routes = project_path(args.claude_routes)
    state_transition_audit = (
        project_path(args.state_transition_audit)
        if args.state_transition_audit else None
    )
    state_transition_review = (
        project_path(args.state_transition_review)
        if args.state_transition_review else None
    )
    environment_root = batch / "gate2"
    environment_root.mkdir(parents=True, exist_ok=True)

    scenarios_list = load_actual_scenarios(scenario_root)
    scenarios = {item["scenario_id"]: item for item in scenarios_list}
    trajectories = load_records(rollout_root)
    if not trajectories:
        raise ValueError("Gate 2 requires at least one completed rollout")
    cohort = cohort_summary(trajectories)

    e1_candidates = e1_packet(trajectories, scenarios)
    e2_candidates = e2_packet(trajectories)
    # Formal E1/E2 bounds apply even when the machine experiments cover every
    # supplied scenario. Sampling is stable and independent of pass outcome.
    e1 = stable_sample(e1_candidates, 40)
    e2 = stable_sample(e2_candidates, 20)
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
        timescale_payload = pending_timescale_payload(trajectories, limit=40)
        atomic(timescale_path, timescale_payload)
    e9_review_items = int(
        timescale_payload.get("record", timescale_payload).get(
            "candidate_variable_count", len(timescale_payload.get("review_items", []))
        ) or 0
    )
    config_environment = load_rollout_config(rollout_config)["environment"]
    state_transition_repair = {
        "status": "pending_human_and_post_fix_rerun",
        "pre_fix_trajectory_evidence_only": True,
        "appraisal_prompt_id": config_environment.get(
            "appraisal_prompt_id", "environment_appraisal_v11"
        ),
        "state_calibration_profile": config_environment.get(
            "state_calibration_profile", "sparse_v1"
        ),
        "ordinary_state_change_budget": 1,
        "thresholds_relaxed": False,
    }
    if state_transition_audit is not None:
        if not state_transition_audit.is_file():
            raise ValueError(
                f"state transition audit does not exist: {state_transition_audit}"
            )
        state_transition_repair["offline_audit"] = evidence_reference(
            state_transition_audit
        )
    if state_transition_review is not None:
        if not state_transition_review.is_file():
            raise ValueError(
                f"state transition review does not exist: {state_transition_review}"
            )
        review_payload = json.loads(
            state_transition_review.read_text(encoding="utf-8")
        )
        state_transition_repair["human_review"] = {
            **evidence_reference(state_transition_review),
            "review_status": review_payload.get(
                "review_status", "pending_human"
            ),
            "human_attestation": (
                review_payload.get("human_attestation") is True
            ),
        }

    if args.prepare_only:
        machine_ready, machine_checks = machine_evidence_ready(
            environment_root, trajectories
        )
        machine_ready = (
            machine_ready and cohort["formal_natural_10_to_20_ready"]
        )
        manifest = {
            "format": "socialflux_batch_gate2_manifest_v1",
            "updated_at_utc": now(),
            "batch_root": str(batch),
            "scenario_count": len(scenarios_list),
            "rollout_count": len(trajectories),
            "cohort": cohort,
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
            "state_transition_repair": state_transition_repair,
            "formal_gate2_audit": audit_environment_gate(
                scenarios_list, environment_root
            ),
            "gate2": {
                "status": (
                    "pending_machine_and_human_evidence"
                    if cohort["formal_natural_10_to_20_ready"]
                    else "blocked_natural_10_to_20_contract"
                ),
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
        "appraisal_prompt_id": config_environment.get(
            "appraisal_prompt_id", "environment_appraisal_v11"
        ),
        "state_calibration_profile": config_environment.get(
            "state_calibration_profile", "sparse_v1"
        ),
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

    _, existing_checks = machine_evidence_ready(environment_root, trajectories)
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
        "--resume",
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

    machine_ready, machine_checks = machine_evidence_ready(
        environment_root, trajectories
    )
    non_video_ready = non_video_machine_evidence_ready(machine_checks)
    formal_horizon_ready = cohort["formal_natural_10_to_20_ready"]
    machine_ready = machine_ready and formal_horizon_ready
    non_video_ready = non_video_ready and formal_horizon_ready
    gate = audit_environment_gate(scenarios_list, environment_root)
    manifest = {
        "format": "socialflux_batch_gate2_manifest_v1",
        "updated_at_utc": now(),
        "batch_root": str(batch),
        "scenario_count": len(scenarios_list),
        "rollout_count": len(trajectories),
        "cohort": cohort,
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
            "blocked_natural_10_to_20_contract" if not formal_horizon_ready
            else "machine_evidence_ready" if machine_ready
            else "awaiting_video_api" if non_video_ready
            else "environment_experiments_incomplete"
        ),
        "machine_checks": machine_checks,
        "state_transition_repair": state_transition_repair,
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
