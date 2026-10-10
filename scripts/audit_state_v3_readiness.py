#!/usr/bin/env python3
"""Audit scenario populations against State Transition Standard v3."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from environment.state_ontology import (
    FAMILY_RULES,
    STATE_ONTOLOGY_VERSION,
    VARIABLE_RULES,
)


FAMILY_RANGES = {
    "emotion": (3, 4),
    "behavioral_disposition": (2, 3),
    "relationship": (2, 3),
    "consequence_risk": (2, 3),
}


def tokens(value):
    text = json.dumps(value, ensure_ascii=False).lower()
    return {
        token
        for token in re.findall(r"[a-z][a-z_'-]{3,}", text)
        if token not in {
            "with", "from", "that", "this", "their", "while", "because",
            "current", "state", "role", "will", "without", "through",
        }
    }


def flatten_rationale(rationale, selected):
    result = {}
    for family, variables in selected.items():
        family_value = rationale.get(family)
        for variable in variables:
            path = f"{family}.{variable}"
            value = None
            if isinstance(family_value, dict):
                value = family_value.get(variable)
            elif isinstance(family_value, str):
                value = family_value
            if value is None:
                value = rationale.get(path)
            result[path] = value
    return result


def trigger_paths(scenario):
    result = set()
    for trigger in scenario.get("video_triggers", []):
        result.update((trigger.get("conditions") or {}).keys())
        result.update((trigger.get("change_conditions") or {}).keys())
    return result


def audit_population(label, root):
    files = sorted(Path(root).glob("scenario_*/scenario_*.json"))
    issues = []
    selected_counts = Counter()
    target_counts = Counter()
    family_shape_counts = Counter()
    boundary_values = 0
    value_count = 0
    suspected_actor_mismatch = 0

    for path in files:
        scenario = json.loads(path.read_text(encoding="utf-8"))
        scenario_id = scenario.get("scenario_id")
        selected = scenario.get("selected_state_variables") or {}
        targets = scenario.get("target_state_ids") or []
        initial = scenario.get("initial_state") or {}
        item_issues = []

        if set(selected) != set(FAMILY_RANGES):
            item_issues.append("missing_or_extra_state_family")
        counts = {
            family: len(selected.get(family, []))
            for family in FAMILY_RANGES
        }
        family_shape_counts[tuple(counts.values())] += 1
        for family, (minimum, maximum) in FAMILY_RANGES.items():
            if not minimum <= counts[family] <= maximum:
                item_issues.append(
                    f"{family}_count_{counts[family]}_outside_{minimum}_{maximum}"
                )
        total = sum(counts.values())
        if not 9 <= total <= 13:
            item_issues.append(f"total_state_count_{total}_outside_9_13")

        selected_paths = {
            f"{family}.{variable}"
            for family, variables in selected.items()
            for variable in variables
        }
        for state_path in selected_paths:
            selected_counts[state_path] += 1
        for state_path in targets:
            target_counts[state_path] += 1
        if not set(targets).issubset(selected_paths):
            item_issues.append("target_not_selected")
        if {x.split(".", 1)[0] for x in targets} != set(FAMILY_RANGES):
            item_issues.append("targets_do_not_cover_four_families")
        if not 6 <= len(targets) <= 9:
            item_issues.append(f"target_count_{len(targets)}_outside_6_9")

        values = []
        shape_ok = set(initial) == set(selected)
        for family, variables in selected.items():
            if set((initial.get(family) or {})) != set(variables):
                shape_ok = False
            for variable in variables:
                value = (initial.get(family) or {}).get(variable)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    values.append(value)
                    value_count += 1
                    boundary_values += value in (0, 10)
        if not shape_ok:
            item_issues.append("s0_shape_mismatch")
        if any(not 1 <= value <= 9 for value in values):
            item_issues.append("s0_contains_boundary_or_out_of_v3_range")
        if len(set(values)) < 4:
            item_issues.append("s0_has_fewer_than_four_distinct_levels")

        rationale = (
            (scenario.get("initialization_notes") or {}).get("rationale") or {}
        )
        state_rationale = flatten_rationale(rationale, selected)
        if any(
            not isinstance(text, str) or not text.strip()
            for text in state_rationale.values()
        ):
            item_issues.append("missing_variable_specific_rationale")

        env = scenario.get("environment_agent", {})
        evaluated = scenario.get("evaluated_agent_role", {})
        env_tokens = tokens(env.get("persona", {}))
        evaluated_tokens = tokens(evaluated.get("persona", {}))
        rationale_tokens = tokens(state_rationale)
        env_overlap = len(rationale_tokens & env_tokens)
        evaluated_overlap = len(rationale_tokens & evaluated_tokens)
        env_name = str((env.get("persona") or {}).get("name", "")).strip()
        evaluated_name = str(evaluated.get("name", "")).strip()
        rationale_text = json.dumps(state_rationale, ensure_ascii=False)
        rationale_text_folded = rationale_text.casefold()
        env_named = bool(
            env_name and env_name.casefold() in rationale_text_folded
        )
        evaluated_named = bool(
            evaluated_name
            and evaluated_name.casefold() in rationale_text_folded
        )
        actor_suspect = (
            evaluated_named and not env_named
        ) or (
            not env_named
            and not evaluated_named
            and evaluated_overlap >= env_overlap + 3
        )
        if actor_suspect:
            item_issues.append("actor_ownership_review_required")
            suspected_actor_mismatch += 1

        relationships = selected.get("relationship", [])
        timescales = {
            VARIABLE_RULES.get(f"relationship.{variable}", {}).get(
                "timescale", FAMILY_RULES["relationship"]["timescale"]
            )
            for variable in relationships
        }
        if "turn_to_episode" not in timescales:
            item_issues.append("no_turn_responsive_relationship_state")
        if "cross_turn_slow" not in timescales:
            item_issues.append("no_slow_relationship_state")

        referenced = trigger_paths(scenario)
        allowed_trigger_paths = selected_paths | set(
            (scenario.get("initial_dynamics") or {}).keys()
        )
        if not referenced.issubset(allowed_trigger_paths):
            item_issues.append("trigger_references_unknown_state")

        if item_issues:
            issues.append({
                "scenario_id": scenario_id,
                "path": str(path),
                "state_counts": counts,
                "total_state_count": total,
                "issues": item_issues,
                "actor_overlap": {
                    "environment_persona": env_overlap,
                    "evaluated_persona": evaluated_overlap,
                },
            })

    return {
        "label": label,
        "scenario_root": str(root),
        "scenario_count": len(files),
        "state_ontology_target": STATE_ONTOLOGY_VERSION,
        "scenarios_with_issues": len(issues),
        "suspected_actor_ownership_mismatches": suspected_actor_mismatch,
        "s0_boundary_values": boundary_values,
        "s0_value_count": value_count,
        "family_shape_counts": {
            "/".join(map(str, key)): count
            for key, count in sorted(family_shape_counts.items())
        },
        "selected_variable_counts": dict(selected_counts.most_common()),
        "target_variable_counts": dict(target_counts.most_common()),
        "issues": issues,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpt", type=Path, required=True)
    parser.add_argument("--claude", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = {
        "format": "socialflux_state_v3_readiness_audit_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "standard": "docs/protocols/STATE_TRANSITION_STANDARD_V3.md",
        "populations": [
            audit_population("gpt50", args.gpt),
            audit_population("claude150", args.claude),
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        item["label"]: {
            "scenarios": item["scenario_count"],
            "with_issues": item["scenarios_with_issues"],
            "actor_review": item["suspected_actor_ownership_mismatches"],
            "boundary_values": item["s0_boundary_values"],
        }
        for item in value["populations"]
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
