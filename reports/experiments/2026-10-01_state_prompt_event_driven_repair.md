# 2026-10-01 State prompt event-driven repair

Status: design and implementation target frozen; scale remains blocked on a small multi-scenario v3.2.9 native pilot and human review. No Gate threshold, calibration threshold, state delta, or accepted-sample denominator was altered.

## Decision

Fixed turn scheduling is removed from the active candidate. The Environment response model receives state-observability context without a turn cadence and decides from current public semantic events whether one non-leading issue is naturally relevant. Actual state remains owned by appraisal -> deterministic calibration -> state update. Response prompts cannot write a delta.

The frozen cross-pool implementation target is runtime v3.2.9:

- appraisal: `environment_appraisal_v23_feature_consistent_slow_first`
- calibrator: unchanged `evidence_causal_hysteretic_v5`
- response: `environment_response_v31_contrastive_event_driven`
- opportunity profile: `state_transition_opportunity_event_driven_v6`
- horizon: unchanged natural 10-20, maximum 20
- multimodal policy: unchanged `online_multimodal_v2`

The freeze applies to both GPT and Claude scenario pools. S0 owns the complete
variable set, initial values, timescales, and bidirectional evidence plans.
Runtime candidates are evidence hypotheses for those existing variables only;
they never add or choose state variables. This freezes the design decision, not
the empirical outcome: v3.2.9 remains ineligible for scale until the retained
native pilot and human review complete.

## Root causes and evidence

1. Sparse fixed turns delayed slow evidence. The v3.2.2 GPT50_001 retained rollout ended naturally at t11; its first open probe appeared at t8 and its only slow candidate appeared at t9, with no second independent event before close. Metrics: 11 turns, 88.64% unchanged labels, 16.67% all-time-static variables, all four families changed, 11 fast changes, 0 slow changes.
2. Removing cadence alone was insufficient. The v3.2.3 GPT50_002 retained rollout was coherent and changed all four families but produced 0 slow candidates/changes across 10 turns. Its authored trust plan explicitly named functional disclosure, collaborative planning, and acceptance of an interim bounded plan, while appraisal repeatedly selected responsiveness and did not emit trust. Metrics: 90.83% unchanged labels, 41.67% all-time-static variables, 9 fast changes, 0 slow changes.
3. Slow candidate recall was crowded out by turn-responsive relationship candidates. Fixed-input v3.2.4/v3.2.5 probes did not emit trust even for a synthetic action containing all authored trust components. V3.2.6 changed only candidate ordering: slow paths are audited first and reserve one of two relationship candidate slots only when current exact evidence and a compatible feature exist.
4. Abstract construct definitions were not enough for natural response construction. V3.2.7/v3.2.8 supplies both authored evidence patterns after deterministically removing their outcome/direction clause. V31 uses them only to recognize a currently grounded contrastive issue; it forbids revealing direction, copying patterns, inventing logistics, or scheduling by turn.
5. One v3.2.8 t2 appraisal emitted a trust candidate citing `repair_signal` while the same appraisal set `repair_signal=0`. The unchanged calibrator correctly suppressed it. V3.2.9 now rejects this self-contradictory structured output so the model must rewrite or omit it. It never changes 0 to non-zero in code. The fixed t2 probe completed with the invalid trust candidate omitted and all remaining cited features non-zero.

## Native rerun result

The single first-pass v3.2.8 GPT50_002 rollout was retained regardless of outcome and machine-passed:

- trajectory: `72ebf1e6863549ce90ae8e2e2cdd9bdc`
- natural turn count: 10
- selected states: 12; labels: 120; unchanged: 109 (90.83%)
- all-time-static variables: 5/12 (41.67%)
- family changes: consequence risk 4, behavioral disposition 3, emotion 1, relationship 3
- fast changes: 6
- slow changes: 1; compliant slow changes: 1
- false changes: 0; feature mismatches: 0; family cap violations: 0; boundary values: 0
- all State-v3 machine requirements: passed
- human review: pending

The slow change occurred at t3, not on a scheduled opportunity. T2 disclosed the privacy-bounded functional need; the Environment proposed an interim exam-week plan with later committee review. T3 explicitly adopted that bounded plan. Appraisal recorded direct `commitment_signal=2` evidence and the unchanged calibrator classified it as decisive, applying `relationship.trust +2`. The opportunity context then became inactive for all later turns.

Structural hard checks all passed. One diagnostic-only action-template detector emitted `repayment_followup_refrain` in a school-accommodation dialogue; this is a likely detector-label false positive and was not a hard rejection.

## Attempt accounting

- v3.2.3 GPT50_001: two retained generation errors, both at t2 appraisal structured validation; neither is counted as a valid rollout.
- v3.2.3 GPT50_002: one retained 10-turn machine rejection, slow change absent.
- v3.2.8 GPT50_002: one retained 10-turn first-pass machine acceptance.
- v3.2.9: fixed-input feature-consistency probe completed; no full native rollout has yet been claimed.

## Verification

- 111 focused runtime/prompt/environment tests passed for v3.2.8.
- 101 focused appraisal/runtime/environment tests passed for v3.2.9.
- readiness check loaded all 50 frozen GPT scenarios with zero network requests.
- post-freeze regression rerun: 161 focused tests passed; GPT50 readiness again reported 50/50 scenarios and zero network requests.
- fixed-input and synthetic probes are explicitly marked diagnostic-only, not Gate evidence, and human review remains pending.

## Remaining before scale

1. Run a small pre-registered multi-scenario native v3.2.9 pilot; keep all generation errors and machine rejections in the denominator.
2. Confirm ordinary (two-event) slow changes as well as decisive one-event changes; the current accepted sample demonstrates only the decisive path.
3. Sample negative-direction slow evidence to ensure slow-first recall is not directionally biased.
4. Inspect the diagnostic template-loop false positive and response retries; do not relax any Gate threshold.
5. Complete human review. Model review must not be reported as human review.
