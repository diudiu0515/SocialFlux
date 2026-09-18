"""Conservative schema-only normalization for structured appraisal outputs."""

from __future__ import annotations

from copy import deepcopy


def canonicalize_social_act(value, allowed):
    """Map harmless label variation without inventing a stronger speech act."""
    label = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "accept": "concession",
        "acceptance": "concession",
        "agreement": "concession",
        "acknowledgement": "inform",
        "acknowledgment": "inform",
        "answer": "inform",
        "statement": "inform",
    }
    label = aliases.get(label, label)
    return label if label in set(allowed) else "other"


def canonicalize_event_features(features, feature_names):
    """Fill omitted fixed features with neutral zero and ignore unknown extras."""
    if not isinstance(features, dict):
        return features
    return {
        name: features.get(name, 0)
        for name in feature_names
    }


def _resolve_variable(variable, state_variables, dynamics_variables):
    value = str(variable).strip()
    all_variables = set(state_variables) | set(dynamics_variables)
    if value in all_variables:
        return value
    matches = [item for item in all_variables if item.rsplit(".", 1)[-1] == value]
    return matches[0] if len(matches) == 1 else None


def canonicalize_impact_lists(appraisal, state_variables, dynamics_variables):
    """Normalize equivalent paths and conservatively suppress unusable impacts.

    Unknown, malformed, or contradictory duplicate impacts are dropped, which
    yields persistence rather than fabricated state meaning.
    """
    normalized = deepcopy(appraisal)
    state_variables = set(state_variables)
    dynamics_variables = set(dynamics_variables)
    required = {
        "variable", "direction", "evidence_strength",
        "directness", "new_evidence",
    }
    collected = {"state": {}, "dynamics": {}}
    conflicts = {"state": set(), "dynamics": set()}
    for source in ("state_impacts", "dynamics_impacts"):
        raw_impacts = normalized.get(source, [])
        if not isinstance(raw_impacts, list):
            continue
        for raw in raw_impacts:
            if not isinstance(raw, dict):
                continue
            impact = dict(raw)
            if "variable" not in impact and "variable_path" in impact:
                impact["variable"] = impact.pop("variable_path")
            if "new_evidence" not in impact:
                impact["new_evidence"] = True
            if "evidence_feature" not in impact and "citing_feature" in impact:
                impact["evidence_feature"] = impact.pop("citing_feature")
            if not required.issubset(impact):
                continue
            impact = {key: impact[key] for key in required}
            variable = _resolve_variable(
                impact.get("variable", ""), state_variables, dynamics_variables
            )
            if variable is None:
                continue
            impact["variable"] = variable
            group = "dynamics" if variable in dynamics_variables else "state"
            if variable in conflicts[group]:
                continue
            previous = collected[group].get(variable)
            if previous is None:
                collected[group][variable] = impact
            elif previous != impact:
                collected[group].pop(variable, None)
                conflicts[group].add(variable)
    normalized["state_impacts"] = [
        collected["state"][key] for key in sorted(collected["state"])
    ]
    normalized["dynamics_impacts"] = [
        collected["dynamics"][key] for key in sorted(collected["dynamics"])
    ]
    return normalized
