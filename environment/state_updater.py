"""Deterministic state updates derived from one structured model appraisal."""

from copy import deepcopy
from math import ceil

from .appraisal import ModelAppraiser
from .calibration import DeterministicStateCalibrator
from .delta_mapper import DELTA_LABELS, DELTA_TO_INT, apply_semantic_deltas


class TransitionValidationError(ValueError):
    pass


class UnsupportedConsequentialClaim(TransitionValidationError):
    """A policy draft asserts a consequential fact absent from public evidence."""

    def __init__(self, claims, appraisal):
        self.claims = deepcopy(claims)
        self.appraisal = deepcopy(appraisal)
        spans = [item.get("claim_span", "") for item in claims]
        super().__init__(
            "unsupported consequential claim(s): "
            + " | ".join(span for span in spans if span)
        )


def unsupported_consequential_claims(appraisal):
    diagnostics = (appraisal or {}).get("dialogue_diagnostics", {})
    return [
        deepcopy(claim)
        for claim in diagnostics.get("consequential_claims", [])
        if claim.get("grounding") == "unsupported_assertion"
        and claim.get("impact_domains")
    ]


def _validate_delta_shape(state, delta, path=""):
    if not isinstance(delta, dict):
        raise TransitionValidationError(f"{path or 'delta'} must be an object")
    expected = set(state)
    if set(delta) != expected:
        missing, extra = expected - set(delta), set(delta) - expected
        raise TransitionValidationError(
            f"{path or 'delta'} variables mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    for key, value in state.items():
        current = f"{path}.{key}" if path else key
        if isinstance(value, dict):
            _validate_delta_shape(value, delta[key], current)
        elif delta[key] not in DELTA_LABELS:
            raise TransitionValidationError(f"{current} has invalid delta {delta[key]!r}")


def validate_transition(transition, state, dynamics):
    if not isinstance(transition, dict):
        raise TransitionValidationError("transition must be an object")
    for key in ("appraisal", "state_delta", "interaction_dynamics_delta", "evidence_turn_ids"):
        if key not in transition:
            raise TransitionValidationError(f"transition missing {key}")
    _validate_delta_shape(state, transition["state_delta"], "state_delta")
    _validate_delta_shape(
        dynamics,
        transition["interaction_dynamics_delta"],
        "interaction_dynamics_delta",
    )
    if not isinstance(transition["appraisal"], dict):
        raise TransitionValidationError("appraisal must be an object")
    return transition


def _canonicalize_bounded_deltas(values, deltas, minimum=0, maximum=10):
    canonical = {}
    int_to_label = {value: key for key, value in DELTA_TO_INT.items()}
    for key, value in values.items():
        if isinstance(value, dict):
            canonical[key] = _canonicalize_bounded_deltas(
                value,
                deltas[key],
                minimum,
                maximum,
            )
            continue
        requested = DELTA_TO_INT[deltas[key]]
        applied = max(minimum, min(maximum, value + requested)) - value
        if applied == 0:
            canonical[key] = "similar"
            continue
        canonical_amount = min(3, ceil(abs(applied) - 1e-9))
        if applied < 0:
            canonical_amount *= -1
        canonical[key] = int_to_label[canonical_amount]
    return canonical


def canonicalize_bounded_transition(transition, state, dynamics):
    """Make semantic labels agree with the numeric effect after 0–10 clipping."""
    normalized = deepcopy(transition)
    normalized["state_delta"] = _canonicalize_bounded_deltas(
        state,
        normalized["state_delta"],
    )
    normalized["interaction_dynamics_delta"] = _canonicalize_bounded_deltas(
        dynamics,
        normalized["interaction_dynamics_delta"],
    )
    return normalized


def apply_transition(state, dynamics, transition):
    validate_transition(transition, state, dynamics)
    new_state, state_numeric = apply_semantic_deltas(state, transition["state_delta"])
    new_dynamics, dynamics_numeric = apply_semantic_deltas(
        dynamics,
        transition["interaction_dynamics_delta"],
    )
    return new_state, new_dynamics, state_numeric, dynamics_numeric


class ModelStateUpdater:
    """Compatibility name for structured appraisal + deterministic calibration.

    The provider is called exactly once here. The next model call belongs to the
    response generator, after the calibrated transition has been applied.
    """

    def __init__(self, scenario, provider, sampling=None, appraiser=None, calibrator=None):
        self.scenario = deepcopy(scenario)
        self.provider = provider
        self.sampling = dict(sampling or {})
        self.appraiser = appraiser or ModelAppraiser(scenario, provider, sampling)
        self.calibrator = calibrator or DeterministicStateCalibrator(scenario)

    @property
    def provenance(self):
        return {
            **getattr(self.provider, "provenance", {}),
            "appraisal_prompt_id": getattr(
                self.appraiser, "prompt_id", "environment_appraisal_v11"
            ),
            "state_update": "deterministic",
            **self.calibrator.provenance,
            "sampling": dict(self.sampling),
        }

    def update(
        self, *, action, previous_state, previous_dynamics, memory,
        longitudinal_context=None, interaction_ledger=None,
    ):
        appraisal = self.appraiser.appraise(
            action=action,
            previous_state=previous_state,
            previous_dynamics=previous_dynamics,
            memory=memory,
            longitudinal_context=longitudinal_context,
            interaction_ledger=interaction_ledger,
        )
        unsupported = unsupported_consequential_claims(appraisal["appraisal"])
        if unsupported:
            raise UnsupportedConsequentialClaim(
                unsupported, appraisal["appraisal"]
            )
        calibrated = self.calibrator.calibrate(
            appraisal["appraisal"], previous_state, previous_dynamics,
            surface_duplicate_evidence_ids=memory.get(
                "deterministic_surface_duplicate_ids", []
            ),
        )
        transition = {
            "appraisal": appraisal["appraisal"],
            "evidence_turn_ids": appraisal["evidence_turn_ids"],
            "appraisal_request_retry_diagnostics": deepcopy(
                appraisal.get("request_retry_diagnostics", [])
            ),
            **calibrated,
        }
        validate_transition(transition, previous_state, previous_dynamics)
        return canonicalize_bounded_transition(
            transition,
            previous_state,
            previous_dynamics,
        )
