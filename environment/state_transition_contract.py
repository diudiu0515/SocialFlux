"""Explicit runtime contract for State Transition Standard v3.

This module keeps scenario readiness, rollout configuration, and recorded
runtime provenance aligned. It validates evidence-bearing inputs; it never
inserts a state change or edits a generated trajectory.
"""

from __future__ import annotations

from environment.delta_mapper import flatten_state
from environment.state_ontology import (
    FAMILY_RULES,
    STATE_ONTOLOGY_VERSION,
    VARIABLE_RULES,
    VALID_TIMESCALES,
    build_state_semantics,
)
from schemas.validate import (
    STATE_CONTRACT_VERSION,
    validate_v3_state_selection,
)


STATE_TRANSITION_STANDARD_V3 = "socialflux_state_transition_standard_v3"
STATE_V3_APPRAISAL_PROMPT_ID = "environment_appraisal_v15"
STATE_V3_BEHAVIORAL_APPRAISAL_PROMPT_ID = "environment_appraisal_v16"
STATE_V3_DIRECTIONAL_APPRAISAL_PROMPT_ID = "environment_appraisal_v17"
STATE_V3_ENVIRONMENT_OWNED_APPRAISAL_PROMPT_ID = "environment_appraisal_v18"
STATE_V3_CAUSAL_APPRAISAL_PROMPT_ID = "environment_appraisal_v19"
STATE_V3_STABLE_ENVIRONMENT_OWNED_APPRAISAL_PROMPT_ID = (
    "environment_appraisal_v15_environment_owned"
)
STATE_V3_SLOW_RECALL_APPRAISAL_PROMPT_ID = (
    "environment_appraisal_v20_slow_evidence_recall"
)
STATE_V3_SLOW_AUDIT_APPRAISAL_PROMPT_ID = (
    "environment_appraisal_v21_slow_candidate_audit"
)
STATE_V3_SLOW_FIRST_APPRAISAL_PROMPT_ID = "environment_appraisal_v22_slow_first"
STATE_V3_FEATURE_CONSISTENT_APPRAISAL_PROMPT_ID = (
    "environment_appraisal_v23_feature_consistent_slow_first"
)
STATE_V3_BALANCED_SLOW_APPRAISAL_PROMPT_ID = (
    "environment_appraisal_v24_balanced_slow_evidence"
)
STATE_V3_OPERATIONAL_SLOW_APPRAISAL_PROMPT_ID = (
    "environment_appraisal_v25_operational_slow_evidence"
)
STATE_V3_BOUND_SLOW_APPRAISAL_PROMPT_ID = (
    "environment_appraisal_v26_bound_slow_evidence"
)
STATE_V3_MEMORY_BOUND_SLOW_APPRAISAL_PROMPT_ID = (
    "environment_appraisal_v27_memory_bound_slow_evidence"
)
STATE_V3_ACTOR_MEMORY_BOUND_SLOW_APPRAISAL_PROMPT_ID = (
    "environment_appraisal_v28_actor_memory_bound_slow_evidence"
)
STATE_V3_CONCISE_ACTOR_MEMORY_SLOW_APPRAISAL_PROMPT_ID = (
    "environment_appraisal_v29_concise_actor_memory_slow_evidence"
)
STATE_V3_SCOPE_AWARE_ACTOR_MEMORY_SLOW_APPRAISAL_PROMPT_ID = (
    "environment_appraisal_v30_scope_aware_actor_memory_slow_evidence"
)
STATE_V3_SCOPE_NOVELTY_ACTOR_MEMORY_SLOW_APPRAISAL_PROMPT_ID = (
    "environment_appraisal_v31_scope_novelty_actor_memory_slow_evidence"
)
STATE_V3_SCOPE_NOVELTY_STRENGTH_ACTOR_MEMORY_SLOW_APPRAISAL_PROMPT_ID = (
    "environment_appraisal_v32_scope_novelty_strength_actor_memory_slow_evidence"
)
STATE_V3_SAFETY_SCOPE_ACTOR_MEMORY_SLOW_APPRAISAL_PROMPT_ID = (
    "environment_appraisal_v33_safety_scope_actor_memory_slow_evidence"
)
STATE_V3_SAFETY_ELIGIBILITY_ACTOR_MEMORY_SLOW_APPRAISAL_PROMPT_ID = (
    "environment_appraisal_v34_safety_eligibility_actor_memory_slow_evidence"
)
STATE_V3_ADJACENT_VARIABLE_RECHECK_ACTOR_MEMORY_SLOW_APPRAISAL_PROMPT_ID = (
    "environment_appraisal_v35_adjacent_variable_recheck_actor_memory_slow_evidence"
)
STATE_V3_EVIDENCE_GROUNDED_STATE_INTERPRETATION_APPRAISAL_PROMPT_ID = (
    "environment_appraisal_v36_evidence_grounded_state_interpretation"
)
STATE_V3_LEGACY_RESPONSE_PROMPT_ID = "environment_response_v26"
STATE_V3_RESPONSE_PROMPT_ID = "environment_response_v27"
STATE_V3_DECISION_CONTINUITY_RESPONSE_PROMPT_ID = (
    "environment_response_v27_decision_continuity"
)
STATE_V3_EARLY_OPPORTUNITY_RESPONSE_PROMPT_ID = "environment_response_v28"
STATE_V3_EVENT_DRIVEN_RESPONSE_PROMPT_ID = "environment_response_v29_event_driven"
STATE_V3_SEMANTIC_EVENT_RESPONSE_PROMPT_ID = (
    "environment_response_v30_semantic_event_driven"
)
STATE_V3_CONTRASTIVE_EVENT_RESPONSE_PROMPT_ID = (
    "environment_response_v31_contrastive_event_driven"
)
STATE_V3_CALIBRATION_PROFILE = "evidence_independent_hysteretic_v3"
STATE_V3_DIRECTIONAL_CALIBRATION_PROFILE = (
    "evidence_independent_directional_hysteretic_v4"
)
STATE_V3_CAUSAL_CALIBRATION_PROFILE = "evidence_causal_hysteretic_v5"
STATE_V3_SLOW_PRIORITY_CAUSAL_CALIBRATION_PROFILE = (
    "evidence_causal_slow_priority_hysteretic_v6"
)
STATE_V3_STATE_JUDGMENT_PRIMARY_CALIBRATION_PROFILE = (
    "state_judgment_primary_hysteretic_v7"
)
STATE_V3_LEGACY_RUNTIME_REVISION = "v3.0"
STATE_V3_RUNTIME_REVISION = "v3.1"
STATE_V3_NATURAL_RUNTIME_REVISION = "v3.2"
STATE_V3_EARLY_OPPORTUNITY_RUNTIME_REVISION = "v3.3"
STATE_V3_BEHAVIORAL_EVIDENCE_RUNTIME_REVISION = "v3.4"
STATE_V3_DIRECTIONAL_EVIDENCE_RUNTIME_REVISION = "v3.5"
STATE_V3_ENVIRONMENT_OWNED_RUNTIME_REVISION = "v3.6"
STATE_V3_CAUSAL_RUNTIME_REVISION = "v3.7"
STATE_V3_STABLE_ENVIRONMENT_OWNED_RUNTIME_REVISION = "v3.2.1"
STATE_V3_DECISION_CONTINUITY_RUNTIME_REVISION = "v3.2.2"
STATE_V3_EVENT_DRIVEN_RUNTIME_REVISION = "v3.2.3"
STATE_V3_SLOW_RECALL_RUNTIME_REVISION = "v3.2.4"
STATE_V3_SLOW_AUDIT_RUNTIME_REVISION = "v3.2.5"
STATE_V3_SLOW_FIRST_RUNTIME_REVISION = "v3.2.6"
STATE_V3_SEMANTIC_EVENT_RUNTIME_REVISION = "v3.2.7"
STATE_V3_CONTRASTIVE_EVENT_RUNTIME_REVISION = "v3.2.8"
STATE_V3_FEATURE_CONSISTENT_RUNTIME_REVISION = "v3.2.9"
STATE_V3_BALANCED_SLOW_RUNTIME_REVISION = "v3.2.10"
STATE_V3_OPERATIONAL_SLOW_RUNTIME_REVISION = "v3.2.11"
STATE_V3_BOUND_SLOW_RUNTIME_REVISION = "v3.2.12"
STATE_V3_MEMORY_BOUND_SLOW_RUNTIME_REVISION = "v3.2.13"
STATE_V3_ACTOR_MEMORY_BOUND_SLOW_RUNTIME_REVISION = "v3.2.14"
STATE_V3_CONCISE_ACTOR_MEMORY_SLOW_RUNTIME_REVISION = "v3.2.15"
STATE_V3_SCOPE_AWARE_ACTOR_MEMORY_SLOW_RUNTIME_REVISION = "v3.2.16"
STATE_V3_SCOPE_NOVELTY_ACTOR_MEMORY_SLOW_RUNTIME_REVISION = "v3.2.17"
STATE_V3_SCOPE_NOVELTY_STRENGTH_ACTOR_MEMORY_SLOW_RUNTIME_REVISION = "v3.2.18"
STATE_V3_SAFETY_SCOPE_ACTOR_MEMORY_SLOW_RUNTIME_REVISION = "v3.2.19"
STATE_V3_SAFETY_ELIGIBILITY_ACTOR_MEMORY_SLOW_RUNTIME_REVISION = "v3.2.20"
STATE_V3_ADJACENT_VARIABLE_RECHECK_ACTOR_MEMORY_SLOW_RUNTIME_REVISION = "v3.2.21"
STATE_V3_EVIDENCE_GROUNDED_STATE_INTERPRETATION_RUNTIME_REVISION = "v3.2.22"
STATE_V3_STATE_JUDGMENT_PRIMARY_RUNTIME_REVISION = "v3.2.23"
STATE_V3_STATE_JUDGMENT_PRIMARY_CONTEXT_RUNTIME_REVISION = "v3.2.24"
STATE_V3_STAGE_ORDER = (
    "evaluated_action",
    "environment_appraisal",
    "deterministic_calibration",
    "environment_state_update",
    "environment_response",
)


