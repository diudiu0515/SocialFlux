"""Deterministic calibration from structured social impacts to state deltas."""

from __future__ import annotations

from copy import deepcopy
from math import ceil

from .delta_mapper import DELTA_TO_INT, flatten_state
from .state_ontology import (
    EVIDENCE_FEATURE_COMPATIBILITY,
    EVIDENCE_FEATURE_DIRECTION_RULES,
    FAMILY_RULES,
    VARIABLE_RULES,
    build_state_semantics,
)


CALIBRATOR_ID = "deterministic_social_delta_calibrator_v1"
EVIDENCE_BALANCED_CALIBRATOR_ID = (
    "deterministic_social_delta_calibrator_evidence_balanced_v2"
)
EVIDENCE_BOUND_SPARSE_CALIBRATOR_ID = (
    "deterministic_social_delta_calibrator_evidence_bound_sparse_v2"
)
EVIDENCE_INDEPENDENT_HYSTERETIC_CALIBRATOR_ID = (
    "deterministic_social_delta_calibrator_evidence_independent_hysteretic_v3"
)
EVIDENCE_INDEPENDENT_DIRECTIONAL_HYSTERETIC_CALIBRATOR_ID = (
    "deterministic_social_delta_calibrator_evidence_independent_directional_hysteretic_v4"
)
EVIDENCE_CAUSAL_HYSTERETIC_CALIBRATOR_ID = (
    "deterministic_social_delta_calibrator_evidence_causal_hysteretic_v5"
)
EVIDENCE_CAUSAL_SLOW_PRIORITY_HYSTERETIC_CALIBRATOR_ID = (
    "deterministic_social_delta_calibrator_evidence_causal_slow_priority_hysteretic_v6"
)
STATE_JUDGMENT_PRIMARY_HYSTERETIC_CALIBRATOR_ID = (
    "deterministic_social_delta_calibrator_state_judgment_primary_hysteretic_v7"
)

