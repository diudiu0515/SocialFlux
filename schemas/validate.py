"""Dependency-free validation for canonical SocialFlux contracts."""

from pathlib import Path
import json

FORBIDDEN_SCENARIO_FIELDS = {
    "action_effects",
    "response_templates",
    "observable_cues_by_action",
}
QUALITY_CHECKS = {
    "social_plausibility",
    "real_tradeoff",
    "longitudinal_necessity",
    "nontrivial_strategy_space",
    "character_motivation_coherence",
    "information_asymmetry",
    "t1_suitability",
    "t2_suitability",
    "t3_suitability",
    "t4_adaptation_opportunity",
    "no_universal_script",
}
DELTA_LABELS = {
    "strong_decrease", "moderate_decrease", "mild_decrease", "similar",
    "mild_increase", "moderate_increase", "strong_increase",
}


def _bounded(value, path):
    if isinstance(value, dict):
        for key, item in value.items():
            _bounded(item, f"{path}.{key}")
    elif not isinstance(value, (int, float)) or not 0 <= value <= 10:
        raise ValueError(f"{path} must be numeric in [0, 10]")


def _validate_multimodal(scenario):
    values = {}

    def collect(node, prefix=""):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                collect(value, path)
            else:
                values[path] = value

    collect(scenario.get("initial_state", {}))
    collect(scenario.get("initial_dynamics", {}))
    operators = {
        ">=": lambda value, threshold: value >= threshold,
        ">": lambda value, threshold: value > threshold,
        "<=": lambda value, threshold: value <= threshold,
        "<": lambda value, threshold: value < threshold,
        "==": lambda value, threshold: value == threshold,
    }
    triggers = scenario.get("video_triggers", [])
    if len(triggers) != 3:
        raise ValueError("canonical scenario must define exactly three video triggers")
    priorities = [trigger.get("priority") for trigger in triggers]
    if any(not isinstance(priority, int) or priority < 1 for priority in priorities):
        raise ValueError("every video trigger requires a positive integer priority")
    if len(set(priorities)) != len(priorities):
        raise ValueError("video trigger priorities must be unique within a scenario")
    for trigger in triggers:
        for key in ("trigger_id", "trigger_mode", "conditions", "cue_template", "observable_expression"):
            if key not in trigger:
                raise ValueError(f"video trigger missing {key}")
        if trigger["trigger_mode"] not in ("threshold", "crossing", "state_change"):
            raise ValueError("video trigger has unsupported trigger_mode")
        conditions = trigger.get("conditions", {})
        for variable, condition in conditions.items():
            if variable not in values:
                raise ValueError(f"video trigger references unknown variable: {variable}")
            if not isinstance(condition, dict) or condition.get("operator") not in operators:
                raise ValueError(f"invalid condition for video trigger variable {variable}")
            if not isinstance(condition.get("threshold"), (int, float)):
                raise ValueError(f"video trigger threshold must be numeric for {variable}")
        if trigger["trigger_mode"] != "state_change" and conditions and all(
            operators[condition["operator"]](values[variable], condition["threshold"])
            for variable, condition in conditions.items()
        ):
            raise ValueError(f"video trigger {trigger['trigger_id']} is active at S0/D0")
        change_conditions = trigger.get("change_conditions", {})
        if trigger["trigger_mode"] == "state_change" and not change_conditions:
            raise ValueError("state_change trigger requires change_conditions")
        for variable, condition in change_conditions.items():
            if variable not in values:
                raise ValueError(f"video change trigger references unknown variable: {variable}")
            if not isinstance(condition, dict) or condition.get("operator") not in operators:
                raise ValueError(f"invalid change condition for video trigger variable {variable}")
            if not isinstance(condition.get("threshold"), (int, float)):
                raise ValueError(f"video change threshold must be numeric for {variable}")
        if not 2 <= trigger.get("cooldown_turns", 0) <= 4:
            raise ValueError("video trigger cooldown_turns must be in [2, 4]")
        if not isinstance(trigger["observable_expression"], dict) or not trigger["observable_expression"]:
            raise ValueError("video trigger observable_expression must be a non-empty object")



def _flat_numeric_paths(values, prefix=""):
    paths = set()
    for key, value in values.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            paths.update(_flat_numeric_paths(value, path))
        else:
            paths.add(path)
    return paths


