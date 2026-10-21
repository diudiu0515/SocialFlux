#!/usr/bin/env python3
"""Generate resumable Gate 2 E3/E4/E5/E7 experiments on matched checkpoints."""

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_VERSION = "gate2_interventions_v2"

from environment.factory import ModelEnvironmentFactory
from evaluation.paraphrase_equivalence import (
    strict_paraphrase_constraints,
    strict_paraphrase_precheck,
)
from evaluation.transition_metrics import compare_transition_outputs
from offline.candidate_generation import ModelCandidateGenerator
from prompts.loader import render_prompt
from providers.factory import build_provider, public_provider_config
from providers.model_routes import ModelRoutes
from providers.structured import complete_json
from providers.text import text_similarity
from rollout.configuration import load_rollout_config
from scripts.audit_formal_rollout_pool import load_records
from scripts.run_history_dependence import (
    _interpret_without_response,
    _interpretation_comparison,
    critical_turn,
)
from scenario_design.catalog import discover_scenario_paths


def load_actual_scenarios(root):
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in discover_scenario_paths(Path(root))
    ]


def select_one_per_scenario(trajectories, scenario_limit=None):
    """Select the deepest deterministic development trajectory per scenario."""
    grouped = {}
    for trajectory in trajectories:
        grouped.setdefault(trajectory["scenario_id"], []).append(trajectory)
    selected = [
        sorted(items, key=lambda item: (-len(item.get("turns", [])), item["trajectory_id"]))[0]
        for _, items in sorted(grouped.items())
        if any(item.get("turns") for item in items)
    ]
    return selected[:scenario_limit] if scenario_limit else selected


