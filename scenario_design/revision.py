"""Evidence-preserving revision of an existing SocialFlux scenario."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from prompts.loader import render_prompt
from providers.structured import complete_json
from schemas.validate import validate_scenario


REVISION_FORMAT = "socialflux_scenario_revision_v1"
PATCH_FIELDS = {
    "title",
    "mechanism",
    "background",
    "narrative_design",
    "environment_agent",
    "evaluated_agent_role",
    "opening_response",
    "longitudinal_design",
}


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")


def validate_revision(value, source_scenario):
    required = {
        "format", "scenario_id", "decision", "diagnosis", "patch",
        "estimated_natural_turn_range", "task_potential",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("scenario revision top-level fields mismatch")
    if value["format"] != REVISION_FORMAT:
        raise ValueError("scenario revision format mismatch")
    if value["scenario_id"] != source_scenario["scenario_id"]:
        raise ValueError("scenario revision changed scenario_id")
    if value["decision"] not in {"revise", "replace_content"}:
        raise ValueError("scenario revision decision is invalid")
    _text(value["diagnosis"], "diagnosis")
    turn_range = value["estimated_natural_turn_range"]
    if (
        not isinstance(turn_range, list)
        or len(turn_range) != 2
        or any(not isinstance(item, int) for item in turn_range)
        or not 1 <= turn_range[0] <= turn_range[1] <= 20
    ):
        raise ValueError("estimated_natural_turn_range is invalid")
    potential = value["task_potential"]
    if not isinstance(potential, dict) or set(potential) != {"T1", "T2", "T3", "T4"}:
        raise ValueError("task_potential must cover T1-T4")
    if any(item not in {"strong", "usable", "weak"} for item in potential.values()):
        raise ValueError("task_potential rating is invalid")
    patch = value["patch"]
    if not isinstance(patch, dict) or set(patch) != PATCH_FIELDS:
        raise ValueError("scenario revision patch fields mismatch")
    for field in ("title", "mechanism", "background", "opening_response"):
        _text(patch[field], field)
    narrative = patch["narrative_design"]
    if not isinstance(narrative, dict) or set(narrative) != {
        "relationship_structure", "power_structure", "goal_conflict",
        "information_asymmetry", "relevant_history", "meaningful_choice_space",
    }:
        raise ValueError("narrative_design fields mismatch")
    for field in (
        "relationship_structure", "power_structure", "goal_conflict",
        "information_asymmetry",
    ):
        _text(narrative[field], f"narrative_design.{field}")
    for field, minimum, maximum in (
        ("relevant_history", 3, 8),
        ("meaningful_choice_space", 3, 6),
    ):
        items = narrative[field]
        if (
            not isinstance(items, list)
            or not minimum <= len(items) <= maximum
            or any(not isinstance(item, str) or not item.strip() for item in items)
        ):
            raise ValueError(f"narrative_design.{field} is invalid")
    if not any(
        item.strip().startswith("事实边界：")
        for item in narrative["relevant_history"]
    ):
        raise ValueError("relevant_history requires an explicit 事实边界 entry")
    environment = patch["environment_agent"]
    if not isinstance(environment, dict) or not {
        "persona", "explicit_goal", "hidden_intention"
    }.issubset(environment):
        raise ValueError("environment_agent is invalid")
    _text(environment["explicit_goal"], "environment_agent.explicit_goal")
    _text(environment["hidden_intention"], "environment_agent.hidden_intention")
    evaluated = patch["evaluated_agent_role"]
    if not isinstance(evaluated, dict) or set(evaluated) != {
        "character_id", "name", "role", "explicit_goal"
    }:
        raise ValueError("evaluated_agent_role is invalid")
    if evaluated["character_id"] != source_scenario["evaluated_agent_role"]["character_id"]:
        raise ValueError("revision changed evaluated character_id")
    for field in ("name", "role", "explicit_goal"):
        _text(evaluated[field], f"evaluated_agent_role.{field}")
    design = patch["longitudinal_design"]
    if design is not None:
        segments = design.get("segments", []) if isinstance(design, dict) else []
        if not 2 <= len(segments) <= 3:
            raise ValueError("longitudinal revision must contain two or three segments")
        if sum(item.get("max_turns", 0) for item in segments) != 20:
            raise ValueError("longitudinal segment max_turns must sum to 20")
    candidate = apply_revision(source_scenario, value, validate=False)
    validate_scenario(candidate)
    return value


def apply_revision(source_scenario, revision, *, validate=True):
    if validate:
        validate_revision(revision, source_scenario)
    scenario = deepcopy(source_scenario)
    for field, value in revision["patch"].items():
        if field == "longitudinal_design" and value is None:
            scenario.pop(field, None)
        else:
            scenario[field] = deepcopy(value)
    scenario["construction_status"] = {
        "normalization": "claude_fable5_revision_pending_human_review",
        "initial_state": "candidate_pending_human_freeze",
        "quality_gate": "pending_generation_and_semantic_review",
    }
    scenario["quality_gate"] = {
        key: "pending"
        for key in source_scenario.get("quality_gate", {})
    }
    scenario["scenario_design_revision"] = {
        "version": "claude_fable5_scenario_revision_v1",
        "design_model": "claude-fable-5",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_scenario_id": source_scenario["scenario_id"],
        "decision": revision["decision"],
        "diagnosis": revision["diagnosis"],
        "estimated_natural_turn_range": deepcopy(
            revision["estimated_natural_turn_range"]
        ),
        "task_potential": deepcopy(revision["task_potential"]),
        "human_review": "pending",
    }
    validate_scenario(scenario)
    return scenario


def generate_revision(provider, scenario, *, seed, max_attempts=3):
    prompt = render_prompt(
        "scenario_revision_v1",
        {
            "scenario": scenario,
            "immutable_fields": {
                "scenario_id": scenario["scenario_id"],
                "source": scenario["source"],
                "selected_state_variables": scenario["selected_state_variables"],
                "target_state_ids": scenario["target_state_ids"],
                "initial_state": scenario["initial_state"],
                "initial_dynamics": scenario["initial_dynamics"],
                "max_turns": scenario["max_turns"],
            },
        },
    )
    return complete_json(
        provider,
        [{"role": "user", "content": prompt}],
        {"temperature": 0.35, "top_p": 0.9, "seed": seed},
        lambda value: validate_revision(value, scenario),
        context=f"scenario revision {scenario['scenario_id']}",
        max_attempts=max_attempts,
        retry_guidance=(
            "Return the exact required patch fields. Preserve immutable IDs, source, "
            "ontology, and numeric initialization. A longitudinal design is optional; "
            "when present it must pass the existing scenario schema and its segment "
            "max_turns must sum to 20."
        ),
    )