def _validate_sparse_effect(effect, allowed_paths, label):
    if not isinstance(effect, dict):
        raise ValueError(f"{label} must be an object")
    unknown = set(effect) - set(allowed_paths)
    if unknown:
        raise ValueError(f"{label} references unknown variables: {sorted(unknown)}")
    invalid = {path: value for path, value in effect.items() if value not in DELTA_LABELS}
    if invalid:
        raise ValueError(f"{label} has invalid semantic deltas: {invalid}")


def _validate_longitudinal_design(scenario):
    design = scenario.get("longitudinal_design")
    if design is None:
        return
    if design.get("format") != "socialflux_longitudinal_v1":
        raise ValueError("longitudinal_design requires socialflux_longitudinal_v1")
    if not str(design.get("time_unit", "")).strip():
        raise ValueError("longitudinal_design requires an explicit time_unit")
    segments = design.get("segments")
    if not isinstance(segments, list) or len(segments) < 2:
        raise ValueError("longitudinal_design requires at least two segments")
    identifiers = [item.get("segment_id") for item in segments]
    if any(not str(item).strip() for item in identifiers) or len(set(identifiers)) != len(identifiers):
        raise ValueError("longitudinal segment IDs must be non-empty and unique")
    state_paths = _flat_numeric_paths(scenario["initial_state"])
    dynamics_paths = _flat_numeric_paths(scenario["initial_dynamics"])
    for index, segment in enumerate(segments):
        minimum = segment.get("min_turns")
        maximum = segment.get("max_turns")
        if not isinstance(minimum, int) or not isinstance(maximum, int) or not 1 <= minimum <= maximum:
            raise ValueError("each longitudinal segment requires 1 <= min_turns <= max_turns")
        if not str(segment.get("reason", "")).strip():
            raise ValueError("each longitudinal segment requires a reason")
        if index:
            for key in ("advance_by", "public_time_record", "opening_response"):
                if not segment.get(key):
                    raise ValueError(f"non-initial longitudinal segment missing {key}")
        time_effect = segment.get("time_effect", {
            "policy": "none", "state_delta": {}, "dynamics_delta": {},
        })
        if time_effect.get("policy") not in ("none", "scenario_authored"):
            raise ValueError("time_effect policy must be none or scenario_authored")
        if time_effect.get("policy") == "none" and (
            time_effect.get("state_delta") or time_effect.get("dynamics_delta")
        ):
            raise ValueError("time-only policy none cannot change state or dynamics")
        _validate_sparse_effect(
            time_effect.get("state_delta", {}), state_paths,
            f"segments[{index}].time_effect.state_delta",
        )
        _validate_sparse_effect(
            time_effect.get("dynamics_delta", {}), dynamics_paths,
            f"segments[{index}].time_effect.dynamics_delta",
        )
    minimum_capacity = sum(item["min_turns"] for item in segments)
    maximum_capacity = sum(item["max_turns"] for item in segments)
    if minimum_capacity > scenario["max_turns"]:
        raise ValueError("longitudinal minimum turns exceed the scenario maximum")
    if maximum_capacity < min(10, scenario["max_turns"]):
        raise ValueError("longitudinal segments do not cover the minimum formal horizon")

    pools = design.get("event_pools", [])
    pool_ids = [pool.get("event_pool_id") for pool in pools]
    if any(not str(item).strip() for item in pool_ids) or len(set(pool_ids)) != len(pool_ids):
        raise ValueError("longitudinal event pool IDs must be non-empty and unique")
    for segment in segments:
        if segment.get("event_pool_id") and segment["event_pool_id"] not in pool_ids:
            raise ValueError("longitudinal segment references an unknown event pool")
    for pool_index, pool in enumerate(pools):
        if pool.get("selection") != "deterministic_by_trajectory_id":
            raise ValueError("event pools must use deterministic_by_trajectory_id")
        outcomes = pool.get("outcomes")
        if not isinstance(outcomes, list) or not outcomes:
            raise ValueError("every event pool requires at least one authored outcome")
        outcome_ids = [item.get("outcome_id") for item in outcomes]
        if any(not str(item).strip() for item in outcome_ids) or len(set(outcome_ids)) != len(outcome_ids):
            raise ValueError("event outcome IDs must be non-empty and unique within a pool")
        for outcome_index, outcome in enumerate(outcomes):
            if not str(outcome.get("public_record", "")).strip():
                raise ValueError("every event outcome requires a public record")
            if outcome.get("causal_scope") not in ("exogenous", "action_mediated"):
                raise ValueError("event outcome requires a valid causal_scope")
            if outcome.get("commitment_effect") not in (
                "none", "fulfilled", "partially_fulfilled", "unfulfilled",
            ):
                raise ValueError("event outcome requires a valid commitment_effect")
            prefix = f"event_pools[{pool_index}].outcomes[{outcome_index}]"
            _validate_sparse_effect(
                outcome.get("state_delta", {}), state_paths,
                f"{prefix}.state_delta",
            )
            _validate_sparse_effect(
                outcome.get("dynamics_delta", {}), dynamics_paths,
                f"{prefix}.dynamics_delta",
            )

