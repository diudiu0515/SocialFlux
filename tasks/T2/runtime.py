"""Stable runtime services shared by the canonical T2 builders.

This module owns T2 file I/O, formal environment construction, public turn
projection, and deterministic state comparison. Command-line scripts may call
these services but must not define their own production semantics.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from environment.delta_mapper import flatten_state
from environment.factory import ModelEnvironmentFactory


ROOT = Path(__file__).resolve().parents[2]
DIRECTIONS = ("higher_in_a", "similar", "higher_in_b", "cannot_determine")
APPRAISAL_PROMPT_ID = "environment_appraisal_v11"
RESPONSE_PROMPT_ID = "environment_response_v25"
RESPONSE_VALIDATION_PROFILE = "hard_only"
HORIZON_MODE = "natural_max_20"


def now():
    return datetime.now(timezone.utc).isoformat()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def scenario_path(ordinal):
    name = f"scenario_{ordinal:03d}"
    return ROOT / "configs" / "scale300_v1" / "scenarios" / name / f"{name}.json"


def environment_for(
    scenario,
    appraisal_provider_config,
    response_provider_config,
    seed,
):
    factory = ModelEnvironmentFactory(
        scenario,
        deepcopy(appraisal_provider_config),
        {"temperature": 0.2, "top_p": 0.9, "seed": seed},
        response_provider_config=deepcopy(response_provider_config),
        response_sampling={
            "temperature": 0.35,
            "top_p": 0.9,
            "seed": seed + 1000,
        },
        appraisal_prompt_id=APPRAISAL_PROMPT_ID,
        response_prompt_id=RESPONSE_PROMPT_ID,
        response_validation_profile=RESPONSE_VALIDATION_PROFILE,
        horizon_mode=HORIZON_MODE,
    )
    return factory()


def public_events(log):
    transition = log.get("segment_transition_after") or {}
    return deepcopy(transition.get("public_events", []))


def public_turn(log):
    return {
        "turn_id": log["turn_id"],
        "evaluated_agent": log["policy_action"]["text"],
        "environment_character": log["environment_response"],
        "observable_expression": deepcopy(log.get("observable_expression", {})),
        "media": deepcopy(log.get("media", [])),
        "public_events_after": public_events(log),
    }


def flat_private(log):
    values = flatten_state(log["state_after"])
    values.update(flatten_state(log["dynamics_after"]))
    return values


def selected_state_ids(scenario):
    selected = scenario.get("selected_state_variables", {})
    state_ids = []
    groups = (
        ("emotion", "behavioral_disposition", "relationship", "consequence_risk")
        if scenario.get("state_contract_version") == "socialflux_state_v2"
        else ("emotion", "motivation", "relationship")
    )
    for group in groups:
        state_ids.extend(f"{group}.{name}" for name in selected.get(group, []))
    if scenario.get("state_contract_version") != "socialflux_state_v2":
        state_ids.extend(selected.get("dynamics", []))
        state_ids.extend(selected.get("risk", []))
    return list(dict.fromkeys(state_ids))


def target_preference_ids(scenario):
    available = set(selected_state_ids(scenario))
    preferred = []
    for state_id in scenario.get("target_state_ids", []):
        candidates = [state_id]
        if state_id.startswith("risk."):
            candidates.append(state_id.split(".", 1)[1])
        for candidate in candidates:
            if candidate in available and candidate not in preferred:
                preferred.append(candidate)
    return preferred


def supported_t2_candidates(scenario, state_a, state_b):
    changed = [
        state_id
        for state_id in selected_state_ids(scenario)
        if state_a.get(state_id) is not None
        and state_b.get(state_id) is not None
        and state_a[state_id] != state_b[state_id]
    ]
    preferred = [
        state_id
        for state_id in target_preference_ids(scenario)
        if state_id in changed
    ]
    return preferred or changed


def internal_direction(state_a, state_b, state_id):
    left = state_a.get(state_id)
    right = state_b.get(state_id)
    if left is None or right is None:
        return "unavailable"
    if left > right:
        return "higher_in_a"
    if left < right:
        return "higher_in_b"
    return "similar"


def call_count(provider):
    return int(getattr(provider, "_call_index", 0) or 0)


def environment_call_counts(environment):
    return {
        "appraisal": call_count(environment.state_updater.provider),
        "response": call_count(environment.response_generator.provider),
    }