CALIBRATION_PROFILES = {
    "sparse_v1": {
        "calibrator_id": CALIBRATOR_ID,
        "ordinary_budget": 1,
        "strong_extra_budget": 1,
        "dimension_caps": None,
        "require_independent_evidence": False,
        "slow_dimensions": (),
        "strong_event_rule": "calibrated_level_3",
    },
    "evidence_balanced_v2": {
        "calibrator_id": EVIDENCE_BALANCED_CALIBRATOR_ID,
        "ordinary_budget": 2,
        "strong_extra_budget": 1,
        "dimension_caps": {
            "emotion": 2,
            "behavioral_disposition": 1,
            "relationship": 1,
            "consequence_risk": 1,
        },
        "require_independent_evidence": True,
        "slow_dimensions": ("relationship", "consequence_risk"),
        "strong_event_rule": "direct_evidence_strength_2",
    },
    "evidence_bound_sparse_v2": {
        "calibrator_id": EVIDENCE_BOUND_SPARSE_CALIBRATOR_ID,
        "ordinary_budget": 1,
        "strong_extra_budget": 1,
        "dimension_caps": {
            "emotion": 2,
            "behavioral_disposition": 1,
            "relationship": 1,
            "consequence_risk": 1,
        },
        "require_independent_evidence": True,
        "slow_dimensions": ("relationship", "consequence_risk"),
        "strong_event_rule": "direct_evidence_strength_2",
    },
    "evidence_independent_hysteretic_v3": {
        "calibrator_id": EVIDENCE_INDEPENDENT_HYSTERETIC_CALIBRATOR_ID,
        "ordinary_budget": 2,
        "strong_extra_budget": 1,
        "dimension_caps": {
            "emotion": 1,
            "behavioral_disposition": 1,
            "relationship": 1,
            "consequence_risk": 1,
        },
        "require_independent_evidence": True,
        "slow_dimensions": (),
        "strong_event_rule": "decisive_evidence",
        "enforce_feature_compatibility": True,
        "use_variable_timescales": True,
        "anti_convergence": True,
    },
    "evidence_independent_directional_hysteretic_v4": {
        "calibrator_id": EVIDENCE_INDEPENDENT_DIRECTIONAL_HYSTERETIC_CALIBRATOR_ID,
        "ordinary_budget": 2,
        "strong_extra_budget": 1,
        "dimension_caps": {
            "emotion": 1,
            "behavioral_disposition": 1,
            "relationship": 1,
            "consequence_risk": 1,
        },
        "require_independent_evidence": True,
        "slow_dimensions": (),
        "strong_event_rule": "decisive_evidence",
        "enforce_feature_compatibility": True,
        "enforce_feature_direction_compatibility": True,
        "use_variable_timescales": True,
        "anti_convergence": True,
    },
    "evidence_causal_hysteretic_v5": {
        "calibrator_id": EVIDENCE_CAUSAL_HYSTERETIC_CALIBRATOR_ID,
        "ordinary_budget": 2,
        "strong_extra_budget": 1,
        "dimension_caps": {
            "emotion": 1,
            "behavioral_disposition": 1,
            "relationship": 1,
            "consequence_risk": 1,
        },
        "require_independent_evidence": True,
        "allow_shared_evidence_across_distinct_variables": True,
        "slow_dimensions": (),
        "strong_event_rule": "decisive_evidence",
        "enforce_feature_compatibility": True,
        "use_variable_timescales": True,
        "anti_convergence": True,
    },
    "evidence_causal_slow_priority_hysteretic_v6": {
        "calibrator_id": EVIDENCE_CAUSAL_SLOW_PRIORITY_HYSTERETIC_CALIBRATOR_ID,
        "ordinary_budget": 2,
        "strong_extra_budget": 1,
        "dimension_caps": {
            "emotion": 1,
            "behavioral_disposition": 1,
            "relationship": 1,
            "consequence_risk": 1,
        },
        "require_independent_evidence": True,
        "allow_shared_evidence_across_distinct_variables": True,
        "slow_dimensions": (),
        "strong_event_rule": "decisive_evidence",
        "enforce_feature_compatibility": True,
        "use_variable_timescales": True,
        "anti_convergence": True,
        "prefer_decisive_slow_on_tie": True,
    },
    "state_judgment_primary_hysteretic_v7": {
        "calibrator_id": STATE_JUDGMENT_PRIMARY_HYSTERETIC_CALIBRATOR_ID,
        # The numeric budget remains logged for compatibility, but this profile
        # treats per-variable semantic judgments as authoritative: every valid
        # new-evidence judgment updates. Candidate count is controlled by the
        # appraisal contract rather than by evidence strength.
        "ordinary_budget": 3,
        "strong_extra_budget": 0,
        "dimension_caps": {
            "emotion": 1,
            "behavioral_disposition": 1,
            "relationship": 1,
            "consequence_risk": 1,
        },
        "require_independent_evidence": True,
        "allow_shared_evidence_across_distinct_variables": True,
        "slow_dimensions": (),
        "strong_event_rule": "decisive_evidence",
        "enforce_feature_compatibility": False,
        "use_variable_timescales": True,
        "anti_convergence": False,
        "prefer_decisive_slow_on_tie": True,
        "feature_is_auxiliary": True,
        "decisive_evidence_rule": "state_judgment",
        "enforce_dialogue_diagnostics_gate": False,
        "consume_slow_evidence_on_update": True,
        "slow_evidence_identity": "turn_event_id",
        "new_evidence_updates_immediately": True,
        "minimum_new_evidence_level": 1,
        "all_eligible_new_evidence_updates": True,
    },
}

FEATURE_NAMES = (
    "goal_alignment",
    "cooperation_signal",
    "repair_signal",
    "pressure",
    "face_threat",
    "commitment_signal",
    "uncertainty_reduction",
    "boundary_violation",
    "respect_signal",
    "withdrawal_signal",
)


def immediate_update_contract():
    """Describe the active v7 policy from the same configuration Python uses."""
    profile = CALIBRATION_PROFILES["state_judgment_primary_hysteretic_v7"]
    if not (profile["new_evidence_updates_immediately"]
            and profile["all_eligible_new_evidence_updates"]
            and profile["feature_is_auxiliary"]
            and not profile["enforce_dialogue_diagnostics_gate"]):
        raise ValueError("immediate appraisal prompt requires the immediate v7 policy")
    return {
        "source": "CALIBRATION_PROFILES.state_judgment_primary_hysteretic_v7",
        "rule": (
            "Every valid ordinary or decisive NEW variable-specific evidence judgment "
            f"receives at least {profile['minimum_new_evidence_level']} directional point(s), "
            "subject only to numeric bounds and event replay protection. "
            "Strength determines magnitude, never eligibility. No evidence and repeated "
            "evidence leave the variable unchanged. Features and dialogue diagnostics "
            "are auxiliary; timescale describes the construct, not an accumulation gate. "
            "Evidence is repeated when already present in history without a new "
            "variable-specific consequence, regardless of past numeric updates."
        ),
    }

