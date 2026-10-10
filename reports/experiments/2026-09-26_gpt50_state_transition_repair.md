# GPT50 Gate 2 state-transition repair record

Date: 2026-09-26 UTC

## Status and scope

- Gate 2 environment replay is paused. The old-contract partial output is
  preserved: 19 attempt records, 9 successful scenarios, 10 recorded errors.
- Claude150 rollout is paused at 97/150. A checked pause sentinel prevents the
  repository launcher from restarting it without an explicit decision.
- No model calls were made for this audit or the human-review packet.
- No post-fix rollout has been claimed. The existing 31 accepted trajectories
  remain diagnostic pre-fix evidence and contain zero exact-20-turn runs.

## Root causes and evidence

The problem is not a shortage of state slots. The accepted cohort contains 245
scenario-variable slots; 29/31 scenarios already use the maximum eight selected
variables. The missing layer was operational semantics and evidence binding.

1. The v11 appraisal contract did not require evidence_feature or evidence_span
   on state candidates, while calibration ranked candidates using those fields.
   All 982 saved candidates therefore used an inferred feature. Of these, 849
   were assigned goal_alignment by the fallback rather than by variable-specific
   evidence.
2. The fallback created ranking artifacts. Eighty turns had an inferred tie at
   the top rank; the lexicographically first variable won 64/80 times.
3. Sparse update budget was consumed by bounded no-ops. Of 312 selected state
   candidates, 167 requested increase from a current value of 10 and applied
   zero. Every selected numeric no-op in the accepted cohort has this form.
4. The configured strong-event extra budget was unreachable in the saved
   evidence: calibrated levels were 372 level-0, 353 level-1, 257 level-2, and
   zero level-3. The old sensitivity rule expected numeric persona fields, while
   the v2 persona contract uses textual values/temperament/style fields.
5. Scenario initialization rationale existed for every selected variable
   (221 variable-specific and 24 family-level fallbacks), but runtime appraisal
   received only state names and numbers. There were zero per-variable runtime
   transition specifications.
6. The resulting transition process was strongly asymmetric:
   - 2,376/2,521 labels unchanged (94.25%);
   - 173/245 scenario-variable series never changed (70.61%);
   - emotion: 0/437 applied changes;
   - relationship: 3/587;
   - consequence risk: 8/728;
   - behavioral disposition: 134/769;
   - applied direction: 140 increases versus 5 decreases;
   - selected-to-applied rate fell from 91.49% in the early third to 17.07% in
     the late third as upward-selected variables saturated.

These figures are computed only on the 31 accepted trajectories. The population
counts 31 accepted, 15 rejected, and 4 generation errors are retained as cohort
provenance but are not mixed into the state percentages.

## Code and contract changes

- Added a canonical operational ontology for all 32 approved state variables:
  definition, increase evidence, decrease evidence, non-evidence, family
  timescale, and persistence/update guidance.
- Runtime appraisal now receives the selected ontology entries plus the
  scenario-specific initialization rationale. The rationale is explicitly
  marked as starting-value context, not current transition evidence.
- environment_appraisal_v12 requires every state/dynamics candidate to bind to
  one exact latest-action span and one explicit event feature.
- Gate 2 now uses evidence_bound_sparse_v2:
  - ordinary state budget remains one;
  - no threshold is relaxed;
  - independent evidence is mandatory;
  - relationship and consequence-risk remain slow evidence dimensions;
  - only a direct strength-2 event can reach the already-existing strong-event
    extra budget;
  - a 0/10 outward no-op cannot consume the event budget.
- GPT50 rollout/T4 and Claude/general T4 configs use the same evidence-bound
  sparse path. No rollout was restarted.
- Added a reproducible accepted-cohort audit and a 31-scenario/245-variable
  human review packet. Every human field is pending and human_attestation is
  false.
- Refreshed the Gate 2 manifest in prepare-only mode with zero network calls.
  It binds both artifacts by SHA-256, records thresholds_relaxed=false, marks
  the trajectories as pre-fix evidence only, and remains blocked on exact-20
  plus human/post-fix evidence.

## Verification

- 135 relevant state, prompt, environment, Gate 2, T4, and quality-gate tests
  pass.
- The ontology resolves all selected variables in all 50 GPT scenarios:
  394 selections, 6-8 variables per scenario.
- Prompt checksum loading and patch formatting checks pass.
- Claude launcher exits at the pause sentinel before any provider call.

## Evidence files

- Offline accepted-cohort audit:
  reports/experiments/2026-09-26_gpt50_state_transition_audit.json
- Human review packet:
  data/gpt50/experiment/gate2/human_review/state_transition_ontology.json
- Audit generator:
  scripts/audit_state_transition_ontology.py
- Review-packet generator:
  scripts/prepare_state_transition_review.py

## Required next steps

1. Human reviewers must evaluate construct relevance, direction anchors,
   non-evidence boundaries, timescale, and initial values for all 245 entries;
   revise/remove decisions remain pending.
2. After ontology sign-off, run a versioned fixed-input pilot across all four
   state families. Report appraisal agreement, calibration activation,
   boundary suppression, and applied deltas separately.
3. Only if the pilot shows reasonable causal directions should the full
   accepted cohort be regenerated to exactly 20 turns and Gate 2 E1/E3-E7/E9
   rerun. Old partial successes cannot be merged into post-fix evidence.
4. E4/E6 must retain active-union and both-active metrics; zero-zero agreement
   remains diagnostic only. E6 service failures stay in the required-run
   denominator and remain a hard blocker.
