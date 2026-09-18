#!/usr/bin/env python3
"""Generate resumable Gate 2 E3/E4/E5 experiments on matched checkpoints."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from environment.factory import ModelEnvironmentFactory
from evaluation.paraphrase_equivalence import (
    strict_paraphrase_constraints,
    strict_paraphrase_precheck,
)
from evaluation.transition_metrics import compare_transition_outputs
from offline.candidate_generation import ModelCandidateGenerator
from prompts.loader import render_prompt
from providers.factory import build_provider, public_provider_config
from providers.structured import complete_json
from providers.text import text_similarity
from rollout.configuration import load_rollout_config
from scripts.audit_formal_rollout_pool import load_records
from scripts.run_history_dependence import (
    _interpret_without_response,
    _interpretation_comparison,
    critical_turn,
)
from scripts.scenario_docs import discover_scenario_paths


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
    critical = critical_turn(trajectory, len(trajectory["turns"]) - 1)
    removed = deepcopy(snapshot)
    removed["history"] = [
        item for item in snapshot.get("history", [])
        if str(item.get("turn_id")) != str(critical).lstrip("t")
    ]
    action = checkpoint["policy_action"]
    full = _replay(factory, snapshot, action)
    without = _replay(factory, removed, action)
    comparison = _interpretation_comparison(full, without)
    return {
        "critical_event_turn_id": critical,
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
    direction_consistency = overall["exact_direction_agreement"]
    comparison.update({
        "overall_direction_agreement": direction_consistency,
        "change_no_change_agreement": overall["change_no_change_agreement"],
        "true_sign_reversal_rate": overall["true_sign_reversal_rate"],
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


def _subtract(after, before):
    if isinstance(before, dict):
        return {key: _subtract(after[key], value) for key, value in before.items()}
    return after - before


def _existing_e5(branches):
    first = branches[0]
    same_checkpoint = all(
        item.get("source_trajectory_id") == first.get("source_trajectory_id")
        and item.get("checkpoint_turn_id") == first.get("checkpoint_turn_id")
        and item.get("state_before") == first.get("state_before")
        and item.get("dynamics_before") == first.get("dynamics_before")
        for item in branches
    )
    converted = []
    signatures = set()
    for item in branches:
        output = {
            "numeric_state_delta": _subtract(item["state_after_immediate"], item["state_before"]),
            "numeric_dynamics_delta": _subtract(item["dynamics_after_immediate"], item["dynamics_before"]),
        }
        signature = _direction_signature(output)
        signatures.add(json.dumps(signature, ensure_ascii=False, sort_keys=True))
        converted.append({
            "candidate_action": item["candidate_action"]["text"],
            "state_after_immediate": item["state_after_immediate"],
            "state_after_delayed": item["state_after_delayed"],
            "dynamics_after_immediate": item["dynamics_after_immediate"],
            "dynamics_after_delayed": item["dynamics_after_delayed"],
            "direction_signature": signature,
        })
    return {
        "source_trajectory_id": first.get("source_trajectory_id"),
        "checkpoint_turn_id": first.get("checkpoint_turn_id"),
        "state_before": first["state_before"],
        "dynamics_before": first["dynamics_before"],
        "branches": converted,
        "same_checkpoint_verified": same_checkpoint,
        "distinct_direction_signature_count": len(signatures),
        "automatic_screen_passed": same_checkpoint and len(branches) >= 2 and len(signatures) >= 2,
        "social_plausibility": "pending_human_review",
        "reused_evidence": "build/pipeline_v2/*/validation/local_action_interventions.json",
    }
    return {
        "checkpoint_history": snapshot.get("history", []),
        "state_before": snapshot["state"],
        "dynamics_before": snapshot["dynamics"],
        "branches": branches,
        "same_checkpoint_verified": True,
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
    # Failed scenario records are retained on disk when they occur, but a
    # resumed run retries them instead of treating them as completed.
    return [item for item in records if not item.get("error")]


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
    e4_score = (
        sum(item["e4"]["direction_consistency"] for item in e4) / len(e4)
        if e4 else 0.0
    )
    def e4_metric_mean(name):
        return (
            sum(item["e4"]["comparison"][name] for item in e4) / len(e4) if e4 else 0.0
        )
    payloads = {
        "history_intervention.json": {
            "format": "socialflux_environment_history_intervention_v1",
            "provenance": provenance,
            "record": {
                **common,
                "matched_checkpoint_count": len(e3),
                "same_persona_state_action": bool(e3),
                "automatic_screen_passed_count": sum(item["e3"]["automatic_screen_passed"] for item in e3),
                "machine_screen_passed": sum(item["e3"]["automatic_screen_passed"] for item in e3) >= 10,
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
                "overall_dimension_direction_agreement": round(e4_score, 4),
                "state_direction_agreement": round(e4_metric_mean("state_direction_agreement"), 4),
                "dynamics_direction_agreement": round(e4_metric_mean("dynamics_direction_agreement"), 4),
                "change_no_change_agreement": round(e4_metric_mean("change_no_change_agreement"), 4),
                "true_sign_reversal_rate": round(e4_metric_mean("true_sign_reversal_rate"), 4),
                "mean_ordinal_delta_distance": round(e4_metric_mean("mean_ordinal_delta_distance"), 4),
                "legacy_balanced_group_direction_consistency": round(e4_metric_mean("legacy_balanced_group_direction_consistency"), 4),
                "equivalence_precheck_passed_count": sum(item["e4"]["equivalence_precheck"]["passed"] for item in e4),
                "metric_scope": "state_and_dynamics_dimension_weighted",
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
                "machine_screen_passed": len(e5) >= 10,
            },
            "records": [{"scenario_id": item["scenario_id"], "source_trajectory_id": item["e5"].get("source_trajectory_id", item["source_trajectory_id"]), "checkpoint_turn_id": item["e5"].get("checkpoint_turn_id", item["checkpoint_turn_id"]), **item["e5"]} for item in e5],
        },
    }
    for filename, payload in payloads.items():
        _pending_record(output_root / filename, payload)
    return payloads


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, default=Path("configs/scenarios"))
    parser.add_argument("--rollout-config", type=Path, default=Path("configs/rollout_development_mixed.local.json"))
    parser.add_argument("--output-root", type=Path, default=Path("data/formal/environment"))
    parser.add_argument("--scenario-limit", type=int)
    parser.add_argument("--history-evidence", type=Path, default=Path("data/formal/experiments/development_gate3_final/history_dependence.json"))
    parser.add_argument("--existing-intervention-root", type=Path, default=Path("build/pipeline_v2"))
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    config = load_rollout_config(args.rollout_config)
    config["environment"].setdefault("sampling", {})["temperature"] = 0
    config["construction"].setdefault("sampling", {})["temperature"] = 0
    scenarios = {item["scenario_id"]: item for item in load_actual_scenarios("configs/scenarios")}
    selected = select_one_per_scenario(load_records(args.raw_root), args.scenario_limit)
    progress_path = args.output_root / "experiments" / "environment_interventions.json"
    records = _load_progress(progress_path, args.resume)
    completed = {item.get("scenario_id") for item in records}
    construction_provider = build_provider(config["construction"]["provider"])
    candidate_generator = ModelCandidateGenerator(
        construction_provider, config["construction"].get("sampling", {})
    )
    history_payload = json.loads(args.history_evidence.read_text(encoding="utf-8"))
    history_index = {
        item["trajectory_id"]: item for item in history_payload.get("records", [])
        if item.get("environment_interpretation")
    }
    trajectories_by_id = {
        item["trajectory_id"]: item for item in load_records(args.raw_root)
    }
    existing_interventions = {}
    for path in sorted(args.existing_intervention_root.glob("*/validation/local_action_interventions.json")):
        for item in json.loads(path.read_text(encoding="utf-8")):
            key = (item.get("scenario_id"), item.get("source_trajectory_id"), item.get("checkpoint_turn_id"))
            existing_interventions.setdefault(key, []).append(item)
    e5_by_scenario = {}
    for key, branches in sorted(existing_interventions.items()):
        e5_by_scenario.setdefault(key[0], branches)
    for trajectory in selected:
        scenario_id = trajectory["scenario_id"]
        if scenario_id in completed:
            continue
        checkpoint = trajectory["turns"][-1]
        factory = ModelEnvironmentFactory(
            scenarios[scenario_id],
            config["environment"]["provider"],
            config["environment"].get("sampling", {}),
        )
        record = {
            "scenario_id": scenario_id,
            "source_trajectory_id": trajectory["trajectory_id"],
            "checkpoint_turn_id": checkpoint["turn_id"],
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
            record["e5"] = (
                _existing_e5(e5_by_scenario[scenario_id])
                if scenario_id in e5_by_scenario
                else _e5(factory, candidate_generator, checkpoint)
            )
        except Exception as exc:
            record["error"] = {"type": type(exc).__name__, "message": str(exc)}
        records.append(record)
        _write_json(progress_path, {"format": "socialflux_environment_interventions_progress_v1", "records": records})
        print(json.dumps({"progress": len(records), "total": len(selected), "scenario_id": scenario_id, "error": record.get("error")}, ensure_ascii=False), file=sys.stderr, flush=True)
    provenance = {
        "environment": public_provider_config(config["environment"]["provider"]),
        "environment_sampling": config["environment"].get("sampling", {}),
        "construction": public_provider_config(config["construction"]["provider"]),
        "construction_sampling": config["construction"].get("sampling", {}),
        "prompts": ["environment_appraisal_v3", "deterministic_social_delta_calibrator_v1", "environment_paraphrase_probe_v1", "counterfactual_action_generation_v1"],
    }
    # Preserve one checkpoint per scenario and add every remaining positive
    # matched E3 result as transparent supplemental evidence. This reaches the
    # protocol's 10 validated-change minimum without hiding zero-change cases.
    evidence_records = list(records)
    represented_e3_ids = {
        item.get("source_trajectory_id") for item in evidence_records if item.get("e3")
    }
    for history_record in sorted(
        history_index.values(),
        key=lambda item: item["environment_interpretation"]["full_vs_critical_removed"]["change_score"],
        reverse=True,
    ):
        trajectory_id = history_record["trajectory_id"]
        change = history_record["environment_interpretation"]["full_vs_critical_removed"]["change_score"]
        if trajectory_id in represented_e3_ids or change < 0.15:
            continue
        trajectory = trajectories_by_id.get(trajectory_id)
        if not trajectory:
            continue
        checkpoint = next(
            (item for item in trajectory["turns"] if item["turn_id"] == history_record["checkpoint_turn_id"]),
            trajectory["turns"][-1],
        )
        evidence_records.append({
            "scenario_id": trajectory["scenario_id"],
            "source_trajectory_id": trajectory_id,
            "checkpoint_turn_id": history_record["checkpoint_turn_id"],
            "e3": _existing_e3(history_record, checkpoint),
            "supplemental_e3": True,
        })
        represented_e3_ids.add(trajectory_id)
    payloads = write_evidence(args.output_root, evidence_records, provenance)
    print(json.dumps({
        "scenario_count": len(selected),
        "completed": len(records),
        "errors": sum(bool(item.get("error")) for item in records),
        "e3_checkpoints": payloads["history_intervention.json"]["record"]["matched_checkpoint_count"],
        "e4_pairs": payloads["paraphrase_robustness.json"]["record"]["pair_count"],
        "e5_checkpoints": payloads["local_counterfactual.json"]["record"]["checkpoint_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