_FEATURE_SENSITIVITY = {
    "goal_alignment": ("achievement_drive", "duty_orientation", "practicality"),
    "cooperation_signal": ("empathy", "patience", "strategic_patience"),
    "repair_signal": ("empathy", "hurt_sensitivity", "mentoring_attachment"),
    "pressure": ("threat_sensitivity", "authority_orientation", "fatigue_sensitivity"),
    "face_threat": ("face_sensitivity", "status_sensitivity", "recognition_need"),
    "commitment_signal": ("duty_orientation", "loyalty", "procedural_loyalty"),
    "uncertainty_reduction": ("certainty_need", "uncertainty_aversion", "precision"),
    "boundary_violation": ("threat_sensitivity", "procedural_loyalty", "discipline"),
    "respect_signal": ("recognition_need", "status_sensitivity", "fairness"),
    "withdrawal_signal": ("hurt_sensitivity", "attachment_avoidance", "emotion_protection"),
}


def _empty_delta(values):
    return {
        key: _empty_delta(value) if isinstance(value, dict) else "similar"
        for key, value in values.items()
    }


def _set_path(values, path, value):
    parts = path.split(".")
    cursor = values
    for part in parts[:-1]:
        cursor = cursor[part]
    cursor[parts[-1]] = value


def _persona_sensitivity(persona, feature):
    values = [
        persona[key]
        for key in _FEATURE_SENSITIVITY.get(feature, ())
        if isinstance(persona.get(key), (int, float))
        and not isinstance(persona.get(key), bool)
    ]
    return sum(values) / len(values) if values else 0.5


def _calibrated_level(
    impact, feature_value, sensitivity, *, feature_is_auxiliary=False,
):
    """Return a deterministic 0–3 magnitude with persistence as the default."""
    if not impact["new_evidence"] or (
        feature_value == 0 and not feature_is_auxiliary
    ):
        return 0
    level = impact["evidence_strength"]
    if isinstance(level, bool) or not isinstance(level, int) or level not in {1, 2}:
        raise ValueError("evidence_strength must be an integer in {1, 2}")
    if impact["directness"] == "indirect":
        level -= 1
    if feature_is_auxiliary:
        return max(0, min(2, level))
    if level >= 2 and abs(feature_value) == 2 and sensitivity >= 0.80:
        level = 3
    elif level >= 2:
        level = 2
    elif level >= 1:
        level = 1
    if sensitivity <= 0.20 and level > 1:
        level -= 1
    return max(0, min(3, level))


def _feature_direction_compatible(variable, direction, feature_name, feature_value):
    rules = EVIDENCE_FEATURE_DIRECTION_RULES.get(variable)
    if not rules:
        return True
    expected_sign = (rules.get(direction) or {}).get(feature_name)
    if expected_sign == "positive":
        return feature_value > 0
    if expected_sign == "negative":
        return feature_value < 0
    return False


def _label(direction, level):
    if level == 0:
        return "similar"
    prefix = {1: "mild", 2: "moderate", 3: "strong"}[level]
    return f"{prefix}_{direction}"


