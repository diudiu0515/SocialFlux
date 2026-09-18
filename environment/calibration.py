"""Deterministic calibration from structured social impacts to state deltas."""

from __future__ import annotations

from copy import deepcopy

from .delta_mapper import DELTA_TO_INT, flatten_state


CALIBRATOR_ID = "deterministic_social_delta_calibrator_v1"

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


def _calibrated_level(impact, feature_value, sensitivity):
    """Return a deterministic 0–3 magnitude with persistence as the default."""
    if not impact["new_evidence"] or feature_value == 0:
        return 0
    level = impact["evidence_strength"]
    if impact["directness"] == "indirect":
        level -= 1
    if level >= 2 and abs(feature_value) == 2 and sensitivity >= 0.80:
        level = 3
    elif level >= 2:
        level = 2
    elif level >= 1:
        level = 1
    if sensitivity <= 0.20 and level > 1:
        level -= 1
    return max(0, min(3, level))


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
):
    candidates = []
    for impact in impacts:
        feature_name = impact.get("evidence_feature")
        feature_inferred = feature_name not in features
        if feature_name not in features:
            feature_name = max(features, key=lambda key: abs(features[key]), default=None)
        feature_value = features.get(feature_name, 0)
        sensitivity = _persona_sensitivity(persona, feature_name)
        level = _calibrated_level(impact, feature_value, sensitivity)
        candidates.append({
            **deepcopy(impact),
            "evidence_feature": feature_name,
            "feature_inferred": feature_inferred,
            "feature_value": feature_value,
            "persona_sensitivity": round(sensitivity, 4),
            "calibrated_level": level,
        })
    candidates.sort(
        key=lambda item: (
            -item["calibrated_level"],
            -abs(item["feature_value"]),
            item["variable"],
        )
    )
    eligible = [item for item in candidates if item["calibrated_level"] > 0]
    budget = ordinary_budget
    if any(
        item["calibrated_level"] == 3 and not item["feature_inferred"]
        for item in eligible
    ):
        budget += strong_extra_budget
    selected = eligible[:budget]
    selected_paths = {item["variable"] for item in selected}
    diagnostics = [
        {**item, "selected": item["variable"] in selected_paths}
        for item in candidates
    ]
    return selected, diagnostics


def _bounded_label(current, requested, minimum=0, maximum=10):
    amount = DELTA_TO_INT[requested]
    applied = max(minimum, min(maximum, current + amount)) - current
    return {value: key for key, value in DELTA_TO_INT.items()}[applied]


class DeterministicStateCalibrator:
    """Apply one shared, inspectable calibration policy across all backbones."""

    def __init__(self, scenario):
        self.scenario = deepcopy(scenario)
        self.persona = deepcopy(scenario.get("environment_agent", {}).get("persona", {}))

    @property
    def provenance(self):
        return {
            "calibrator_id": CALIBRATOR_ID,
            "implementation": "deterministic_python",
            "state_persistence_default": True,
            "ordinary_change_budget": {"state": 1, "dynamics": 1},
            "strong_event_extra_budget": {"state": 1, "dynamics": 0},
        }

    def calibrate(
        self, appraisal, previous_state, previous_dynamics,
        surface_duplicate_evidence_ids=None,
    ):
        features = appraisal["event_features"]
        state_delta = _empty_delta(previous_state)
        dynamics_delta = _empty_delta(previous_dynamics)
        state_selected, state_diagnostics = _ranked_impacts(
            appraisal["state_impacts"],
            features,
            self.persona,
            ordinary_budget=1,
            strong_extra_budget=1,
        )
        dynamics_selected, dynamics_diagnostics = _ranked_impacts(
            appraisal["dynamics_impacts"],
            features,
            self.persona,
            ordinary_budget=1,
        )
        semantic_novelty = (
            appraisal.get("dialogue_diagnostics", {})
            .get("substantive_novelty", {})
            .get("label")
        )
        surface_duplicate_evidence_ids = list(surface_duplicate_evidence_ids or [])
        deterministic_no_change = (
            semantic_novelty == "none" or bool(surface_duplicate_evidence_ids)
        )
        if deterministic_no_change:
            state_selected = []
            dynamics_selected = []
            state_diagnostics = [
                {
                    **item, "selected": False,
                    "suppressed_by": (
                        "exact_same_speaker_surface_duplicate"
                        if surface_duplicate_evidence_ids else "semantic_novelty_none"
                    ),
                }
                for item in state_diagnostics
            ]
            dynamics_diagnostics = [
                {
                    **item, "selected": False,
                    "suppressed_by": (
                        "exact_same_speaker_surface_duplicate"
                        if surface_duplicate_evidence_ids else "semantic_novelty_none"
                    ),
                }
                for item in dynamics_diagnostics
            ]
        flat_state = flatten_state(previous_state)
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
                "semantic_no_change_enforced": deterministic_no_change,
                "surface_duplicate_evidence_ids": surface_duplicate_evidence_ids,
                "state_impacts": state_diagnostics,
                "dynamics_impacts": dynamics_diagnostics,
            },
        }