def validate_blueprint(blueprint):
    required = (
        "scenario_id",
        "title",
        "mechanism",
        "source",
        "narrative_design",
        "background",
        "environment_agent",
        "evaluated_agent_role",
        "selected_state_variables",
        "target_state_ids",
    )
    missing = [key for key in required if key not in blueprint]
    if missing:
        raise ValueError(f"scenario blueprint missing required fields: {missing}")
    forbidden = {
        "initial_state",
        "initial_dynamics",
        "action_effects",
        "response_templates",
        "observable_cues_by_action",
    } & set(blueprint)
    if forbidden:
        raise ValueError(f"blueprint contains premature state/action fields: {sorted(forbidden)}")
    if blueprint["source"].get("type") not in ("narrative-derived", "synthetic-script"):
        raise ValueError("blueprint requires a supported source type")
    return blueprint


def validate_narrative_structure(structure):
    required = {
        "source_work", "abstract_mechanism", "relationship_structure",
        "power_structure", "goal_conflict", "information_asymmetry",
        "longitudinal_dependency", "adaptation_boundaries",
        "elements_to_discard", "originalization_requirements",
        "redistribution_policy",
    }
    if set(structure) != required:
        raise ValueError("narrative structure fields do not match the schema")
    source = structure["source_work"]
    if (
        not isinstance(source, dict)
        or set(source) != {"title", "medium"}
        or not isinstance(source["title"], str)
        or not source["title"].strip()
        or source["medium"] not in ("film", "television")
    ):
        raise ValueError("narrative source work must provide title and film/television medium")
    for key in (
        "abstract_mechanism", "relationship_structure", "power_structure",
        "goal_conflict", "information_asymmetry",
    ):
        if not isinstance(structure[key], str) or not structure[key].strip():
            raise ValueError(f"narrative structure {key} must be non-empty text")
    for key in ("longitudinal_dependency", "adaptation_boundaries"):
        if (
            not isinstance(structure[key], list)
            or len(structure[key]) < 2
            or not all(isinstance(item, str) and item.strip() for item in structure[key])
        ):
            raise ValueError(f"narrative structure {key} requires at least two text items")
    for key in ("elements_to_discard", "originalization_requirements"):
        if (
            not isinstance(structure[key], list)
            or len(structure[key]) < 4
            or not all(isinstance(item, str) and item.strip() for item in structure[key])
        ):
            raise ValueError(f"narrative structure {key} requires at least four text items")
    if structure["redistribution_policy"] != "structural_abstraction_only_original_surface_text":
        raise ValueError("narrative structure must require original surface text")
    return structure


def validate_instance_quality_judgment(judgment, expected_task_type=None):
    required = {"task_type", "scores", "fatal_issues", "summary", "recommendation"}
    if set(judgment) != required:
        raise ValueError("instance quality judgment fields do not match the schema")
    if expected_task_type and judgment["task_type"] != expected_task_type:
        raise ValueError("instance quality judgment task type mismatch")
    score_keys = {
        "history_dependency", "evidence_sufficiency", "social_plausibility",
        "nontriviality", "answerability",
    }
    if set(judgment["scores"]) != score_keys or not all(
        isinstance(value, int) and 1 <= value <= 5
        for value in judgment["scores"].values()
    ):
        raise ValueError("instance quality judgment requires five integer scores in [1, 5]")
    if not isinstance(judgment["fatal_issues"], list) or not all(
        isinstance(item, str) and item.strip() for item in judgment["fatal_issues"]
    ):
        raise ValueError("instance quality fatal issues must be non-empty strings")
    if not isinstance(judgment["summary"], str) or not judgment["summary"].strip():
        raise ValueError("instance quality judgment summary must be non-empty")
    if judgment["recommendation"] not in ("use", "revise", "reject"):
        raise ValueError("invalid instance quality recommendation")
    return judgment


