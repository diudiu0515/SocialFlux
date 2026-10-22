"""Revision-compliant acceptance over natural trajectories and local interventions."""

import json
from pathlib import Path

from .environment_validity import (
    local_action_intervention_evidence,
    trajectory_structure,
)
from .timescale_validity import build_timescale_review_items
from scenario_design.catalog import assert_document_current, assert_manifest_current, discover_scenario_paths


CRITERIA = (
    "1. State-Update Human Agreement",
    "2. Persona Sensitivity",
    "3. Paraphrase Robustness",
    "4. History Intervention",
    "5. Local Action Intervention",
    "6. Neutral-State Stability",
    "7. Response-State Consistency",
    "8. Full-Trajectory Plausibility",
    "9. Timescale Validity",
)


def load_scenarios(directory):
    directory = Path(directory)
    assert_manifest_current(directory)
    scenarios = []
    for path in discover_scenario_paths(directory):
        assert_document_current(path)
        scenarios.append(json.loads(path.read_text(encoding="utf-8")))
    return scenarios


def _pending(criterion, requirement):
    return {
        "criterion": criterion,
        "status": "pending",
        "requirement": requirement,
    }


def build_acceptance_report(
    scenarios,
    trajectories=None,
    interventions=None,
    instance_quality=None,
):
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
    trajectory_quality = (instance_quality or {}).get("trajectory_quality")
    quality_ready = True
    if trajectory_quality is not None:
        quality_ready = (
            trajectory_quality.get("trajectory_count") == len(trajectories)
            and trajectory_quality.get("passed") == len(trajectories)
        )
    trajectory_ready = structural_ready and quality_ready
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
    timescale_items = build_timescale_review_items(trajectories, limit=40)
    timescale_families = {
        name: sum(
            item["expected_timescale_prior"] == name
            for item in timescale_items
        )
        for name in ("fast", "medium", "slow", "context_dependent")
    }
    timescale_ready = (
        len(timescale_items) >= 10
        and all(timescale_families[name] >= 1 for name in ("fast", "medium", "slow"))
        and any(item["changed_turn_count"] > 0 for item in timescale_items)
    )

    criteria = [
        _pending(
            CRITERIA[0],
            "30–50 sampled transitions reviewed by one named human for direction/plausibility",
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
            "status": "provisionally_ready" if trajectory_ready else "pending",
            "trajectory_count": len(trajectories),
            "structural_checks": structures,
            "quality_checks": trajectory_quality,
            "formal_human_judgment": "pending",
            "requirement": "15–20 complete natural trajectories reviewed by one named primary reviewer",
        },
        {
            "criterion": CRITERIA[8],
            "status": "evidence_ready" if timescale_ready else "pending",
            "candidate_variable_count": len(timescale_items),
            "timescale_families": timescale_families,
            "review_items": timescale_items,
            "human_judgment": "pending",
            "requirement": (
                "10+ state variables covering fast/medium/slow priors, with human "
                "review of context-dependent speed, persistence and reversals"
            ),
        },
    ]
    return {
        "format": "socialflux_environment_acceptance_v3",
        "scenario_count": len(scenarios),
        "trajectory_count": len(trajectories),
        "trajectory_origin_required": "free_form_model_interaction",
        "criteria": criteria,
        "gate": {
            "automated_artifacts_ready": trajectory_ready and local_ready and timescale_ready,
            "research_acceptance": all(item["status"] == "passed" for item in criteria),
            "formal_human_pending": [item["criterion"] for item in criteria],
            "deprecated_checks": [
                "multi-turn repair/neutral/escalation controlled-policy sensitivity",
                "scenario-authored expected state-delta matching",
            ],
        },
    }