def select_intervention_checkpoint(trajectory):
    """Use a fixed 70%-horizon checkpoint, not a terminal success-biased one."""
    turns = trajectory.get("turns", [])
    if not turns:
        raise ValueError("intervention trajectory has no turns")
    target_turn = max(1, min(len(turns), (7 * len(turns) + 9) // 10))
    return turns[target_turn - 1]


def _paraphrase(provider, sampling, trajectory, checkpoint):
    original = checkpoint["policy_action"]["text"]
    payload = {
        "scenario_id": trajectory["scenario_id"],
        "background": checkpoint["observation"].get("background", ""),
        "speaker_role": checkpoint["observation"].get("role", {}),
        "recent_history": checkpoint["observation"].get("history", [])[-4:],
        "latest_action": original,
        "strict_surface_constraints": strict_paraphrase_constraints(original),
    }

    def validate(value):
        if set(value) != {"paraphrase"}:
            raise ValueError("paraphrase output must contain exactly paraphrase")
        text = str(value["paraphrase"]).strip()
        similarity = text_similarity(original, text)
        if text == original:
            raise ValueError("paraphrase must be distinct from the source action")
        if similarity < 0.1 or similarity > 0.99:
            raise ValueError("paraphrase wording distance is outside the probe range")
        precheck = strict_paraphrase_precheck(original, text)
        if not precheck["passed"]:
            raise ValueError(f"strict paraphrase precheck failed: {precheck['reasons']}")
        return text

    prompt = render_prompt("environment_paraphrase_probe_v1", payload)
    return complete_json(
        provider,
        [{"role": "user", "content": prompt}],
        sampling,
        validate,
        context="environment paraphrase probe",
        max_attempts=5,
    )


def _replay(factory, snapshot, action):
    environment = factory()
    environment.restore(deepcopy(snapshot))
    return _interpret_without_response(environment, action)


def _e3(factory, trajectory, checkpoint):
    snapshot = deepcopy(checkpoint["environment_snapshot_before"])
    checkpoint_index = trajectory["turns"].index(checkpoint)
    critical = critical_turn(
        trajectory,
        checkpoint_index,
        checkpoint.get("memory_view", {}).get("relevant_turn_ids", []),
    )
    removed = deepcopy(snapshot)
    removed["history"] = [
        item for item in snapshot.get("history", [])
        if str(item.get("turn_id")) != str(critical).lstrip("t")
    ]
    action = checkpoint["policy_action"]
    full = _replay(factory, snapshot, action)
    without = _replay(factory, removed, action)
    comparison = _interpretation_comparison(full, without)
    relevant_turn_ids = [
        str(item) if str(item).startswith("t") else f"t{item}"
        for item in checkpoint.get("memory_view", {}).get(
            "relevant_turn_ids", []
        )
    ]
    return {
        "critical_event_turn_id": critical,
        "relevant_memory_turn_ids": relevant_turn_ids,
        "critical_event_in_relevant_memory": critical in relevant_turn_ids,
        "action": action["text"],
        "full_history": snapshot.get("history", []),
        "critical_removed_history": removed.get("history", []),
        "full_output": full,
        "critical_removed_output": without,
        "comparison": comparison,
        "automatic_screen_passed": comparison["change_score"] >= 0.15,
    }


def _existing_e3(history_record, checkpoint):
    comparison = history_record["environment_interpretation"]["full_vs_critical_removed"]
    return {
        "critical_event_turn_id": (history_record.get("critical_event_turn_ids") or [None])[0],
        "action": checkpoint["policy_action"]["text"],
        "comparison": comparison,
        "automatic_screen_passed": comparison["change_score"] >= 0.15,
        "reused_evidence": {
            "experiment": "history_dependence_matched_environment_replay",
            "trajectory_id": history_record["trajectory_id"],
            "checkpoint_turn_id": history_record["checkpoint_turn_id"],
            "score": history_record.get("score"),
            "passed": history_record.get("passed"),
        },
    }


def _persona_variant(provider, sampling, scenario, trajectory, checkpoint):
    original = scenario["environment_agent"]["persona"]
    payload = {
        "scenario_id": scenario["scenario_id"],
        "background": checkpoint["observation"].get("background", ""),
        "current_public_history": checkpoint["observation"].get("history", [])[-6:],
        "latest_action": checkpoint["policy_action"]["text"],
        "original_persona": original,
        "fixed_fields": ["name", "role", "core_values", "boundaries"],
        "fields_to_contrast": [
            "temperament", "communication_style",
            "decision_style", "conflict_style",
        ],
    }

    def validate(value):
        if set(value) != {"persona"} or not isinstance(value["persona"], dict):
            raise ValueError("persona intervention must contain exactly persona")
        persona = value["persona"]
        if set(persona) != set(original):
            raise ValueError("persona intervention must preserve persona keys")
        for key in ("name", "role", "core_values", "boundaries"):
            if persona[key] != original[key]:
                raise ValueError(f"persona intervention changed fixed field {key}")
        changed = 0
        for key in (
            "temperament", "communication_style",
            "decision_style", "conflict_style",
        ):
            if type(persona[key]) is not type(original[key]):
                raise ValueError(f"persona intervention changed type for {key}")
            if persona[key] != original[key]:
                changed += 1
        if changed < 3:
            raise ValueError("persona intervention must contrast at least three style fields")
        return persona

    prompt = render_prompt("environment_persona_intervention_v1", payload)
    return complete_json(
        provider,
        [{"role": "user", "content": prompt}],
        sampling,
        validate,
        context=f"persona intervention {trajectory['scenario_id']}",
        max_attempts=5,
    )


def _e7(config, construction_provider, construction_sampling, scenario, trajectory, checkpoint):
    snapshot = deepcopy(checkpoint["environment_snapshot_before"])
    action = checkpoint["policy_action"]
    alternate_persona = _persona_variant(
        construction_provider, construction_sampling, scenario, trajectory, checkpoint
    )
    counterfactual_scenario = deepcopy(scenario)
    counterfactual_scenario["environment_agent"]["persona"] = alternate_persona
    base_factory = ModelEnvironmentFactory(
        scenario,
        config["environment"]["provider"],
        config["environment"].get("sampling", {}),
        appraisal_prompt_id=config["environment"].get(
            "appraisal_prompt_id", "environment_appraisal_v11"
        ),
        state_calibration_profile=config["environment"].get(
            "state_calibration_profile", "sparse_v1"
        ),
    )
    persona_factory = ModelEnvironmentFactory(
        counterfactual_scenario,
        config["environment"]["provider"],
        config["environment"].get("sampling", {}),
        appraisal_prompt_id=config["environment"].get(
            "appraisal_prompt_id", "environment_appraisal_v11"
        ),
        state_calibration_profile=config["environment"].get(
            "state_calibration_profile", "sparse_v1"
        ),
    )
    original_output = _replay(base_factory, snapshot, action)
    persona_output = _replay(persona_factory, snapshot, action)
    comparison = _interpretation_comparison(original_output, persona_output)
    return {
        "action": action["text"],
        "fixed_checkpoint": {
            "state": snapshot["state"],
            "dynamics": snapshot["dynamics"],
            "history": snapshot.get("history", []),
        },
        "original_persona": scenario["environment_agent"]["persona"],
        "counterfactual_persona": alternate_persona,
        "original_output": original_output,
        "counterfactual_output": persona_output,
        "comparison": comparison,
        "same_state_history_action": True,
        "automatic_screen_passed": comparison["change_score"] >= 0.1,
        "human_interpretation": "pending",
    }


def _e4(factory, construction_provider, construction_sampling, trajectory, checkpoint):
    snapshot = checkpoint["environment_snapshot_before"]
    original = checkpoint["policy_action"]
    paraphrase = _paraphrase(
        construction_provider, construction_sampling, trajectory, checkpoint
    )
    # Both sides use fresh providers with the same configured seed/call index.
    # Reusing the original rollout transition would confound wording with the
    # rollout's later per-call seed.
    original_output = _replay(factory, snapshot, original)
    paraphrase_output = _replay(factory, snapshot, {"text": paraphrase})
    comparison = _interpretation_comparison(original_output, paraphrase_output)
    direction_consistency = (
        comparison["state_direction_agreement"]
        + comparison["dynamics_direction_agreement"]
    ) / 2
    legacy_direction_consistency = direction_consistency
    metric_groups = compare_transition_outputs(original_output, paraphrase_output)
    overall = metric_groups["overall"]
    all_dimension_direction_agreement = overall["exact_direction_agreement"]
    active_direction_agreement = overall[
        "active_union_direction_agreement"
    ]
    active_change_agreement = overall[
        "active_union_change_no_change_agreement"
    ]
    active_reversal_rate = overall[
        "active_union_true_sign_reversal_rate"
    ]
    direction_consistency = (
        active_direction_agreement
        if active_direction_agreement is not None else 0.0
    )
    comparison.update({
        "overall_direction_agreement": direction_consistency,
        "all_dimension_direction_agreement": all_dimension_direction_agreement,
        "active_union_direction_agreement": active_direction_agreement,
        "active_union_change_no_change_agreement": active_change_agreement,
        "active_union_true_sign_reversal_rate": active_reversal_rate,
        "active_union_dimension_count": overall["active_union_count"],
        "zero_zero_dimension_count": overall["zero_zero_count"],
        "zero_zero_dimension_fraction": overall["zero_zero_fraction"],
        "both_changed_dimension_count": overall["both_changed_count"],
        "both_changed_direction_agreement": overall[
            "both_changed_direction_agreement"
        ],
        "change_no_change_agreement": active_change_agreement,
        "true_sign_reversal_rate": active_reversal_rate,
        "all_dimension_change_no_change_agreement": overall[
            "change_no_change_agreement"
        ],
        "all_dimension_true_sign_reversal_rate": overall[
            "true_sign_reversal_rate"
        ],
        "mean_ordinal_delta_distance": overall["mean_ordinal_delta_distance"],
        "legacy_balanced_group_direction_consistency": round(
            legacy_direction_consistency, 4
        ),
    })
    return {
        "original_action": original["text"],
        "paraphrase": paraphrase,
        "wording_similarity": round(text_similarity(original["text"], paraphrase), 4),
        "original_output": original_output,
        "paraphrase_output": paraphrase_output,
        "comparison": comparison,
        "direction_consistency": round(direction_consistency, 4),
        "all_dimension_direction_agreement": round(
            all_dimension_direction_agreement, 4
        ),
        "automatic_screen_passed": direction_consistency >= 0.8,
        "equivalence_precheck": strict_paraphrase_precheck(original["text"], paraphrase),
        "semantic_equivalence": "pending_human_review",
    }


def _direction_signature(output):
    def sign(value):
        return 0 if value == 0 else (1 if value > 0 else -1)
    pairs = []
    for group in ("numeric_state_delta", "numeric_dynamics_delta"):
        def visit(value, prefix=""):
            if isinstance(value, dict):
                for key in sorted(value):
                    visit(value[key], f"{prefix}.{key}" if prefix else key)
            else:
                pairs.append((f"{group}.{prefix}", sign(value)))
        visit(output[group])
    return pairs


def _appraisal_signature(output):
    appraisal = output.get("appraisal", {})
    impacts = []
    for group in ("state_impacts", "dynamics_impacts"):
        impacts.extend(
            (group, item.get("variable"), item.get("direction"))
            for item in appraisal.get(group, [])
        )
    return {
        "social_act": appraisal.get("social_act"),
        "event_features": appraisal.get("event_features", {}),
        "impacts": sorted(impacts),
    }


def _e5(factory, candidate_generator, checkpoint):
    snapshot = checkpoint["environment_snapshot_before"]
    candidates = candidate_generator.candidate_actions(checkpoint["observation"], count=3)
    branches = []
    for candidate in candidates:
        output = _replay(factory, snapshot, candidate)
        branches.append({
            "candidate_action": candidate["text"],
            "output": output,
            "direction_signature": _direction_signature(output),
        })
    signatures = {
        json.dumps(item["direction_signature"], ensure_ascii=False, sort_keys=True)
        for item in branches
    }
    appraisal_signatures = {
        json.dumps(
            _appraisal_signature(item["output"]),
            ensure_ascii=False,
            sort_keys=True,
        )
        for item in branches
    }
    distinct_actions = {
        item["candidate_action"].strip() for item in branches
    }
    return {
        "checkpoint_history": snapshot.get("history", []),
        "state_before": snapshot["state"],
        "dynamics_before": snapshot["dynamics"],
        "branches": branches,
        "same_checkpoint_verified": True,
        "candidate_action_count": len(branches),
        "distinct_candidate_action_count": len(distinct_actions),
        "distinct_appraisal_signature_count": len(appraisal_signatures),
        "distinct_direction_signature_count": len(signatures),
        "automatic_screen_passed": len(branches) >= 2 and len(signatures) >= 2,
        "social_plausibility": "pending_human_review",
    }


def _load_progress(path, resume):
    if not resume or not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    if not isinstance(records, list):
        raise ValueError("resume file must contain records")
    # Keep every attempt, including errors. Completion is decided separately,
    # so a resumed run retries failures without erasing their audit trail.
    return records


def _successful_record(item):
    return (
        not item.get("error")
        and {"e3", "e4", "e5", "e7"} <= set(item)
    )


def _latest_successful_records(records, experiment_version=None):
    """Use one latest successful attempt per scenario for aggregate evidence."""
    latest = {}
    for item in records:
        if (
            _successful_record(item)
            and item.get("scenario_id")
            and (
                experiment_version is None
                or item.get("experiment_version") == experiment_version
            )
        ):
            latest[item["scenario_id"]] = item
    return [latest[key] for key in sorted(latest)]


def _project_path(path):
    path = Path(path).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _pending_record(path, payload):
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("record", existing).get("human_attestation") is True:
            raise ValueError(f"refusing to overwrite signed human evidence: {path}")
    _write_json(path, payload)


def write_evidence(output_root, records, provenance):
    successful = [item for item in records if not item.get("error")]
    common = {
        "human_attestation": False,
        "reviewers": [],
        "reviewed_at_utc": "",
        "review_status": "pending_human",
        "passed": False,
    }
    e3 = [item for item in successful if item.get("e3")]
    e4 = [item for item in successful if item.get("e4")]
    e5 = [item for item in successful if item.get("e5")]
    e7 = [item for item in successful if item.get("e7")]
    e4_metric_groups = [
        compare_transition_outputs(
            item["e4"]["original_output"], item["e4"]["paraphrase_output"]
        )["overall"]
        for item in e4
    ]

    def weighted_metric(name, count_name):
        denominator = sum(item[count_name] for item in e4_metric_groups)
        if not denominator:
            return 0.0
        return sum(
            (item[name] or 0.0) * item[count_name]
            for item in e4_metric_groups
        ) / denominator

    active_dimension_count = sum(
        item["active_union_count"] for item in e4_metric_groups
    )
    variable_count = sum(item["variable_count"] for item in e4_metric_groups)
    zero_zero_count = sum(item["zero_zero_count"] for item in e4_metric_groups)
    both_changed_count = sum(
        item["both_changed_count"] for item in e4_metric_groups
    )
    e4_score = weighted_metric(
        "active_union_direction_agreement", "active_union_count"
    )
    e4_active_change_agreement = weighted_metric(
        "active_union_change_no_change_agreement", "active_union_count"
    )
    e4_active_reversal_rate = weighted_metric(
        "active_union_true_sign_reversal_rate", "active_union_count"
    )
    e4_all_dimension_score = weighted_metric(
        "exact_direction_agreement", "variable_count"
    )
    e4_both_changed_agreement = weighted_metric(
        "both_changed_direction_agreement", "both_changed_count"
    )
    def e4_metric_mean(name):
        values = [
            item["e4"]["comparison"].get(name) for item in e4
            if item["e4"]["comparison"].get(name) is not None
        ]
        return sum(values) / len(values) if values else 0.0
    payloads = {
        "history_intervention.json": {
            "format": "socialflux_environment_history_intervention_v1",
            "provenance": provenance,
            "record": {
                **common,
                "matched_checkpoint_count": len(e3),
                "same_persona_state_action": bool(e3),
                "automatic_screen_passed_count": sum(item["e3"]["automatic_screen_passed"] for item in e3),
                "automatic_screen_pass_fraction": round(
                    sum(item["e3"]["automatic_screen_passed"] for item in e3)
                    / len(e3), 4
                ) if e3 else 0.0,
                "machine_coverage_ready": len(e3) >= 10,
                "machine_screen_passed": sum(
                    item["e3"]["automatic_screen_passed"] for item in e3
                ) >= 10,
            },
            "records": [{"scenario_id": item["scenario_id"], "source_trajectory_id": item["source_trajectory_id"], "checkpoint_turn_id": item["checkpoint_turn_id"], **item["e3"]} for item in e3],
        },
        "paraphrase_robustness.json": {
            "format": "socialflux_environment_paraphrase_robustness_v1",
            "provenance": provenance,
            "record": {
                **common,
                "pair_count": len(e4),
                "direction_consistency": round(e4_score, 4),
                "active_union_direction_agreement": round(e4_score, 4),
                "all_dimension_direction_agreement": round(
                    e4_all_dimension_score, 4
                ),
                "active_union_dimension_count": active_dimension_count,
                "zero_zero_dimension_count": zero_zero_count,
                "zero_zero_dimension_fraction": round(
                    zero_zero_count / variable_count, 4
                ) if variable_count else None,
                "both_changed_dimension_count": both_changed_count,
                "both_changed_direction_agreement": round(
                    e4_both_changed_agreement, 4
                ) if both_changed_count else None,
                "active_union_change_no_change_agreement": round(
                    e4_active_change_agreement, 4
                ),
                "active_union_true_sign_reversal_rate": round(
                    e4_active_reversal_rate, 4
                ),
                "state_direction_agreement": round(e4_metric_mean("state_direction_agreement"), 4),
                "dynamics_direction_agreement": round(e4_metric_mean("dynamics_direction_agreement"), 4),
                "change_no_change_agreement": round(e4_active_change_agreement, 4),
                "true_sign_reversal_rate": round(e4_active_reversal_rate, 4),
                "all_dimension_change_no_change_agreement": round(
                    weighted_metric(
                        "change_no_change_agreement", "variable_count"
                    ), 4
                ),
                "all_dimension_true_sign_reversal_rate": round(
                    weighted_metric("true_sign_reversal_rate", "variable_count"),
                    4,
                ),
                "mean_ordinal_delta_distance": round(e4_metric_mean("mean_ordinal_delta_distance"), 4),
                "legacy_balanced_group_direction_consistency": round(e4_metric_mean("legacy_balanced_group_direction_consistency"), 4),
                "equivalence_precheck_passed_count": sum(item["e4"]["equivalence_precheck"]["passed"] for item in e4),
                "metric_scope": "state_and_dynamics_active_union_dimension_weighted",
                "machine_screen_passed": len(e4) >= 10 and e4_score >= 0.8,
            },
            "records": [{"scenario_id": item["scenario_id"], "source_trajectory_id": item["source_trajectory_id"], "checkpoint_turn_id": item["checkpoint_turn_id"], **item["e4"]} for item in e4],
        },
        "local_counterfactual.json": {
            "format": "socialflux_environment_local_counterfactual_v1",
            "provenance": provenance,
            "record": {
                **common,
                "checkpoint_count": len(e5),
                "same_checkpoint_verified": bool(e5) and all(item["e5"]["same_checkpoint_verified"] for item in e5),
                "automatic_screen_passed_count": sum(item["e5"]["automatic_screen_passed"] for item in e5),
                "automatic_screen_pass_fraction": round(
                    sum(item["e5"]["automatic_screen_passed"] for item in e5)
                    / len(e5), 4
                ) if e5 else 0.0,
                "machine_coverage_ready": len(e5) >= 10,
                "machine_screen_passed": len(e5) >= 10,
            },
            "records": [{"scenario_id": item["scenario_id"], "source_trajectory_id": item["e5"].get("source_trajectory_id", item["source_trajectory_id"]), "checkpoint_turn_id": item["e5"].get("checkpoint_turn_id", item["checkpoint_turn_id"]), **item["e5"]} for item in e5],
        },
        "persona_intervention.json": {
            "format": "socialflux_environment_persona_intervention_v1",
            "provenance": provenance,
            "record": {
                **common,
                "matched_checkpoint_count": len(e7),
                "same_state_history_action": bool(e7) and all(
                    item["e7"]["same_state_history_action"] for item in e7
                ),
                "automatic_screen_passed_count": sum(
                    item["e7"]["automatic_screen_passed"] for item in e7
                ),
                "automatic_screen_pass_fraction": round(
                    sum(item["e7"]["automatic_screen_passed"] for item in e7)
                    / len(e7), 4
                ) if e7 else 0.0,
                "machine_coverage_ready": len(e7) >= 10,
                "machine_screen_passed": len(e7) >= 10,
            },
            "records": [{
                "scenario_id": item["scenario_id"],
                "source_trajectory_id": item["source_trajectory_id"],
                "checkpoint_turn_id": item["checkpoint_turn_id"],
                **item["e7"],
            } for item in e7],
        },
    }
    for filename, payload in payloads.items():
        _pending_record(output_root / filename, payload)
    return payloads


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, default=Path("configs/scenarios"))
    parser.add_argument("--scenario-root", type=Path, default=Path("configs/scenarios"))
    parser.add_argument("--rollout-config", type=Path, default=Path("configs/rollout_development_mixed.local.json"))
    parser.add_argument("--output-root", type=Path, default=Path("data/formal/environment"))
    parser.add_argument("--scenario-limit", type=int)
    parser.add_argument("--history-evidence", type=Path, default=Path("data/formal/experiments/development_gate3_final/history_dependence.json"))
    parser.add_argument("--existing-intervention-root", type=Path, default=Path("build/pipeline_v2"))
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--environment-routes",
        type=Path,
        help=(
            "optional same-model route table used only for environment appraisal "
            "transport/failover; it does not alter prompts, calibration, or thresholds"
        ),
    )
    parser.add_argument(
        "--stop-after-consecutive-provider-overloads", type=int, default=3,
    )
    args = parser.parse_args()
    args.raw_root = _project_path(args.raw_root)
    args.scenario_root = _project_path(args.scenario_root)
    args.rollout_config = _project_path(args.rollout_config)
    args.output_root = _project_path(args.output_root)
    args.history_evidence = _project_path(args.history_evidence)
    args.existing_intervention_root = _project_path(
        args.existing_intervention_root
    )
    if args.environment_routes is not None:
        args.environment_routes = _project_path(args.environment_routes)
    config = load_rollout_config(args.rollout_config)
    if args.environment_routes is not None:
        config["environment"]["provider"] = ModelRoutes.load(
            args.environment_routes
        ).provider_config("appraisal")
    config["environment"].setdefault("sampling", {})["temperature"] = 0
    config["construction"].setdefault("sampling", {})["temperature"] = 0
    scenarios = {item["scenario_id"]: item for item in load_actual_scenarios(args.scenario_root)}
    selected = select_one_per_scenario(load_records(args.raw_root), args.scenario_limit)
    progress_path = args.output_root / "experiments" / "environment_interventions.json"
    records = _load_progress(progress_path, args.resume)
    completed = {
        item.get("scenario_id") for item in records
        if _successful_record(item)
        and item.get("experiment_version") == EXPERIMENT_VERSION
    }
    construction_provider = build_provider(config["construction"]["provider"])
    candidate_generator = ModelCandidateGenerator(
        construction_provider, config["construction"].get("sampling", {})
    )
    history_payload = (
        json.loads(args.history_evidence.read_text(encoding="utf-8"))
        if args.history_evidence.exists() else {"records": []}
    )
    history_index = {
        item["trajectory_id"]: item for item in history_payload.get("records", [])
        if item.get("environment_interpretation")
        and item["environment_interpretation"].get(
            "full_vs_critical_removed", {}
        ).get("change_score_scope")
        == "active_union_state_or_dynamics_or_structural_appraisal"
    }
    consecutive_provider_overloads = 0
    for trajectory in selected:
        scenario_id = trajectory["scenario_id"]
        if scenario_id in completed:
            continue
        checkpoint = select_intervention_checkpoint(trajectory)
        factory = ModelEnvironmentFactory(
            scenarios[scenario_id],
            config["environment"]["provider"],
            config["environment"].get("sampling", {}),
            appraisal_prompt_id=config["environment"].get(
                "appraisal_prompt_id", "environment_appraisal_v11"
            ),
            state_calibration_profile=config["environment"].get(
                "state_calibration_profile", "sparse_v1"
            ),
        )
        record = {
            "scenario_id": scenario_id,
            "source_trajectory_id": trajectory["trajectory_id"],
            "checkpoint_turn_id": checkpoint["turn_id"],
            "attempt": 1 + sum(
                item.get("scenario_id") == scenario_id for item in records
            ),
            "experiment_version": EXPERIMENT_VERSION,
        }
        try:
            record["e3"] = (
                _existing_e3(history_index[trajectory["trajectory_id"]], checkpoint)
                if trajectory["trajectory_id"] in history_index
                else _e3(factory, trajectory, checkpoint)
            )
            record["e4"] = _e4(
                factory,
                construction_provider,
                config["construction"].get("sampling", {}),
                trajectory,
                checkpoint,
            )
            record["e5"] = _e5(factory, candidate_generator, checkpoint)
            record["e7"] = _e7(
                config,
                construction_provider,
                config["construction"].get("sampling", {}),
                scenarios[scenario_id],
                trajectory,
                checkpoint,
            )
            consecutive_provider_overloads = 0
        except Exception as exc:
            record["error"] = {"type": type(exc).__name__, "message": str(exc)}
            message = str(exc).lower()
            if "429" in message or "overloaded" in message:
                consecutive_provider_overloads += 1
            else:
                consecutive_provider_overloads = 0
        records.append(record)
        _write_json(progress_path, {"format": "socialflux_environment_interventions_progress_v1", "records": records})
        print(json.dumps({"progress": len(records), "total": len(selected), "scenario_id": scenario_id, "error": record.get("error")}, ensure_ascii=False), file=sys.stderr, flush=True)
        if (
            args.stop_after_consecutive_provider_overloads > 0
            and consecutive_provider_overloads
            >= args.stop_after_consecutive_provider_overloads
        ):
            print(json.dumps({
                "paused": "provider_overload",
                "consecutive_overloads": consecutive_provider_overloads,
            }), file=sys.stderr, flush=True)
            break
    provenance = {
        "environment": public_provider_config(config["environment"]["provider"]),
        "environment_sampling": config["environment"].get("sampling", {}),
        "construction": public_provider_config(config["construction"]["provider"]),
        "construction_sampling": config["construction"].get("sampling", {}),
        "prompts": [config["environment"].get("appraisal_prompt_id", "environment_appraisal_v11"), config["environment"].get("state_calibration_profile", "sparse_v1"), "environment_paraphrase_probe_v1", "environment_persona_intervention_v1", "counterfactual_action_generation_v1"],
        "experiment_version": EXPERIMENT_VERSION,
        "checkpoint_selection": "fixed_70_percent_horizon_v1",
        "environment_route_source": (
            str(args.environment_routes)
            if args.environment_routes is not None else "rollout_config"
        ),
        "input_cohort": {
            "scenario_count": len(selected),
            "scenario_ids": sorted(item["scenario_id"] for item in selected),
            "trajectory_ids": sorted(item["trajectory_id"] for item in selected),
            "source_status_counts": dict(sorted(Counter(
                item.get("gate2_audit_input", {}).get(
                    "source_status", "unspecified"
                )
                for item in selected
            ).items())),
            "turn_count_distribution": {
                str(key): value for key, value in sorted(Counter(
                    len(item.get("turns", [])) for item in selected
                ).items())
            },
        },
    }
    evidence_records = _latest_successful_records(
        records, experiment_version=EXPERIMENT_VERSION
    )
    payloads = write_evidence(args.output_root, evidence_records, provenance)
    print(json.dumps({
        "scenario_count": len(selected),
        "completed": len(records),
        "errors": sum(bool(item.get("error")) for item in records),
        "e3_checkpoints": payloads["history_intervention.json"]["record"]["matched_checkpoint_count"],
        "e4_pairs": payloads["paraphrase_robustness.json"]["record"]["pair_count"],
        "e5_checkpoints": payloads["local_counterfactual.json"]["record"]["checkpoint_count"],
        "e7_checkpoints": payloads["persona_intervention.json"]["record"]["matched_checkpoint_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