def validate_quality_report(report):
    required = {"format", "source_type", "checks", "recommendation", "summary", "review_status"}
    if set(report) != required:
        raise ValueError("quality report fields do not match the schema")
    if report["format"] != "socialflux_source_quality_v1":
        raise ValueError("invalid quality report format")
    if report["source_type"] not in ("narrative-derived", "synthetic-script"):
        raise ValueError("invalid quality report source type")
    if set(report["checks"]) != QUALITY_CHECKS:
        raise ValueError("quality report must contain the complete checklist")
    if not all(value in ("pass", "revise", "fail") for value in report["checks"].values()):
        raise ValueError("quality checks must be pass, revise, or fail")
    if report["recommendation"] not in ("pass", "revise", "reject"):
        raise ValueError("invalid quality recommendation")
    if report["review_status"] not in ("pending_human_review", "approved", "rejected"):
        raise ValueError("invalid quality review status")
    if not str(report["summary"]).strip():
        raise ValueError("quality report summary must not be empty")
    return report


def validate_initial_state_proposal(proposal, blueprint):
    required = {
        "initial_state", "initial_dynamics", "observable_expression",
        "media_generation", "video_triggers", "max_turns", "t3_delayed_horizon",
        "sampling_plan", "rationale", "trigger_reachability", "status",
    }
    if set(proposal) != required:
        raise ValueError("initial-state proposal fields do not match the schema")
    if proposal["status"] != "candidate_pending_human_freeze":
        raise ValueError("model initial state must remain a human-review candidate")
    _bounded(proposal["initial_state"], "initial_state")
    _bounded(proposal["initial_dynamics"], "initial_dynamics")
    candidate = dict(blueprint)
    candidate.update({
        key: proposal[key]
        for key in (
            "initial_state", "initial_dynamics", "observable_expression",
            "media_generation", "video_triggers", "max_turns",
            "t3_delayed_horizon", "sampling_plan",
        )
    })
    candidate["construction_status"] = {
        "normalization": "model_normalized_pending_human_review",
        "initial_state": proposal["status"],
        "quality_gate": "approved",
    }
    candidate["quality_gate"] = {key: "pass" for key in QUALITY_CHECKS}
    validate_scenario(candidate)
    values = {}
    def collect(node, prefix=""):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                collect(value, path)
            else:
                values[path] = value
    collect(proposal["initial_state"])
    collect(proposal["initial_dynamics"])
    operators = {
        ">=": lambda value, threshold: value >= threshold,
        ">": lambda value, threshold: value > threshold,
        "<=": lambda value, threshold: value <= threshold,
        "<": lambda value, threshold: value < threshold,
        "==": lambda value, threshold: value == threshold,
    }
    for trigger in proposal["video_triggers"]:
        if trigger.get("trigger_mode") == "state_change":
            continue
        conditions = trigger.get("conditions", {})
        if conditions and all(
            variable in values
            and operators[condition["operator"]](values[variable], condition["threshold"])
            for variable, condition in conditions.items()
        ):
            raise ValueError(f"video trigger {trigger['trigger_id']} is active at S0/D0")
    return proposal