def _ranked_impacts(
    impacts,
    features,
    persona,
    *,
    ordinary_budget,
    strong_extra_budget=0,
    dimension_caps=None,
    require_independent_evidence=False,
    slow_dimensions=(),
    strong_event_rule="calibrated_level_3",
    current_values=None,
    initial_values=None,
    enforce_feature_compatibility=False,
    enforce_feature_direction_compatibility=False,
    use_variable_timescales=False,
    anti_convergence=False,
    semantic_novelty=None,
    slow_evidence_counts=None,
    allow_shared_evidence_across_distinct_variables=False,
    prefer_decisive_slow_on_tie=False,
    feature_is_auxiliary=False,
    decisive_evidence_rule="legacy_dialogue_feature",
    variable_timescales=None,
    new_evidence_updates_immediately=False,
    minimum_new_evidence_level=0,
    all_eligible_new_evidence_updates=False,
):
    candidates = []
    for source_index, impact in enumerate(impacts):
        feature_name = impact.get("evidence_feature")
        feature_inferred = feature_name not in features
        if feature_name not in features and not feature_is_auxiliary:
            feature_name = max(
                features, key=lambda key: abs(features[key]), default=None
            )
        feature_value = features.get(feature_name, 0)
        sensitivity = _persona_sensitivity(persona, feature_name)
        level = _calibrated_level(
            impact,
            feature_value,
            sensitivity,
            feature_is_auxiliary=feature_is_auxiliary,
        )
        if (
            new_evidence_updates_immediately
            and impact.get("new_evidence")
            and level < minimum_new_evidence_level
        ):
            level = minimum_new_evidence_level
        variable = impact["variable"]
        dimension = variable.split(".", 1)[0]
        current = (current_values or {}).get(variable)
        initial = (initial_values or {}).get(variable)
        cumulative_evidence = (
            isinstance(current, (int, float))
            and not isinstance(current, bool)
            and isinstance(initial, (int, float))
            and not isinstance(initial, bool)
            and (
                (impact["direction"] == "increase" and current > initial)
                or (impact["direction"] == "decrease" and current < initial)
            )
        )
        raw_evidence_span = impact.get("evidence_span", "")
        evidence_span = (
            raw_evidence_span.strip()
            if isinstance(raw_evidence_span, str) else ""
        )
        explicit_evidence = bool(evidence_span) and (
            feature_is_auxiliary
            or (feature_name in features and not feature_inferred)
        )
        compatible_features = EVIDENCE_FEATURE_COMPATIBILITY.get(variable, set())
        feature_compatible = (
            feature_name in compatible_features
            if compatible_features else not enforce_feature_compatibility
        )
        feature_direction_compatible = (
            _feature_direction_compatible(
                variable,
                impact["direction"],
                feature_name,
                feature_value,
            )
            if enforce_feature_direction_compatibility
            else True
        )
        family_timescale = FAMILY_RULES.get(dimension, {}).get("timescale")
        timescale = (variable_timescales or {}).get(
            variable,
            VARIABLE_RULES.get(variable, {}).get(
                "timescale", family_timescale
            ),
        )
        if decisive_evidence_rule == "state_judgment":
            decisive_evidence = (
                explicit_evidence
                and impact["evidence_strength"] == 2
                and impact["directness"] == "direct"
            )
        elif decisive_evidence_rule == "legacy_dialogue_feature":
            decisive_evidence = (
                explicit_evidence
                and impact["evidence_strength"] == 2
                and impact["directness"] == "direct"
                and abs(feature_value) == 2
                and semantic_novelty in {
                    "new_position", "new_tradeoff", "new_evidence", "new_decision",
                }
            )
        else:
            raise ValueError(
                f"unsupported decisive evidence rule {decisive_evidence_rule!r}"
            )
        prior_consistent_evidence = (slow_evidence_counts or {}).get(
            (variable, impact["direction"]), 0
        )
        candidates.append({
            **deepcopy(impact),
            "source_index": source_index,
            "evidence_feature": feature_name,
            "feature_inferred": feature_inferred,
            "feature_value": feature_value,
            "persona_sensitivity": round(sensitivity, 4),
            "calibrated_level": level,
            "dimension": dimension,
            "cumulative_evidence": cumulative_evidence,
            "explicit_evidence": explicit_evidence,
            "feature_compatible": feature_compatible,
            "feature_direction_compatible": feature_direction_compatible,
            "feature_role": (
                "auxiliary_diagnostic"
                if feature_is_auxiliary else "eligibility_and_magnitude"
            ),
            "timescale": timescale,
            "decisive_evidence": decisive_evidence,
            "prior_consistent_evidence": prior_consistent_evidence,
        })

    # Qualification is deliberately complete before ranking or budget selection.
    # Thus an invalid high-scoring candidate cannot occupy a slot or grant the
    # strong-event extra budget.
    for item in candidates:
        reasons = []
        current = (current_values or {}).get(item["variable"])
        if item["calibrated_level"] <= 0:
            reasons.append("no_calibrated_change")
        elif (
            isinstance(current, (int, float))
            and not isinstance(current, bool)
            and (
                (item["direction"] == "increase" and current >= 10)
                or (item["direction"] == "decrease" and current <= 0)
            )
        ):
            reasons.append("state_boundary_noop")
        elif require_independent_evidence and not item["explicit_evidence"]:
            reasons.append("missing_explicit_evidence")
        elif enforce_feature_compatibility and not item["feature_compatible"]:
            reasons.append("feature_variable_mismatch")
        elif (
            enforce_feature_direction_compatibility
            and not item["feature_direction_compatible"]
        ):
            reasons.append("feature_direction_mismatch")
        elif (
            use_variable_timescales
            and not new_evidence_updates_immediately
            and item["timescale"] == "cross_turn_slow"
            and not item["decisive_evidence"]
            and item["prior_consistent_evidence"] < 1
        ):
            reasons.append(
                "slow_variable_requires_decisive_or_two_independent_events"
            )
        elif (
            item["dimension"] in set(slow_dimensions)
            and not (
                item["evidence_strength"] == 2
                and item["directness"] == "direct"
            )
            and not item["cumulative_evidence"]
        ):
            reasons.append("slow_dimension_requires_strong_or_cumulative_evidence")
        elif (
            anti_convergence
            and isinstance(current, (int, float))
            and not isinstance(current, bool)
            and isinstance((initial_values or {}).get(item["variable"]), (int, float))
            and not isinstance((initial_values or {}).get(item["variable"]), bool)
            and not item["decisive_evidence"]
            and (
                (
                    item["direction"] == "increase"
                    and (
                        current >= 8
                        or current - (initial_values or {})[item["variable"]] >= 2
                    )
                )
                or (
                    item["direction"] == "decrease"
                    and (
                        current <= 2
                        or (initial_values or {})[item["variable"]] - current >= 2
                    )
                )
            )
        ):
            reasons.append("reinforcement_plateau_requires_decisive_evidence")
        item["eligibility_status"] = "ineligible" if reasons else "eligible"
        item["eligibility_reasons"] = reasons

    candidates.sort(
        key=lambda item: (
            item["eligibility_status"] != "eligible",
            -int(
                prefer_decisive_slow_on_tie
                and item["timescale"] == "cross_turn_slow"
                and item["decisive_evidence"]
            ),
            -item["calibrated_level"],
            (
                0 if feature_is_auxiliary else -abs(item["feature_value"])
            ),
            item["source_index"],
        )
    )
    eligible = [
        item for item in candidates if item["eligibility_status"] == "eligible"
    ]
    if strong_event_rule == "direct_evidence_strength_2":
        strong_event = any(
            item["evidence_strength"] == 2
            and item["directness"] == "direct"
            and item["new_evidence"]
            and item["feature_value"] != 0
            and (item["explicit_evidence"] or not require_independent_evidence)
            for item in eligible
        )
    elif strong_event_rule == "calibrated_level_3":
        strong_event = any(
            item["calibrated_level"] == 3 and not item["feature_inferred"]
            for item in eligible
        )
    elif strong_event_rule == "decisive_evidence":
        strong_event = any(item["decisive_evidence"] for item in eligible)
    else:
        raise ValueError(f"unsupported strong event rule {strong_event_rule!r}")

    budget = len(eligible) if all_eligible_new_evidence_updates else ordinary_budget
    if strong_event and not all_eligible_new_evidence_updates:
        budget += strong_extra_budget
    selected = []
    selected_spans = set()
    dimension_counts = {}
    diagnostics = []
    for selection_rank, item in enumerate(candidates, start=1):
        suppression = (
            item["eligibility_reasons"][0]
            if item["eligibility_reasons"] else None
        )
        if suppression is None and (
            require_independent_evidence
            and not allow_shared_evidence_across_distinct_variables
            and item.get("evidence_span") in selected_spans
        ):
            suppression = "evidence_already_supports_another_change"
        elif suppression is None and len(selected) >= budget:
            suppression = "event_change_budget"
        elif suppression is None:
            cap = (
                None
                if all_eligible_new_evidence_updates
                else (dimension_caps or {}).get(item["dimension"])
            )
            if cap is not None and dimension_counts.get(item["dimension"], 0) >= cap:
                suppression = "dimension_change_budget"

        is_selected = suppression is None
        diagnostic = {
            **item,
            "selection_rank": selection_rank,
            "selected": is_selected,
            "selection_reason": (
                (
                    "selected_valid_new_evidence_immediate"
                    if all_eligible_new_evidence_updates
                    else "selected_within_budgets"
                )
                if is_selected else suppression
            ),
            "final_delta": (
                _label(item["direction"], item["calibrated_level"])
                if is_selected else "similar"
            ),
        }
        if suppression is not None:
            diagnostic["suppressed_by"] = suppression
        diagnostics.append(diagnostic)
        if is_selected:
            selected.append(item)
            selected_spans.add(item.get("evidence_span"))
            dimension_counts[item["dimension"]] = (
                dimension_counts.get(item["dimension"], 0) + 1
            )
    return selected, diagnostics


