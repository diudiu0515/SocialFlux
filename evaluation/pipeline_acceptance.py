"""Revision-compliant acceptance over natural trajectories and local interventions."""

import json
from pathlib import Path

from .environment_validity import (
    local_action_intervention_evidence,
    seed_coverage,
    trajectory_structure,
)
from scripts.scenario_docs import (
    assert_document_current,
    assert_manifest_current,
    discover_scenario_paths,
)


CRITERIA = (
    "1. State-Update Human Agreement",
    "2. Persona Sensitivity",
    "3. Paraphrase Robustness",
    "4. History Intervention",
    "5. Local Action Intervention",
    "6. Neutral-State Stability",
    "7. Response-State Consistency",
    "8. Full-Trajectory Plausibility",
    "9. Seed Robustness",
)


def load_scenarios(directory):
    directory = Path(directory)
    assert_manifest_current(directory)
    scenarios = []
    for path in discover_scenario_paths(directory):
        assert_document_current(path)
        scenarios.append(json.loads(path.read_text(encoding="utf-8")))
    return scenarios


def load_trajectory_pool(directory):
    trajectories = []
    for bundle in sorted(Path(directory).glob("scenario_*/rollouts")):
        manifest_path = bundle / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("config", {}).get("origin") != "free_form_model_interaction":
            continue
        for trajectory_id in manifest.get("trajectory_ids", []):
            path = bundle / f"{trajectory_id}.json"
            if path.exists():
                trajectories.append(json.loads(path.read_text(encoding="utf-8")))
    return trajectories


def load_local_interventions(output_dir):
    records = []
    for path in sorted(Path(output_dir).glob("*/validation/local_action_interventions.json")):
        records.extend(json.loads(path.read_text(encoding="utf-8")))
    return records


def _pending(criterion, requirement):
    return {
        "criterion": criterion,
        "status": "pending",
        "requirement": requirement,
    }


def build_acceptance_report(scenarios, trajectories=None, interventions=None):
    trajectories = list(trajectories or [])
    interventions = list(interventions or [])
    structures = [
        {
            "trajectory_id": trajectory.get("trajectory_id"),
            **trajectory_structure(trajectory),
        }
        for trajectory in trajectories
    ]
    structural_ready = bool(structures) and all(item["passed"] for item in structures)
    intervention_groups = {}
    for branch in interventions:
        key = (
            branch.get("scenario_id", "unknown"),
            branch.get("source_trajectory_id", "unknown"),
            branch.get("checkpoint_turn_id", "unknown"),
        )
        intervention_groups.setdefault(key, []).append(branch)
    local_evidence = [
        {
            "checkpoint": list(key),
            **local_action_intervention_evidence(branches),
        }
        for key, branches in intervention_groups.items()
    ]
    local_ready = bool(local_evidence) and all(item["divergent"] for item in local_evidence)
    seeds = seed_coverage(trajectories)

    criteria = [
        _pending(
            CRITERIA[0],
            "30–50 sampled transitions, three human annotators, direction/plausibility agreement",
        ),
        _pending(
            CRITERIA[1],
            "same checkpoint/action with persona-only intervention and human interpretation",
        ),
        _pending(
            CRITERIA[2],
            "human-approved paraphrase pairs evaluated by the model state updater",
        ),
        _pending(
            CRITERIA[3],
            "same checkpoint with one causally relevant historical event removed",
        ),
        {
            "criterion": CRITERIA[4],
            "status": "evidence_ready" if local_ready else "pending",
            "automated_evidence": local_evidence,
            "human_judgment": "pending",
            "requirement": "shared real checkpoint, free-form alternative actions, qualitative human validation",
        },
        _pending(
            CRITERIA[5],
            "human-identified neutral/no-op actions and transition-drift analysis",
        ),
        _pending(
            CRITERIA[6],
            "same context with controlled hidden-state intervention and response comparison",
        ),
        {
            "criterion": CRITERIA[7],
            "status": "provisionally_ready" if structural_ready else "pending",
            "trajectory_count": len(trajectories),
            "structural_checks": structures,
            "formal_human_judgment": "pending",
            "requirement": "15–20 complete natural trajectories reviewed by three annotators",
        },
        {
            "criterion": CRITERIA[8],
            "status": "evidence_ready" if seeds["ready"] else "pending",
            "seed_coverage": seeds,
            "human_judgment": "pending",
            "requirement": "same model/config across multiple seeds plus qualitative direction comparison",
        },
    ]
    return {
        "format": "socialflux_environment_acceptance_v2",
        "scenario_count": len(scenarios),
        "trajectory_count": len(trajectories),
        "trajectory_origin_required": "free_form_model_interaction",
        "criteria": criteria,
        "gate": {
            "automated_artifacts_ready": structural_ready and local_ready and seeds["ready"],
            "research_acceptance": all(item["status"] == "passed" for item in criteria),
            "formal_human_pending": [item["criterion"] for item in criteria],
            "deprecated_checks": [
                "multi-turn repair/neutral/escalation controlled-policy sensitivity",
                "scenario-authored expected state-delta matching",
            ],
        },
    }