def validate_scenario(scenario):
    required = (
        "scenario_id",
        "title",
        "mechanism",
        "source",
        "narrative_design",
        "construction_status",
        "quality_gate",
        "background",
        "environment_agent",
        "evaluated_agent_role",
        "initial_state",
        "initial_dynamics",
        "max_turns",
    )
    missing = [key for key in required if key not in scenario]
    if missing:
        raise ValueError(f"scenario missing required fields: {missing}")
    forbidden = FORBIDDEN_SCENARIO_FIELDS & set(scenario)
    if forbidden:
        raise ValueError(f"scenario must not define action taxonomy/effects: {sorted(forbidden)}")
    if scenario["source"].get("type") not in ("narrative-derived", "synthetic-script"):
        raise ValueError("scenario source.type must use a supported hybrid source")
    design = scenario["narrative_design"]
    if not isinstance(design, dict):
        raise ValueError("narrative_design must be an object")
    for key in (
        "relationship_structure",
        "power_structure",
        "goal_conflict",
        "information_asymmetry",
    ):
        if not isinstance(design.get(key), str) or not design[key].strip():
            raise ValueError(f"narrative_design.{key} must be non-empty text")
    for key, minimum, maximum in (
        ("relevant_history", 1, 5),
        ("meaningful_choice_space", 3, 8),
    ):
        items = design.get(key)
        if (
            not isinstance(items, list)
            or not minimum <= len(items) <= maximum
            or any(not isinstance(item, str) or not item.strip() for item in items)
        ):
            raise ValueError(
                f"narrative_design.{key} must contain {minimum}-{maximum} "
                "non-empty text items"
            )
    status = scenario["construction_status"]
    if status.get("initial_state") not in ("candidate_pending_human_freeze", "human_frozen"):
        raise ValueError("invalid initial state review status")
    if set(scenario["quality_gate"]) != QUALITY_CHECKS:
        raise ValueError("scenario quality_gate must contain the complete checklist")
    if not all(value in ("pending", "pass", "fail") for value in scenario["quality_gate"].values()):
        raise ValueError("scenario quality checks must be pending/pass/fail")
    agent = scenario["environment_agent"]
    for key in ("persona", "explicit_goal", "hidden_intention"):
        if key not in agent:
            raise ValueError(f"environment_agent missing {key}")
    persona = agent["persona"]
    if not isinstance(persona, dict):
        raise ValueError("environment_agent.persona must be an object")
    for key in ("name", "role"):
        if not isinstance(persona.get(key), str) or not persona[key].strip():
            raise ValueError(f"environment_agent.persona missing text {key}")
    evaluated = scenario["evaluated_agent_role"]
    for key in ("character_id", "name", "role", "explicit_goal"):
        if not str(evaluated.get(key, "")).strip():
            raise ValueError(f"evaluated_agent_role missing {key}")
    _bounded(scenario["initial_state"], "initial_state")
    _bounded(scenario["initial_dynamics"], "initial_dynamics")
    if scenario["max_turns"] != 20:
        raise ValueError("canonical scenario max_turns must be exactly 20")
    horizon = scenario.get("t3_delayed_horizon", 5)
    if not isinstance(horizon, int) or not 5 <= horizon <= 10:
        raise ValueError("t3_delayed_horizon must be between 5 and 10")
    _validate_longitudinal_design(scenario)
    _validate_multimodal(scenario)
    return scenario


def validate_trajectory(trajectory):
    required = (
        "trajectory_id",
        "scenario_id",
        "policy_id",
        "policy_provenance",
        "environment_provenance",
        "initial_state",
        "initial_dynamics",
        "turns",
        "ending",
    )
    missing = [key for key in required if key not in trajectory]
    if missing:
        raise ValueError(f"trajectory missing required fields: {missing}")
    if not trajectory["turns"]:
        raise ValueError("trajectory must contain at least one turn")
    for turn in trajectory["turns"]:
        action = turn.get("policy_action")
        if not isinstance(action, dict) or not str(action.get("text", "")).strip():
            raise ValueError("every policy action must be non-empty free-form text")
        if "action_id" in action:
            raise ValueError("free-form trajectories must not contain action_id taxonomy")
    if trajectory.get("longitudinal_design_version"):
        if trajectory["longitudinal_design_version"] != "socialflux_longitudinal_v1":
            raise ValueError("unsupported longitudinal trajectory version")
        timeline = trajectory.get("public_timeline")
        if not isinstance(timeline, list):
            raise ValueError("longitudinal trajectory requires a public timeline")
        timeline_ids = {item.get("event_id") for item in timeline}
        previous_elapsed = 0
        for turn in trajectory["turns"]:
            if not str(turn.get("segment_id", "")).strip():
                raise ValueError("longitudinal turn requires a segment_id")
            before = turn.get("elapsed_time_before")
            after = turn.get("elapsed_time_after")
            if not isinstance(before, int) or not isinstance(after, int):
                raise ValueError("longitudinal turn requires integer elapsed time")
            if before < previous_elapsed or after < before:
                raise ValueError("longitudinal elapsed time must be monotonic")
            previous_elapsed = after
            transition = turn.get("segment_transition_after") or {}
            event_ids = {
                event.get("event_id")
                for event in transition.get("public_events", [])
            }
            if not event_ids.issubset(timeline_ids):
                raise ValueError(
                    "turn references a public event absent from trajectory timeline"
                )
    return trajectory


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