def _bounded_label(current, requested, minimum=0, maximum=10):
    amount = DELTA_TO_INT[requested]
    applied = max(minimum, min(maximum, current + amount)) - current
    if applied == 0:
        return "similar"
    canonical_amount = min(3, ceil(abs(applied) - 1e-9))
    if applied < 0:
        canonical_amount *= -1
    return {value: key for key, value in DELTA_TO_INT.items()}[
        canonical_amount
    ]


class DeterministicStateCalibrator:
    """Apply one shared, inspectable calibration policy across all backbones."""

    def __init__(self, scenario, profile="sparse_v1"):
        if profile not in CALIBRATION_PROFILES:
            raise ValueError(f"unsupported state calibration profile {profile!r}")
        self.scenario = deepcopy(scenario)
        self.persona = deepcopy(scenario.get("environment_agent", {}).get("persona", {}))
        self.profile = profile
        self.profile_config = deepcopy(CALIBRATION_PROFILES[profile])
        semantics = build_state_semantics(self.scenario).get("variables", {})
        self._variable_timescales = {
            path: value["timescale"] for path, value in semantics.items()
        }
        self._slow_evidence_history = {}
        # Retain consumed event identities separately from the pending pool.
        # Otherwise an already-consumed event can be inserted again after the
        # pending set is cleared and later contribute to a second update.
        self._consumed_slow_evidence_history = {}
        self._calibration_sequence = 0

    @property
    def provenance(self):
        config = self.profile_config
        return {
            "calibrator_id": config["calibrator_id"],
            "calibration_profile": self.profile,
            "implementation": "deterministic_python",
            "state_persistence_default": True,
            "ordinary_change_budget": {
                "state": config["ordinary_budget"], "dynamics": 1
            },
            "strong_event_extra_budget": {
                "state": config["strong_extra_budget"], "dynamics": 0
            },
            "state_dimension_change_budgets": deepcopy(config["dimension_caps"]),
            "effective_state_dimension_change_budgets": (
                None
                if config.get("all_eligible_new_evidence_updates", False)
                else deepcopy(config["dimension_caps"])
            ),
            "state_selection_budget_policy": (
                "all_eligible_new_evidence"
                if config.get("all_eligible_new_evidence_updates", False)
                else "configured_event_and_dimension_budgets"
            ),
            "independent_evidence_required": config[
                "require_independent_evidence"
            ],
            "shared_evidence_across_distinct_variables_allowed": config.get(
                "allow_shared_evidence_across_distinct_variables", False
            ),
            "decisive_slow_tie_break": config.get(
                "prefer_decisive_slow_on_tie", False
            ),
            "slow_evidence_dimensions": list(config["slow_dimensions"]),
            "strong_event_rule": config["strong_event_rule"],
            "feature_compatibility_enforced": config.get(
                "enforce_feature_compatibility", False
            ),
            "feature_role": (
                "auxiliary_diagnostic"
                if config.get("feature_is_auxiliary", False)
                else "eligibility_and_magnitude"
            ),
            "dialogue_diagnostics_gate_enforced": config.get(
                "enforce_dialogue_diagnostics_gate", True
            ),
            "feature_direction_compatibility_enforced": config.get(
                "enforce_feature_direction_compatibility", False
            ),
            "variable_timescales_enforced": config.get(
                "use_variable_timescales", False
            ),
            "anti_convergence_hysteresis": config.get(
                "anti_convergence", False
            ),
            "new_evidence_updates_immediately": config.get(
                "new_evidence_updates_immediately", False
            ),
            "minimum_new_evidence_level": config.get(
                "minimum_new_evidence_level", 0
            ),
            "all_eligible_new_evidence_updates": config.get(
                "all_eligible_new_evidence_updates", False
            ),
            "slow_transition_rule": (
                "any_valid_new_evidence_updates_with_minimum_delta"
                if config.get("new_evidence_updates_immediately", False)
                else "one_decisive_or_two_independent_consistent_events"
                if config.get("use_variable_timescales", False)
                else None
            ),
            "slow_evidence_identity": config.get(
                "slow_evidence_identity", "feature_and_evidence_span"
            ),
            "slow_evidence_consumed_on_update": config.get(
                "consume_slow_evidence_on_update", False
            ),
        }

    def calibrate(
        self, appraisal, previous_state, previous_dynamics,
        surface_duplicate_evidence_ids=None, current_event_id=None,
    ):
        features = appraisal["event_features"]
        state_delta = _empty_delta(previous_state)
        dynamics_delta = _empty_delta(previous_dynamics)
        config = self.profile_config
        flat_state = flatten_state(previous_state)
        initial_state = flatten_state(self.scenario.get("initial_state", {}))
        semantic_novelty = (
            appraisal.get("dialogue_diagnostics", {})
            .get("substantive_novelty", {})
            .get("label")
        )
        if config.get("consume_slow_evidence_on_update", False):
            self._calibration_sequence += 1
            evidence_event_id = current_event_id or (
                f"calibration_call_{self._calibration_sequence}"
            )
        else:
            evidence_event_id = current_event_id
        state_impacts = deepcopy(appraisal["state_impacts"])
        replayed_consumed_sources = set()
        if config.get("consume_slow_evidence_on_update", False):
            for source_index, impact in enumerate(state_impacts):
                variable = impact.get("variable")
                if (
                    self._variable_timescales.get(variable) == "cross_turn_slow"
                    and evidence_event_id in self._consumed_slow_evidence_history.get(
                        variable, set()
                    )
                ):
                    impact["new_evidence"] = False
                    replayed_consumed_sources.add(source_index)
        state_selected, state_diagnostics = _ranked_impacts(
            state_impacts,
            features,
            self.persona,
            ordinary_budget=config["ordinary_budget"],
            strong_extra_budget=config["strong_extra_budget"],
            dimension_caps=config["dimension_caps"],
            require_independent_evidence=config["require_independent_evidence"],
            allow_shared_evidence_across_distinct_variables=config.get(
                "allow_shared_evidence_across_distinct_variables", False
            ),
            prefer_decisive_slow_on_tie=config.get(
                "prefer_decisive_slow_on_tie", False
            ),
            slow_dimensions=config["slow_dimensions"],
            strong_event_rule=config["strong_event_rule"],
            current_values=flat_state,
            initial_values=initial_state,
            enforce_feature_compatibility=config.get(
                "enforce_feature_compatibility", False
            ),
            enforce_feature_direction_compatibility=config.get(
                "enforce_feature_direction_compatibility", False
            ),
            use_variable_timescales=config.get(
                "use_variable_timescales", False
            ),
            anti_convergence=config.get("anti_convergence", False),
            semantic_novelty=semantic_novelty,
            feature_is_auxiliary=config.get("feature_is_auxiliary", False),
            decisive_evidence_rule=config.get(
                "decisive_evidence_rule", "legacy_dialogue_feature"
            ),
            variable_timescales=self._variable_timescales,
            new_evidence_updates_immediately=config.get(
                "new_evidence_updates_immediately", False
            ),
            minimum_new_evidence_level=config.get(
                "minimum_new_evidence_level", 0
            ),
            all_eligible_new_evidence_updates=config.get(
                "all_eligible_new_evidence_updates", False
            ),
            slow_evidence_counts={
                key: len(values)
                for key, values in self._slow_evidence_history.items()
            },
        )
        dynamics_selected, dynamics_diagnostics = _ranked_impacts(
            appraisal["dynamics_impacts"],
            features,
            self.persona,
            ordinary_budget=1,
            current_values=flatten_state(previous_dynamics),
            feature_is_auxiliary=config.get("feature_is_auxiliary", False),
            decisive_evidence_rule=config.get(
                "decisive_evidence_rule", "legacy_dialogue_feature"
            ),
            new_evidence_updates_immediately=config.get("new_evidence_updates_immediately", False),
            minimum_new_evidence_level=config.get("minimum_new_evidence_level", 0),
            all_eligible_new_evidence_updates=config.get("all_eligible_new_evidence_updates", False),
        )
        surface_duplicate_evidence_ids = list(surface_duplicate_evidence_ids or [])
        dialogue_gate_enforced = config.get(
            "enforce_dialogue_diagnostics_gate", True
        )
        deterministic_no_change = dialogue_gate_enforced and (
            semantic_novelty == "none" or bool(surface_duplicate_evidence_ids)
        )
        if deterministic_no_change:
            suppression = (
                "exact_same_speaker_surface_duplicate"
                if surface_duplicate_evidence_ids else "semantic_novelty_none"
            )
            state_selected = []
            dynamics_selected = []
            state_diagnostics = [
                {
                    **item,
                    "selected": False,
                    "selection_reason": suppression,
                    "suppressed_by": suppression,
                    "final_delta": "similar",
                }
                for item in state_diagnostics
            ]
            dynamics_diagnostics = [
                {
                    **item,
                    "selected": False,
                    "selection_reason": suppression,
                    "suppressed_by": suppression,
                    "final_delta": "similar",
                }
                for item in dynamics_diagnostics
            ]
        elif config.get("use_variable_timescales", False):
            for item in state_diagnostics:
                if item.get("source_index") in replayed_consumed_sources:
                    item["eligibility_status"] = "ineligible"
                    item["eligibility_reasons"] = [
                        "slow_evidence_already_consumed"
                    ]
                    item["selected"] = False
                    item["selection_reason"] = "slow_evidence_already_consumed"
                    item["suppressed_by"] = "slow_evidence_already_consumed"
                    item["final_delta"] = "similar"
                    item["slow_evidence_replayed_consumed"] = True
            selected_keys = {
                (item["variable"], item["direction"], item["source_index"])
                for item in state_selected
            }
            consume = config.get("consume_slow_evidence_on_update", False)
            for item in state_diagnostics:
                feature_ok = (
                    item.get("feature_compatible")
                    or not config.get("enforce_feature_compatibility", False)
                )
                valid_slow_evidence = (
                    item.get("timescale") == "cross_turn_slow"
                    and item.get("explicit_evidence")
                    and feature_ok
                    and item.get("feature_direction_compatible", True)
                    and item.get("new_evidence")
                    and item.get("calibrated_level", 0) > 0
                )
                if not valid_slow_evidence:
                    continue
                key = (item["variable"], item["direction"])
                opposite = (
                    item["variable"],
                    "decrease" if item["direction"] == "increase" else "increase",
                )
                selected = (
                    item["variable"], item["direction"], item["source_index"]
                ) in selected_keys
                if consume:
                    opposite_ids = sorted(
                        self._slow_evidence_history.pop(opposite, set())
                    )
                    item["opposite_pending_cleared_ids"] = opposite_ids
                    if selected:
                        consumed = sorted(
                            self._slow_evidence_history.pop(key, set())
                        )
                        consumed.append(evidence_event_id)
                        self._consumed_slow_evidence_history.setdefault(
                            item["variable"], set()
                        ).update(consumed)
                        item["slow_evidence_consumed_ids"] = consumed
                        item["slow_evidence_consumed"] = True
                    else:
                        self._slow_evidence_history.setdefault(key, set()).add(
                            evidence_event_id
                        )
                        item["slow_evidence_consumed"] = False
                else:
                    evidence_key = (
                        item.get("evidence_feature"),
                        item.get("evidence_span"),
                    )
                    self._slow_evidence_history.setdefault(key, set()).add(
                        evidence_key
                    )
                item["slow_evidence_event_id"] = evidence_event_id
                item["slow_evidence_pending_after"] = len(
                    self._slow_evidence_history.get(key, set())
                )
        flat_dynamics = flatten_state(previous_dynamics)
        for impact in state_selected:
            requested = _label(impact["direction"], impact["calibrated_level"])
            _set_path(
                state_delta,
                impact["variable"],
                _bounded_label(flat_state[impact["variable"]], requested),
            )
        for impact in dynamics_selected:
            requested = _label(impact["direction"], impact["calibrated_level"])
            # Dynamics are flat today, but _set_path also supports grouped future schemas.
            _set_path(
                dynamics_delta,
                impact["variable"],
                _bounded_label(flat_dynamics[impact["variable"]], requested),
            )
        return {
            "state_delta": state_delta,
            "interaction_dynamics_delta": dynamics_delta,
            "calibration": {
                **self.provenance,
                "semantic_novelty": semantic_novelty,
                "semantic_novelty_role": (
                    "eligibility_gate"
                    if dialogue_gate_enforced else "interaction_diagnostic_only"
                ),
                "semantic_no_change_enforced": deterministic_no_change,
                "current_evidence_event_id": evidence_event_id,
                "surface_duplicate_evidence_ids": surface_duplicate_evidence_ids,
                "slow_evidence_history": {
                    f"{variable}:{direction}": len(values)
                    for (variable, direction), values in sorted(
                        self._slow_evidence_history.items()
                    )
                },
                "slow_evidence_consumed_history": {
                    variable: sorted(values)
                    for variable, values in sorted(
                        self._consumed_slow_evidence_history.items()
                    )
                },
                "state_impacts": state_diagnostics,
                "dynamics_impacts": dynamics_diagnostics,
            },
        }