def validate_state_transition_environment_config(environment, *, explicit=False):
    """Validate the named v3 binding before any provider is constructed.

    Historical configurations may omit a standard. A rollout configuration
    using either v3 component must declare the complete standard explicitly;
    direct diagnostic factories can opt out by leaving ``explicit=False``.
    """
    standard = environment.get("state_transition_standard")
    prompt_id = environment.get("appraisal_prompt_id")
    response_prompt_id = environment.get("response_prompt_id")
    profile = environment.get("state_calibration_profile")
    runtime_revision = (
        environment.get("state_transition_runtime_revision")
        or STATE_V3_LEGACY_RUNTIME_REVISION
    )
    if runtime_revision not in {
        STATE_V3_LEGACY_RUNTIME_REVISION,
        STATE_V3_RUNTIME_REVISION,
        STATE_V3_NATURAL_RUNTIME_REVISION,
        STATE_V3_EARLY_OPPORTUNITY_RUNTIME_REVISION,
        STATE_V3_BEHAVIORAL_EVIDENCE_RUNTIME_REVISION,
        STATE_V3_DIRECTIONAL_EVIDENCE_RUNTIME_REVISION,
        STATE_V3_ENVIRONMENT_OWNED_RUNTIME_REVISION,
        STATE_V3_CAUSAL_RUNTIME_REVISION,
        STATE_V3_STABLE_ENVIRONMENT_OWNED_RUNTIME_REVISION,
        STATE_V3_DECISION_CONTINUITY_RUNTIME_REVISION,
        STATE_V3_EVENT_DRIVEN_RUNTIME_REVISION,
        STATE_V3_SLOW_RECALL_RUNTIME_REVISION,
        STATE_V3_SLOW_AUDIT_RUNTIME_REVISION,
        STATE_V3_SLOW_FIRST_RUNTIME_REVISION,
        STATE_V3_SEMANTIC_EVENT_RUNTIME_REVISION,
        STATE_V3_CONTRASTIVE_EVENT_RUNTIME_REVISION,
        STATE_V3_FEATURE_CONSISTENT_RUNTIME_REVISION,
        STATE_V3_BALANCED_SLOW_RUNTIME_REVISION,
        STATE_V3_OPERATIONAL_SLOW_RUNTIME_REVISION,

        STATE_V3_BOUND_SLOW_RUNTIME_REVISION,
        STATE_V3_MEMORY_BOUND_SLOW_RUNTIME_REVISION,
        STATE_V3_ACTOR_MEMORY_BOUND_SLOW_RUNTIME_REVISION,
        STATE_V3_CONCISE_ACTOR_MEMORY_SLOW_RUNTIME_REVISION,
        STATE_V3_SCOPE_AWARE_ACTOR_MEMORY_SLOW_RUNTIME_REVISION,
        STATE_V3_SCOPE_NOVELTY_ACTOR_MEMORY_SLOW_RUNTIME_REVISION,
        STATE_V3_SCOPE_NOVELTY_STRENGTH_ACTOR_MEMORY_SLOW_RUNTIME_REVISION,
        STATE_V3_SAFETY_SCOPE_ACTOR_MEMORY_SLOW_RUNTIME_REVISION,
        STATE_V3_SAFETY_ELIGIBILITY_ACTOR_MEMORY_SLOW_RUNTIME_REVISION,
        STATE_V3_ADJACENT_VARIABLE_RECHECK_ACTOR_MEMORY_SLOW_RUNTIME_REVISION,
        STATE_V3_EVIDENCE_GROUNDED_STATE_INTERPRETATION_RUNTIME_REVISION,
        STATE_V3_STATE_JUDGMENT_PRIMARY_RUNTIME_REVISION,
        STATE_V3_STATE_JUDGMENT_PRIMARY_CONTEXT_RUNTIME_REVISION,
    }:
        raise ValueError(
            f"unsupported state transition runtime revision {runtime_revision!r}"
        )
    expected_response_prompt = {
        STATE_V3_LEGACY_RUNTIME_REVISION: STATE_V3_LEGACY_RESPONSE_PROMPT_ID,
        STATE_V3_RUNTIME_REVISION: STATE_V3_RESPONSE_PROMPT_ID,
        STATE_V3_NATURAL_RUNTIME_REVISION: STATE_V3_RESPONSE_PROMPT_ID,
        STATE_V3_EARLY_OPPORTUNITY_RUNTIME_REVISION: (
            STATE_V3_EARLY_OPPORTUNITY_RESPONSE_PROMPT_ID
        ),
        STATE_V3_BEHAVIORAL_EVIDENCE_RUNTIME_REVISION: (
            STATE_V3_EARLY_OPPORTUNITY_RESPONSE_PROMPT_ID
        ),
        STATE_V3_DIRECTIONAL_EVIDENCE_RUNTIME_REVISION: (
            STATE_V3_EARLY_OPPORTUNITY_RESPONSE_PROMPT_ID
        ),
        STATE_V3_ENVIRONMENT_OWNED_RUNTIME_REVISION: (
            STATE_V3_EARLY_OPPORTUNITY_RESPONSE_PROMPT_ID
        ),
        STATE_V3_CAUSAL_RUNTIME_REVISION: (
            STATE_V3_EARLY_OPPORTUNITY_RESPONSE_PROMPT_ID
        ),
        STATE_V3_STABLE_ENVIRONMENT_OWNED_RUNTIME_REVISION: (
            STATE_V3_RESPONSE_PROMPT_ID
        ),
        STATE_V3_DECISION_CONTINUITY_RUNTIME_REVISION: (
            STATE_V3_DECISION_CONTINUITY_RESPONSE_PROMPT_ID
        ),
        STATE_V3_EVENT_DRIVEN_RUNTIME_REVISION: (
            STATE_V3_EVENT_DRIVEN_RESPONSE_PROMPT_ID
        ),
        STATE_V3_SLOW_RECALL_RUNTIME_REVISION: (
            STATE_V3_EVENT_DRIVEN_RESPONSE_PROMPT_ID
        ),
        STATE_V3_SLOW_AUDIT_RUNTIME_REVISION: (
            STATE_V3_EVENT_DRIVEN_RESPONSE_PROMPT_ID
        ),
        STATE_V3_SLOW_FIRST_RUNTIME_REVISION: (
            STATE_V3_EVENT_DRIVEN_RESPONSE_PROMPT_ID
        ),
        STATE_V3_SEMANTIC_EVENT_RUNTIME_REVISION: (
            STATE_V3_SEMANTIC_EVENT_RESPONSE_PROMPT_ID
        ),
        STATE_V3_CONTRASTIVE_EVENT_RUNTIME_REVISION: (
            STATE_V3_CONTRASTIVE_EVENT_RESPONSE_PROMPT_ID
        ),
        STATE_V3_FEATURE_CONSISTENT_RUNTIME_REVISION: (
            STATE_V3_CONTRASTIVE_EVENT_RESPONSE_PROMPT_ID
        ),
        STATE_V3_BALANCED_SLOW_RUNTIME_REVISION: (
            STATE_V3_CONTRASTIVE_EVENT_RESPONSE_PROMPT_ID
        ),
        STATE_V3_OPERATIONAL_SLOW_RUNTIME_REVISION: (
            STATE_V3_CONTRASTIVE_EVENT_RESPONSE_PROMPT_ID
        ),
        STATE_V3_BOUND_SLOW_RUNTIME_REVISION: (
            STATE_V3_CONTRASTIVE_EVENT_RESPONSE_PROMPT_ID
        ),
        STATE_V3_MEMORY_BOUND_SLOW_RUNTIME_REVISION: (
            STATE_V3_CONTRASTIVE_EVENT_RESPONSE_PROMPT_ID
        ),
        STATE_V3_ACTOR_MEMORY_BOUND_SLOW_RUNTIME_REVISION: (
            STATE_V3_CONTRASTIVE_EVENT_RESPONSE_PROMPT_ID
        ),
        STATE_V3_CONCISE_ACTOR_MEMORY_SLOW_RUNTIME_REVISION: (
            STATE_V3_CONTRASTIVE_EVENT_RESPONSE_PROMPT_ID
        ),
        STATE_V3_SCOPE_AWARE_ACTOR_MEMORY_SLOW_RUNTIME_REVISION: (
            STATE_V3_CONTRASTIVE_EVENT_RESPONSE_PROMPT_ID
        ),
        STATE_V3_SCOPE_NOVELTY_ACTOR_MEMORY_SLOW_RUNTIME_REVISION: (
            STATE_V3_CONTRASTIVE_EVENT_RESPONSE_PROMPT_ID
        ),
        STATE_V3_SCOPE_NOVELTY_STRENGTH_ACTOR_MEMORY_SLOW_RUNTIME_REVISION: (
            STATE_V3_CONTRASTIVE_EVENT_RESPONSE_PROMPT_ID
        ),
        STATE_V3_SAFETY_SCOPE_ACTOR_MEMORY_SLOW_RUNTIME_REVISION: (
            STATE_V3_CONTRASTIVE_EVENT_RESPONSE_PROMPT_ID
        ),
        STATE_V3_SAFETY_ELIGIBILITY_ACTOR_MEMORY_SLOW_RUNTIME_REVISION: (
            STATE_V3_CONTRASTIVE_EVENT_RESPONSE_PROMPT_ID
        ),
        STATE_V3_ADJACENT_VARIABLE_RECHECK_ACTOR_MEMORY_SLOW_RUNTIME_REVISION: (
            STATE_V3_CONTRASTIVE_EVENT_RESPONSE_PROMPT_ID
        ),
        STATE_V3_EVIDENCE_GROUNDED_STATE_INTERPRETATION_RUNTIME_REVISION: (
            STATE_V3_CONTRASTIVE_EVENT_RESPONSE_PROMPT_ID
        ),
        STATE_V3_STATE_JUDGMENT_PRIMARY_RUNTIME_REVISION: (
            STATE_V3_CONTRASTIVE_EVENT_RESPONSE_PROMPT_ID
        ),
        STATE_V3_STATE_JUDGMENT_PRIMARY_CONTEXT_RUNTIME_REVISION: (
            STATE_V3_CONTRASTIVE_EVENT_RESPONSE_PROMPT_ID
        ),
    }[runtime_revision]
    expected_appraisal_prompt = {
        STATE_V3_BEHAVIORAL_EVIDENCE_RUNTIME_REVISION: (
            STATE_V3_BEHAVIORAL_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_DIRECTIONAL_EVIDENCE_RUNTIME_REVISION: (
            STATE_V3_DIRECTIONAL_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_ENVIRONMENT_OWNED_RUNTIME_REVISION: (
            STATE_V3_ENVIRONMENT_OWNED_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_CAUSAL_RUNTIME_REVISION: (
            STATE_V3_CAUSAL_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_STABLE_ENVIRONMENT_OWNED_RUNTIME_REVISION: (
            STATE_V3_STABLE_ENVIRONMENT_OWNED_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_DECISION_CONTINUITY_RUNTIME_REVISION: (
            STATE_V3_STABLE_ENVIRONMENT_OWNED_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_EVENT_DRIVEN_RUNTIME_REVISION: (
            STATE_V3_STABLE_ENVIRONMENT_OWNED_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_SLOW_RECALL_RUNTIME_REVISION: (
            STATE_V3_SLOW_RECALL_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_SLOW_AUDIT_RUNTIME_REVISION: (
            STATE_V3_SLOW_AUDIT_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_SLOW_FIRST_RUNTIME_REVISION: (
            STATE_V3_SLOW_FIRST_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_SEMANTIC_EVENT_RUNTIME_REVISION: (
            STATE_V3_SLOW_FIRST_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_CONTRASTIVE_EVENT_RUNTIME_REVISION: (
            STATE_V3_SLOW_FIRST_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_FEATURE_CONSISTENT_RUNTIME_REVISION: (
            STATE_V3_FEATURE_CONSISTENT_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_BALANCED_SLOW_RUNTIME_REVISION: (
            STATE_V3_BALANCED_SLOW_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_OPERATIONAL_SLOW_RUNTIME_REVISION: (
            STATE_V3_OPERATIONAL_SLOW_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_BOUND_SLOW_RUNTIME_REVISION: (
            STATE_V3_BOUND_SLOW_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_MEMORY_BOUND_SLOW_RUNTIME_REVISION: (
            STATE_V3_MEMORY_BOUND_SLOW_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_ACTOR_MEMORY_BOUND_SLOW_RUNTIME_REVISION: (
            STATE_V3_ACTOR_MEMORY_BOUND_SLOW_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_CONCISE_ACTOR_MEMORY_SLOW_RUNTIME_REVISION: (
            STATE_V3_CONCISE_ACTOR_MEMORY_SLOW_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_SCOPE_AWARE_ACTOR_MEMORY_SLOW_RUNTIME_REVISION: (
            STATE_V3_SCOPE_AWARE_ACTOR_MEMORY_SLOW_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_SCOPE_NOVELTY_ACTOR_MEMORY_SLOW_RUNTIME_REVISION: (
            STATE_V3_SCOPE_NOVELTY_ACTOR_MEMORY_SLOW_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_SCOPE_NOVELTY_STRENGTH_ACTOR_MEMORY_SLOW_RUNTIME_REVISION: (
            STATE_V3_SCOPE_NOVELTY_STRENGTH_ACTOR_MEMORY_SLOW_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_SAFETY_SCOPE_ACTOR_MEMORY_SLOW_RUNTIME_REVISION: (
            STATE_V3_SAFETY_SCOPE_ACTOR_MEMORY_SLOW_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_SAFETY_ELIGIBILITY_ACTOR_MEMORY_SLOW_RUNTIME_REVISION: (
            STATE_V3_SAFETY_ELIGIBILITY_ACTOR_MEMORY_SLOW_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_ADJACENT_VARIABLE_RECHECK_ACTOR_MEMORY_SLOW_RUNTIME_REVISION: (
            STATE_V3_ADJACENT_VARIABLE_RECHECK_ACTOR_MEMORY_SLOW_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_EVIDENCE_GROUNDED_STATE_INTERPRETATION_RUNTIME_REVISION: (
            STATE_V3_EVIDENCE_GROUNDED_STATE_INTERPRETATION_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_STATE_JUDGMENT_PRIMARY_RUNTIME_REVISION: (
            STATE_V3_EVIDENCE_GROUNDED_STATE_INTERPRETATION_APPRAISAL_PROMPT_ID
        ),
        STATE_V3_STATE_JUDGMENT_PRIMARY_CONTEXT_RUNTIME_REVISION: (
            STATE_V3_EVIDENCE_GROUNDED_STATE_INTERPRETATION_APPRAISAL_PROMPT_ID
        ),
    }.get(runtime_revision, STATE_V3_APPRAISAL_PROMPT_ID)
    if runtime_revision in {
        STATE_V3_STATE_JUDGMENT_PRIMARY_RUNTIME_REVISION,
        STATE_V3_STATE_JUDGMENT_PRIMARY_CONTEXT_RUNTIME_REVISION,
    }:
        expected_calibration_profile = (
            STATE_V3_STATE_JUDGMENT_PRIMARY_CALIBRATION_PROFILE
        )
    elif runtime_revision in {
        STATE_V3_MEMORY_BOUND_SLOW_RUNTIME_REVISION,
        STATE_V3_ACTOR_MEMORY_BOUND_SLOW_RUNTIME_REVISION,
        STATE_V3_CONCISE_ACTOR_MEMORY_SLOW_RUNTIME_REVISION,
        STATE_V3_SCOPE_AWARE_ACTOR_MEMORY_SLOW_RUNTIME_REVISION,
        STATE_V3_SCOPE_NOVELTY_ACTOR_MEMORY_SLOW_RUNTIME_REVISION,
        STATE_V3_SCOPE_NOVELTY_STRENGTH_ACTOR_MEMORY_SLOW_RUNTIME_REVISION,
        STATE_V3_SAFETY_SCOPE_ACTOR_MEMORY_SLOW_RUNTIME_REVISION,
        STATE_V3_SAFETY_ELIGIBILITY_ACTOR_MEMORY_SLOW_RUNTIME_REVISION,
        STATE_V3_ADJACENT_VARIABLE_RECHECK_ACTOR_MEMORY_SLOW_RUNTIME_REVISION,
        STATE_V3_EVIDENCE_GROUNDED_STATE_INTERPRETATION_RUNTIME_REVISION,
    }:
        expected_calibration_profile = (
            STATE_V3_SLOW_PRIORITY_CAUSAL_CALIBRATION_PROFILE
        )
    elif runtime_revision == STATE_V3_DIRECTIONAL_EVIDENCE_RUNTIME_REVISION:
        expected_calibration_profile = STATE_V3_DIRECTIONAL_CALIBRATION_PROFILE
    elif runtime_revision in {
        STATE_V3_CAUSAL_RUNTIME_REVISION,
        STATE_V3_STABLE_ENVIRONMENT_OWNED_RUNTIME_REVISION,
        STATE_V3_DECISION_CONTINUITY_RUNTIME_REVISION,
        STATE_V3_EVENT_DRIVEN_RUNTIME_REVISION,
        STATE_V3_SLOW_RECALL_RUNTIME_REVISION,
        STATE_V3_SLOW_AUDIT_RUNTIME_REVISION,
        STATE_V3_SLOW_FIRST_RUNTIME_REVISION,
        STATE_V3_SEMANTIC_EVENT_RUNTIME_REVISION,
        STATE_V3_CONTRASTIVE_EVENT_RUNTIME_REVISION,
        STATE_V3_FEATURE_CONSISTENT_RUNTIME_REVISION,
        STATE_V3_BALANCED_SLOW_RUNTIME_REVISION,
        STATE_V3_OPERATIONAL_SLOW_RUNTIME_REVISION,
        STATE_V3_BOUND_SLOW_RUNTIME_REVISION,
    }:
        expected_calibration_profile = STATE_V3_CAUSAL_CALIBRATION_PROFILE
    else:
        expected_calibration_profile = STATE_V3_CALIBRATION_PROFILE
    uses_v3_component = (
        prompt_id in {
            STATE_V3_APPRAISAL_PROMPT_ID,
            STATE_V3_BEHAVIORAL_APPRAISAL_PROMPT_ID,
            STATE_V3_DIRECTIONAL_APPRAISAL_PROMPT_ID,
            STATE_V3_ENVIRONMENT_OWNED_APPRAISAL_PROMPT_ID,
            STATE_V3_CAUSAL_APPRAISAL_PROMPT_ID,
            STATE_V3_STABLE_ENVIRONMENT_OWNED_APPRAISAL_PROMPT_ID,
            STATE_V3_SLOW_RECALL_APPRAISAL_PROMPT_ID,
            STATE_V3_SLOW_AUDIT_APPRAISAL_PROMPT_ID,
            STATE_V3_SLOW_FIRST_APPRAISAL_PROMPT_ID,
            STATE_V3_FEATURE_CONSISTENT_APPRAISAL_PROMPT_ID,
            STATE_V3_BALANCED_SLOW_APPRAISAL_PROMPT_ID,
            STATE_V3_OPERATIONAL_SLOW_APPRAISAL_PROMPT_ID,

            STATE_V3_BOUND_SLOW_APPRAISAL_PROMPT_ID,
            STATE_V3_MEMORY_BOUND_SLOW_APPRAISAL_PROMPT_ID,
            STATE_V3_ACTOR_MEMORY_BOUND_SLOW_APPRAISAL_PROMPT_ID,
            STATE_V3_CONCISE_ACTOR_MEMORY_SLOW_APPRAISAL_PROMPT_ID,
            STATE_V3_SCOPE_AWARE_ACTOR_MEMORY_SLOW_APPRAISAL_PROMPT_ID,
            STATE_V3_SCOPE_NOVELTY_ACTOR_MEMORY_SLOW_APPRAISAL_PROMPT_ID,
            STATE_V3_SCOPE_NOVELTY_STRENGTH_ACTOR_MEMORY_SLOW_APPRAISAL_PROMPT_ID,
            STATE_V3_SAFETY_SCOPE_ACTOR_MEMORY_SLOW_APPRAISAL_PROMPT_ID,
            STATE_V3_SAFETY_ELIGIBILITY_ACTOR_MEMORY_SLOW_APPRAISAL_PROMPT_ID,
            STATE_V3_ADJACENT_VARIABLE_RECHECK_ACTOR_MEMORY_SLOW_APPRAISAL_PROMPT_ID,
            STATE_V3_EVIDENCE_GROUNDED_STATE_INTERPRETATION_APPRAISAL_PROMPT_ID,
        }
        or response_prompt_id in {
            STATE_V3_LEGACY_RESPONSE_PROMPT_ID,
            STATE_V3_RESPONSE_PROMPT_ID,
            STATE_V3_EARLY_OPPORTUNITY_RESPONSE_PROMPT_ID,
            STATE_V3_DECISION_CONTINUITY_RESPONSE_PROMPT_ID,
            STATE_V3_EVENT_DRIVEN_RESPONSE_PROMPT_ID,
            STATE_V3_SEMANTIC_EVENT_RESPONSE_PROMPT_ID,
            STATE_V3_CONTRASTIVE_EVENT_RESPONSE_PROMPT_ID,
        }
        or profile in {
            STATE_V3_CALIBRATION_PROFILE,
            STATE_V3_DIRECTIONAL_CALIBRATION_PROFILE,
            STATE_V3_CAUSAL_CALIBRATION_PROFILE,
            STATE_V3_SLOW_PRIORITY_CAUSAL_CALIBRATION_PROFILE,
            STATE_V3_STATE_JUDGMENT_PRIMARY_CALIBRATION_PROFILE,
        }
    )
    if standard is None:
        if explicit and uses_v3_component:
            raise ValueError(
                "v3 rollout must explicitly declare "
                f"environment.state_transition_standard={STATE_TRANSITION_STANDARD_V3!r}"
            )
        return None
    if standard != STATE_TRANSITION_STANDARD_V3:
        raise ValueError(f"unsupported state transition standard {standard!r}")
    expected = {
        "appraisal_prompt_id": expected_appraisal_prompt,
        "response_prompt_id": expected_response_prompt,
        "state_calibration_profile": expected_calibration_profile,
        "horizon_mode": "natural_max_20",
        "minimum_natural_turns": (
            10
            if runtime_revision in {
                STATE_V3_NATURAL_RUNTIME_REVISION,
                STATE_V3_EARLY_OPPORTUNITY_RUNTIME_REVISION,
                STATE_V3_BEHAVIORAL_EVIDENCE_RUNTIME_REVISION,
                STATE_V3_DIRECTIONAL_EVIDENCE_RUNTIME_REVISION,
                STATE_V3_ENVIRONMENT_OWNED_RUNTIME_REVISION,
                STATE_V3_CAUSAL_RUNTIME_REVISION,
                STATE_V3_STABLE_ENVIRONMENT_OWNED_RUNTIME_REVISION,
                STATE_V3_DECISION_CONTINUITY_RUNTIME_REVISION,
                STATE_V3_EVENT_DRIVEN_RUNTIME_REVISION,
                STATE_V3_SLOW_RECALL_RUNTIME_REVISION,
                STATE_V3_SLOW_AUDIT_RUNTIME_REVISION,
                STATE_V3_SLOW_FIRST_RUNTIME_REVISION,
                STATE_V3_SEMANTIC_EVENT_RUNTIME_REVISION,
                STATE_V3_CONTRASTIVE_EVENT_RUNTIME_REVISION,
                STATE_V3_FEATURE_CONSISTENT_RUNTIME_REVISION,
                STATE_V3_BALANCED_SLOW_RUNTIME_REVISION,

                STATE_V3_OPERATIONAL_SLOW_RUNTIME_REVISION,


                STATE_V3_BOUND_SLOW_RUNTIME_REVISION,
                STATE_V3_MEMORY_BOUND_SLOW_RUNTIME_REVISION,
                STATE_V3_ACTOR_MEMORY_BOUND_SLOW_RUNTIME_REVISION,
                STATE_V3_CONCISE_ACTOR_MEMORY_SLOW_RUNTIME_REVISION,
                STATE_V3_SCOPE_AWARE_ACTOR_MEMORY_SLOW_RUNTIME_REVISION,
                STATE_V3_SCOPE_NOVELTY_ACTOR_MEMORY_SLOW_RUNTIME_REVISION,
                STATE_V3_SCOPE_NOVELTY_STRENGTH_ACTOR_MEMORY_SLOW_RUNTIME_REVISION,
                STATE_V3_SAFETY_SCOPE_ACTOR_MEMORY_SLOW_RUNTIME_REVISION,
                STATE_V3_SAFETY_ELIGIBILITY_ACTOR_MEMORY_SLOW_RUNTIME_REVISION,
                STATE_V3_ADJACENT_VARIABLE_RECHECK_ACTOR_MEMORY_SLOW_RUNTIME_REVISION,
                STATE_V3_EVIDENCE_GROUNDED_STATE_INTERPRETATION_RUNTIME_REVISION,
                STATE_V3_STATE_JUDGMENT_PRIMARY_RUNTIME_REVISION,
                STATE_V3_STATE_JUDGMENT_PRIMARY_CONTEXT_RUNTIME_REVISION,
            }
            else 20
        ),
    }
    # The immediate-evidence runtime can stop naturally from the first turn.
    # Ten turns remains a dataset richness target, checked by the rollout Gate,
    # not a reason to force more dialogue. Keep old min=10 configs reproducible.
    if (
        runtime_revision == STATE_V3_STATE_JUDGMENT_PRIMARY_CONTEXT_RUNTIME_REVISION
        and type(environment.get("minimum_natural_turns")) is int
        and environment["minimum_natural_turns"] == 1
    ):
        expected["minimum_natural_turns"] = 1
    mismatches = {
        key: {"expected": expected_value, "actual": environment.get(key)}
        for key, expected_value in expected.items()
        if environment.get(key) != expected_value
    }
    if mismatches:
        raise ValueError(
            "state v3 runtime components are inseparable: " + repr(mismatches)
        )
    return standard


def validate_state_v3_scenario(scenario):
    """Validate the state layer needed by a v3 API rollout.

    The general scenario schema remains backward compatible. This stricter
    check is applied only when a rollout opts into the named v3 standard.
    """
    scenario_id = scenario.get("scenario_id", "<unknown>")
    if scenario.get("state_contract_version") != STATE_CONTRACT_VERSION:
        raise ValueError(
            f"{scenario_id}: state v3 requires {STATE_CONTRACT_VERSION}"
        )
    if scenario.get("state_ontology_version") != STATE_ONTOLOGY_VERSION:
        raise ValueError(
            f"{scenario_id}: state v3 requires ontology {STATE_ONTOLOGY_VERSION}"
        )

    selected = scenario.get("selected_state_variables")
    if not isinstance(selected, dict):
        raise ValueError(f"{scenario_id}: missing selected_state_variables")
    validate_v3_state_selection(selected)
    selected_paths = {
        f"{family}.{variable}"
        for family, variables in selected.items()
        for variable in variables
    }

    initial = scenario.get("initial_state")
    if not isinstance(initial, dict) or set(flatten_state(initial)) != selected_paths:
        raise ValueError(f"{scenario_id}: S0 must initialize every selected state")
    values = list(flatten_state(initial).values())
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 1 <= value <= 9
        for value in values
    ):
        raise ValueError(f"{scenario_id}: state v3 S0 values must be numeric in [1, 9]")
    if len(set(values)) < 4:
        raise ValueError(f"{scenario_id}: state v3 S0 needs four distinct levels")

    targets = scenario.get("target_state_ids")
    if (
        not isinstance(targets, list)
        or not 6 <= len(targets) <= 9
        or len(targets) != len(set(targets))
        or not set(targets).issubset(selected_paths)
        or {path.split(".", 1)[0] for path in targets} != set(selected)
    ):
        raise ValueError(
            f"{scenario_id}: state v3 targets must be 6-9 selected paths "
            "covering all four families"
        )

    notes = scenario.get("initialization_notes") or {}
    rationale = notes.get("rationale") or {}
    for family, variables in selected.items():
        family_rationale = rationale.get(family)
        if not isinstance(family_rationale, dict) or set(family_rationale) != set(variables):
            raise ValueError(
                f"{scenario_id}: every {family} S0 variable needs its own rationale"
            )
        if any(
            not isinstance(text, str) or not text.strip()
            for text in family_rationale.values()
        ):
            raise ValueError(
                f"{scenario_id}: every {family} S0 rationale must be non-empty"
            )

    plan = notes.get("state_transition_plan")
    if not isinstance(plan, dict) or set(plan) != selected_paths:
        raise ValueError(
            f"{scenario_id}: bidirectional transition plan must cover every state"
        )
    for path, directions in plan.items():
        if not isinstance(directions, dict) or set(directions) != {
            "increase_evidence", "decrease_evidence"
        }:
            raise ValueError(f"{scenario_id}: invalid transition plan for {path}")
        increase = directions["increase_evidence"]
        decrease = directions["decrease_evidence"]
        if (
            not isinstance(increase, str)
            or not increase.strip()
            or not isinstance(decrease, str)
            or not decrease.strip()
            or increase.strip() == decrease.strip()
        ):
            raise ValueError(
                f"{scenario_id}: {path} needs distinct non-empty evidence directions"
            )

    timescale_overrides = notes.get("state_timescales") or {}
    if not isinstance(timescale_overrides, dict):
        raise ValueError(f"{scenario_id}: state_timescales must be an object")
    unknown_timescales = set(timescale_overrides) - selected_paths
    if unknown_timescales:
        raise ValueError(
            f"{scenario_id}: state_timescales contains unselected paths "
            f"{sorted(unknown_timescales)}"
        )
    invalid_timescales = {
        path: value for path, value in timescale_overrides.items()
        if value not in VALID_TIMESCALES
    }
    if invalid_timescales:
        raise ValueError(
            f"{scenario_id}: invalid state_timescales {invalid_timescales!r}"
        )
    semantics = build_state_semantics(scenario)["variables"]
    relationship_timescales = {
        semantics[f"relationship.{variable}"]["timescale"]
        for variable in selected["relationship"]
    }
    if "turn_to_episode" not in relationship_timescales:
        raise ValueError(
            f"{scenario_id}: state v3 needs a turn-responsive relationship variable"
        )
    if "cross_turn_slow" not in relationship_timescales:
        raise ValueError(
            f"{scenario_id}: state v3 needs a genuinely slow relationship variable"
        )
    return scenario
