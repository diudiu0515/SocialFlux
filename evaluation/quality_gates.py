"""Strict four-layer quality-gate audit for SocialFlux artifacts.

This module intentionally treats machine checks, independent-model evidence and
human approval as different evidence classes.  A missing class is ``pending``;
it is never converted into a pass by a heuristic.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path

from evaluation.instance_quality import build_instance_quality_report
from evaluation.rollout_gate import audit_pool_contract, audit_rollout, content_sha256
from schemas.validate import QUALITY_CHECKS, validate_scenario
from evaluation.review_registry import validate_human_review


SCENARIO_CHECKS = (
    "social_mechanism",
    "real_tradeoff",
    "both_sides_have_goals",
    "no_unique_script",
    "history_changes_meaning",
    "multiple_plausible_trajectories",
    "t1_suitability",
    "t2_suitability",
    "t3_suitability",
    "t4_adaptation_opportunity",
    "no_hidden_state_leakage",
    "narrative_provenance",
    "narrative_originalization",
    "quality_checklist",
    "human_approval",
)

ENVIRONMENT_EVIDENCE = {
    "E1_state_transition_agreement": "state_transition_agreement.json",
    "E2_full_trajectory_plausibility": "trajectory_plausibility.json",
    "E3_history_intervention": "history_intervention.json",
    "E4_paraphrase_robustness": "paraphrase_robustness.json",
    "E5_local_counterfactual": "local_counterfactual.json",
    "E6_backbone_sensitivity": "backbone_sensitivity.json",
}

TASK_REVIEW_RATINGS = {
    "T1_state_tracking": {
        "from_free_form_rollout", "target_state_meaningful",
        "history_evidence_present", "current_only_insufficient",
        "nontrivial_transition", "no_hidden_state_leakage", "human_answerable",
    },
    "T2_history_sensitive_merge": {
        "histories_from_natural_rollouts", "meaningful_history_divergence",
        "shared_observation_identical", "shared_video_identical_or_not_applicable",
        "shared_observation_natural_after_both", "state_interpretation_differs",
        "current_observation_nonleaking", "causal_history_evidence_localizable",
    },
    "T3_counterfactual_choice_effect": {
        "checkpoint_from_natural_rollout", "actions_socially_plausible",
        "no_obvious_good_bad_choice", "real_social_tradeoff",
        "immediate_effect_judgable", "delayed_effect_judgable",
        "same_continuation_protocol", "no_simulator_instability_reversal",
        "human_effect_judgable",
    },
}


def _status(checks):
    values = [item["status"] for item in checks.values()]
    if "fail" in values:
        return "rejected"
    if "pending" in values or "revise" in values:
        return "pending"
    return "passed"


def _check(status, reason):
    return {"status": status, "reason": reason}


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def audit_scenario_gate(scenario, scenario_path=None, review_registry=None):
    """Audit Gate 1 and preserve the cryptographic human-review boundary."""
    design = scenario.get("narrative_design", {})
    environment = scenario.get("environment_agent", {})
    evaluated = scenario.get("evaluated_agent_role", {})
    source = scenario.get("source", {})
    choices = design.get("meaningful_choice_space", [])
    history = design.get("relevant_history", [])
    target_states = scenario.get("target_state_ids", [])
    selected = scenario.get("selected_state_variables", {})
    checks = {
        "social_mechanism": _check(
            "pass" if _nonempty(scenario.get("mechanism")) else "fail",
            "mechanism must be explicit",
        ),
        "real_tradeoff": _check(
            "pass" if _nonempty(design.get("goal_conflict")) and len(choices) >= 2 else "fail",
            "goal conflict and at least two meaningful choices are required",
        ),
        "both_sides_have_goals": _check(
            "pass" if _nonempty(environment.get("explicit_goal")) and _nonempty(evaluated.get("explicit_goal")) else "fail",
            "both participants need explicit goals/incentives",
        ),
        "no_unique_script": _check(
            "pass" if len(choices) >= 2 and not any(key in scenario for key in ("action_effects", "response_templates")) else "fail",
            "scenario must leave multiple free-form responses without scripted effects",
        ),
        "history_changes_meaning": _check(
            "pass" if len(history) >= 2 and _nonempty(design.get("information_asymmetry")) else "fail",
            "relevant history and information asymmetry are required",
        ),
        "multiple_plausible_trajectories": _check(
            "pass" if len(choices) >= 3 else "revise",
            "at least three plausible choice directions are needed",
        ),
        "t1_suitability": _check(
            "pass" if target_states and selected else "fail",
            "target state IDs and selected state variables are required",
        ),
        "t2_suitability": _check(
            "pass" if len(history) >= 2 and _nonempty(design.get("information_asymmetry")) else "fail",
            "T2 needs divergent history with current-observation control",
        ),
        "t3_suitability": _check(
            "pass" if len(choices) >= 3 else "revise",
            "T3 needs multiple socially plausible actions",
        ),
        "t4_adaptation_opportunity": _check(
            "pass" if _nonempty(design.get("relationship_structure")) and _nonempty(design.get("power_structure")) else "fail",
            "T4 needs a continuing relationship and adaptive power context",
        ),
        "no_hidden_state_leakage": _check(
            "pass" if _nonempty(environment.get("hidden_intention")) and not any(
                key in scenario for key in ("action_effects", "response_templates", "observable_cues_by_action")
            ) else "fail",
            "private intention may exist, but scripted state/action mappings may not",
        ),
        "narrative_provenance": _check("pass", "synthetic-script has no external source requirement"),
        "narrative_originalization": _check("pass", "synthetic-script has no external source requirement"),
        "quality_checklist": _check("pending", "quality_gate checklist has not been human-reviewed"),
        "human_approval": _check("pending", "quality approval and S0/D0 freeze require a real reviewer"),
    }
    if source.get("type") == "narrative-derived":
        missing = [key for key in ("work_title", "year", "medium", "related_characters_or_plot_position") if not source.get(key)]
        # Existing source records use a provenance note, but the protocol asks
        # for a reproducible work/year/media/plot-position record.
        checks["narrative_provenance"] = _check(
            "revise" if missing else "pass",
            "missing narrative provenance fields: " + ", ".join(missing) if missing else "narrative provenance is recorded",
        )
        original = (
            source.get("surface_text_policy") == "original_surface_text"
            and source.get("redistribution_status") == "transformed_structural_abstraction"
            and "no copied dialogue" in source.get("provenance_note", "").lower()
        )
        checks["narrative_originalization"] = _check(
            "pass" if original else "revise",
            "requires structural abstraction, original surface text, and an explicit no-copied-dialogue release record",
        )
    checklist = scenario.get("quality_gate", {})
    if set(checklist) != QUALITY_CHECKS:
        checks["quality_checklist"] = _check("fail", "quality_gate checklist does not match the canonical set")
    elif any(value == "fail" for value in checklist.values()):
        checks["quality_checklist"] = _check("fail", "quality_gate contains a human-marked fail")
    elif any(value != "pass" for value in checklist.values()):
        checks["quality_checklist"] = _check("pending", "quality_gate contains pending checks")
    else:
        checks["quality_checklist"] = _check("pass", "all quality checklist entries are pass")
    if scenario.get("construction_status", {}).get("quality_gate") == "approved" and scenario.get("construction_status", {}).get("initial_state") == "human_frozen":
        if scenario_path is not None and review_registry is not None:
            try:
                validate_human_review(scenario, scenario_path, review_registry)
                checks["human_approval"] = _check("pass", "signed review is bound to the exact scenario file")
            except ValueError as exc:
                checks["human_approval"] = _check("fail", str(exc))
        else:
            checks["human_approval"] = _check("pending", "approved status requires a cryptographically bound human review registry")
    try:
        validate_scenario(scenario)
        schema = _check("pass", "canonical scenario schema validates")
    except (TypeError, ValueError) as exc:
        schema = _check("fail", str(exc))
    checks["schema"] = schema
    status = _status(checks)
    return {
        "gate": "gate_1_scenario_quality",
        "scenario_id": scenario.get("scenario_id"),
        "status": status,
        "passed": status == "passed",
        "checks": checks,
    }


def _read_evidence(root, filename):
    if root is None:
        return None
    path = Path(root) / filename
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _environment_evidence_passes(name, payload):
    if not isinstance(payload, dict):
        return False, "evidence must be a JSON object"
    record = payload.get("record", payload)
    if not isinstance(record, dict):
        return False, "evidence record must be a JSON object"
    def at_least(value, threshold):
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value >= threshold
        )
    def human_record(minimum_reviewers):
        reviewers = record.get("reviewers", [])
        if (
            record.get("human_attestation") is not True
            or not isinstance(reviewers, list)
            or len(reviewers) < minimum_reviewers
            or len(set(reviewers)) != len(reviewers)
            or any(not str(item).strip() for item in reviewers)
        ):
            return False
        try:
            reviewed_at = datetime.fromisoformat(
                str(record.get("reviewed_at_utc", "")).replace("Z", "+00:00")
            )
        except ValueError:
            return False
        return reviewed_at.tzinfo is not None
    if name == "E1_state_transition_agreement":
        passed = (
            human_record(3)
            and record.get("annotator_count", 0) >= 3
            and 30 <= record.get("transition_count", 0) <= 50
            and at_least(record.get("agreement"), 0.70)
        )
        return passed, "requires 3+ named humans, timestamp, 30–50 transitions and agreement >=0.70"
    if name == "E2_full_trajectory_plausibility":
        scores = record.get("scores", {})
        passed = (
            human_record(3)
            and record.get("annotator_count", 0) >= 3
            and 15 <= record.get("trajectory_count", 0) <= 20
            and at_least(scores.get("overall"), 4.0)
            and all(at_least(scores.get(key), 3.5) for key in (
                "persona_consistency", "history_sensitivity", "state_continuity", "response_state_consistency"
            ))
        )
        return passed, "requires 3+ named humans, timestamp, 15–20 trajectories, overall >=4 and each named dimension >=3.5"
    if name == "E3_history_intervention":
        passed = (
            record.get("passed") is True
            and human_record(1)
            and record.get("matched_checkpoint_count", 0) >= 10
            and record.get("same_persona_state_action") is True
        )
        return passed, "requires a named human and timestamp, 10+ matched checkpoints, same persona/state/action and validated change"
    if name == "E4_paraphrase_robustness":
        passed = (
            record.get("passed") is True
            and human_record(1)
            and record.get("pair_count", 0) >= 10
            and at_least(record.get("direction_consistency"), 0.80)
        )
        return passed, "requires a named human and timestamp, 10+ approved pairs and direction consistency >=0.80"
    if name == "E5_local_counterfactual":
        passed = (
            record.get("passed") is True
            and human_record(1)
            and record.get("checkpoint_count", 0) >= 10
            and record.get("same_checkpoint_verified") is True
        )
        return passed, "requires a named human and timestamp, 10+ same-checkpoint interventions and validity judgment"
    if name == "E6_backbone_sensitivity":
        families = {
            item.get("model_family") for item in payload.get("backbones", [])
            if item.get("model_family")
        }
        passed = (
            payload.get("format") == "socialflux_backbone_sensitivity_v1"
            and record.get("passed") is True
            and record.get("matched_checkpoint_count", 0) >= 10
            and len(families) >= 2
        )
        return passed, "requires 10+ matched checkpoints and two different environment model families"
    return False, "unknown environment evidence type"


def audit_environment_gate(scenarios, evidence_root=None):
    checks = {}
    evidence = {}
    for name, filename in ENVIRONMENT_EVIDENCE.items():
        value = _read_evidence(evidence_root, filename)
        evidence[name] = {"file": filename, "present": value is not None}
        if value is None:
            checks[name] = _check("pending", f"missing independent evidence file {filename}")
            continue
        passed, reason = _environment_evidence_passes(name, value)
        checks[name] = _check("pass" if passed else "fail", reason)
    status = _status(checks)
    return {
        "gate": "gate_2_environment_validity",
        "status": status,
        "passed": status == "passed",
        "scenario_count": len(scenarios),
        "checks": checks,
        "evidence": evidence,
    }


def load_rollouts(root, require_selected_manifest=False):
    root = Path(root)
    if not root.exists():
        return []
    nested = any((path / "rollouts").is_dir() for path in root.glob("scenario_*"))
    rollout_dirs = sorted(
        path / "rollouts" if nested else path
        for path in root.glob("scenario_*")
        if (path / "rollouts" if nested else path).is_dir()
    )
    if require_selected_manifest:
        for scenario_dir in rollout_dirs:
            manifest_path = scenario_dir / "manifest.json"
            if not manifest_path.exists():
                raise ValueError(f"selected rollout pool is missing {manifest_path}")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("format") != "socialflux_rollout_manifest_v2":
                raise ValueError(f"{manifest_path} has an unsupported format")
            config = manifest.get("config", {})
            if config.get("pool_stage") != "formal_selected":
                raise ValueError(f"{manifest_path} is not a formal_selected manifest")
            audits = config.get("quality_audits", [])
            trajectory_ids = manifest.get("trajectory_ids", [])
            audit_ids = [item.get("trajectory_id") for item in audits]
            actual_ids = []
            for candidate in scenario_dir.glob("*.json"):
                if candidate.name in {"manifest.json", "quality_report.json"}:
                    continue
                payload = json.loads(candidate.read_text(encoding="utf-8"))
                if payload.get("turns"):
                    actual_ids.append(payload.get("trajectory_id"))
            if (
                not audits
                or len(set(trajectory_ids)) != len(trajectory_ids)
                or set(trajectory_ids) != set(audit_ids)
                or set(trajectory_ids) != set(actual_ids)
                or not all(item.get("passed") is True for item in audits)
            ):
                raise ValueError(f"{manifest_path} does not contain all-passing quality audits")
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
    records = []
    seen = set()
    for path in sorted(paths):
        if not path.exists():
            raise ValueError(f"rollout manifest references missing trajectory {path}")
        if path.parent.name == "rejected":
            continue
        value = json.loads(path.read_text(encoding="utf-8"))
        identifier = value.get("trajectory_id")
        if identifier and identifier not in seen and value.get("turns"):
            records.append(value)
            seen.add(identifier)
    return records


def _index(path):
    if path is None or not Path(path).exists():
        return {}
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    records = value if isinstance(value, list) else value.get("records", [])
    return {item["trajectory_id"]: item for item in records if item.get("trajectory_id")}


def audit_rollout_gate(
    trajectories,
    judgments_path=None,
    history_path=None,
    selected_by_scenario=None,
    pool_stage="raw",
):
    if pool_stage not in {"raw", "selected"}:
        raise ValueError("rollout pool stage must be raw or selected")
    judgments = _index(judgments_path)
    history = _index(history_path)
    audits = [audit_rollout(item, judgments.get(item["trajectory_id"]), history.get(item["trajectory_id"])) for item in trajectories]
    if pool_stage == "selected" and selected_by_scenario is None:
        selected_by_scenario = defaultdict(list)
        for trajectory in trajectories:
            selected_by_scenario[trajectory.get("scenario_id")].append(trajectory)
    contract = audit_pool_contract(
        trajectories,
        selected_by_scenario,
        require_raw_minimum=pool_stage == "raw",
    )
    hard_contract = {
        "api_fraction_at_most_30_percent": contract["checks"]["api_fraction_at_most_30_percent"],
        "environment_policy_separated": contract["checks"]["environment_policy_separated"],
    }
    status = "passed" if contract["passed"] and all(item["passed"] for item in audits) else (
        "rejected" if any(item["status"] == "rejected" for item in audits) or not all(hard_contract.values()) else "pending"
    )
    by_scenario = defaultdict(lambda: {"raw": 0, "passed": 0, "pending": 0, "rejected": 0})
    for item in audits:
        row = by_scenario[item["scenario_id"]]
        row["raw"] += 1
        status_key = "pending" if item["status"] == "pending_evidence" else item["status"]
        row[status_key] += 1
    scenario_rows = dict(by_scenario)
    for row in scenario_rows.values():
        row["raw_shortfall_to_12"] = (
            max(0, 12 - row["raw"]) if pool_stage == "raw" else 0
        )
        row["quality_evidence_shortfall"] = row["pending"]
    return {
        "gate": "gate_3_rollout_quality",
        "status": status,
        "passed": status == "passed",
        "trajectory_count": len(trajectories),
        "audits": audits,
        "by_scenario": scenario_rows,
        "pool_contract": contract,
        "pool_stage": pool_stage,
        "supplement_needed": {
            "raw_trajectories_to_12": sum(row["raw_shortfall_to_12"] for row in scenario_rows.values()),
            "local_model_families_to_3": max(0, 3 - len(contract["local_model_families"])),
            "independent_quality_or_history_reviews": sum(row["quality_evidence_shortfall"] for row in scenario_rows.values()),
        },
    }


def _read_jsonl(path):
    if path is None or not Path(path).exists():
        return []
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _read_interventions(root):
    if root is None or not Path(root).exists():
        return []
    records = []
    for path in sorted(Path(root).glob("*/validation/local_action_interventions.json")):
        records.extend(json.loads(path.read_text(encoding="utf-8")))
    return records


def audit_task_instance_gate(instances, trajectories, interventions=None, human_review_path=None, gate3_passed_ids=None):
    structural = build_instance_quality_report(instances, trajectories, interventions or [])
    audits = structural["instances"]
    gate3_passed_ids = set(gate3_passed_ids or ())
    source_ready = []
    for instance in instances:
        ids = instance.get("metadata", {}).get("source_trajectory_ids") or [instance.get("metadata", {}).get("source_trajectory_id")]
        ids = [item for item in ids if item]
        source_ready.append(bool(ids) and all(item in gate3_passed_ids for item in ids))
    human_review = _read_jsonl(human_review_path)
    instance_ids = {item.get("instance_id") for item in instances}
    instances_by_id = {item.get("instance_id"): item for item in instances}
    reviewed_ids = set()
    invalid_reviews = []
    for item in human_review:
        instance_id = item.get("instance_id")
        instance = instances_by_id.get(instance_id)
        try:
            reviewed_at = datetime.fromisoformat(
                str(item.get("reviewed_at_utc", "")).replace("Z", "+00:00")
            )
        except ValueError:
            reviewed_at = None
        valid = (
            instance is not None
            and item.get("human_attestation") is True
            and item.get("review_status") == "approved"
            and bool(str(item.get("reviewer", "")).strip())
            and reviewed_at is not None
            and reviewed_at.tzinfo is not None
            and item.get("instance_sha256") == content_sha256(instance)
            and set(item.get("ratings", {})) == TASK_REVIEW_RATINGS.get(instance.get("task_type"), set())
            and all(value is True for value in item.get("ratings", {}).values())
        )
        if valid:
            reviewed_ids.add(instance_id)
        else:
            invalid_reviews.append(instance_id)
    checks = {
        "structural_checks": _check("pass" if structural["structurally_passed"] == structural["instance_count"] and structural["instance_count"] else "fail", "all instance contract checks pass"),
        "source_trajectory_gate3": _check("pass" if source_ready and all(source_ready) else "pending", "every instance source must pass Gate 3"),
        "independent_or_human_semantic_review": _check(
            "pass" if human_review and reviewed_ids == instance_ids and not invalid_reviews else "pending",
            "every candidate needs a named, timestamped, hash-bound blind human review; invalid=" + str(invalid_reviews),
        ),
    }
    status = _status(checks)
    eligible = [instance for instance, ready, audit in zip(instances, source_ready, audits) if ready and audit["passed"]]
    task_counts = Counter(instance.get("task_type") for instance in instances)
    return {
        "gate": "gate_4_task_instance_quality",
        "status": status,
        "passed": status == "passed",
        "instance_count": len(instances),
        "structurally_passed": structural["structurally_passed"],
        "eligible_instance_count": len(eligible),
        "task_counts": dict(task_counts),
        "checks": checks,
        "quality_report": structural,
    }


def audit_all_gates(scenarios, trajectories, instances, interventions=None, environment_evidence=None, judgments_path=None, history_path=None, human_review_path=None, scenario_paths=None, review_registry=None, rollout_stage="raw"):
    scenario_paths = scenario_paths or {}
    gate1 = [audit_scenario_gate(scenario, scenario_paths.get(scenario.get("scenario_id")), review_registry) for scenario in scenarios]
    gate1_status = "passed" if gate1 and all(item["passed"] for item in gate1) else ("rejected" if any(item["status"] == "rejected" for item in gate1) else "pending")
    gate2 = audit_environment_gate(scenarios, environment_evidence)
    gate3 = audit_rollout_gate(
        trajectories,
        judgments_path,
        history_path,
        pool_stage=rollout_stage,
    )
    if rollout_stage == "selected":
        expected_scenarios = {item.get("scenario_id") for item in scenarios}
        observed_scenarios = {item.get("scenario_id") for item in trajectories}
        scenario_coverage = expected_scenarios == observed_scenarios
        gate3["selected_scenario_coverage"] = {
            "passed": scenario_coverage,
            "missing": sorted(expected_scenarios - observed_scenarios),
            "unexpected": sorted(observed_scenarios - expected_scenarios),
        }
        if not scenario_coverage:
            gate3["passed"] = False
            gate3["status"] = "rejected"
    passed_ids = [item["trajectory_id"] for item in gate3["audits"] if item["passed"]]
    gate4 = audit_task_instance_gate(instances, trajectories, interventions, human_review_path, passed_ids)
    gates = {"gate_1_scenario_quality": {"status": gate1_status, "passed": gate1_status == "passed", "scenarios": gate1}, "gate_2_environment_validity": gate2, "gate_3_rollout_quality": gate3, "gate_4_task_instance_quality": gate4}
    deficiencies = []
    for item in gate1:
        if not item["passed"]:
            deficiencies.append({"gate": "gate_1_scenario_quality", "scenario_id": item["scenario_id"], "status": item["status"]})
    for gate_name, gate in (("gate_2_environment_validity", gate2), ("gate_3_rollout_quality", gate3), ("gate_4_task_instance_quality", gate4)):
        if not gate["passed"]:
            deficiencies.append({"gate": gate_name, "status": gate["status"]})
    return {
        "format": "socialflux_four_quality_gates_v1",
        "scenario_count": len(scenarios),
        "trajectory_count": len(trajectories),
        "instance_count": len(instances),
        "gates": gates,
        "eligible_trajectory_count": len(passed_ids),
        "deficiencies": deficiencies,
        "research_ready": all(gate["passed"] for gate in [
            {"passed": gate1_status == "passed"}, gate2, gate3, gate4,
        ]),
        "human_boundary": "No automated, model, or structural result can replace scenario/S0-D0 approval, environment human validation, blind task review, or formal human GT.",
    }
