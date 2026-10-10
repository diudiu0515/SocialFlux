# SocialFlux State Transition Standard v3

Status: design-frozen on 2026-10-01. Applies equally to GPT and Claude scenario
pools. Runtime v3.2.9 is the frozen implementation target; scale approval still
requires the pre-registered native pilot and human review described below.
Replaces the draft rule that selected exactly eight state variables.

## 0. Frozen interpretation

S0 fixes the complete mutable state space for the trajectory: all selected
variables, their initial values, their per-variable timescales, construct
definitions, and bidirectional evidence plans. Runtime never selects, adds,
removes, or swaps state variables.

A per-turn `state_impact` or "candidate" is only an evidence hypothesis about
one of those already-selected S0 variables. It is not a candidate state
variable and it is not itself a state change. Appraisal may emit it only from
the current observable event; deterministic calibration alone decides whether
the evidence is sufficient to apply a delta.

This interpretation is frozen. Neither a missing slow transition nor a failed
trajectory authorizes fixed turn windows, a preselected runtime path or
direction, synthetic evidence, forced deltas, relaxed thresholds, or
successful-sample selection.

## 1. State shape at S0

Every scenario uses exactly four mutable state families owned by the
environment character:

| Family | Required selected variables | Typical timescale |
|---|---:|---|
| emotion | 3-4 | fast |
| behavioral_disposition | 2-3 | fast to medium |
| relationship | 2-3 | variable-specific medium or slow |
| consequence_risk | 2-3 | event-responsive medium |

Thus S0 contains 9-13 variables, normally 10-11. Every selected variable must:

- have a numeric S0 value and its own environment-character rationale;
- use a grounded value in [1, 9], with extremes reserved for exceptional facts;
- have distinct scenario-reachable increase and decrease evidence;
- remain conceptually distinct from the other selected variables.

Emotion selection must cover distinct affective functions rather than near
synonyms: threat, obstruction/loss, approach/recovery, and optionally
self-evaluative or social affect.

Each scenario should include at least one turn-responsive relationship state
when appropriate, such as perceived responsiveness, fairness, safety, or role
legitimacy, and at least one genuinely slower relational construct when the
scenario can expose relevant evidence. Trust is not a default.

## 2. Ownership and evidence

Mutable state always describes environment_agent, never evaluated_agent.
The evaluated participant's action is causal evidence, not the state owner.

Ownership is checked separately for each family:

- emotion is felt by the environment character;
- behavioral disposition is the environment character's readiness to act;
- relationship is the environment character's belief about the evaluated
  participant. In particular, role legitimacy is not the environment
  character's view of their own authority, responsiveness is not the
  environment character's response to the evaluated participant, and safety
  is not whether the evaluated participant is safe from the environment;
- consequence risk is the environment character's assessment of exposure to
  their own goal, standing, autonomy, material position, safety, relationship,
  or a relevant institution. The person at risk cannot silently switch to the
  evaluated participant.

Reauthoring evidence plans must preserve runtime order. Every planned cause is
a newly observed evaluated-participant action or a fact supplied by that
action before appraisal and state update. A later environment response cannot
serve as evidence for the state update that precedes it.

No-change is the default. Every applied update requires:

1. a non-empty exact evidence span from the current observable event;
2. an evidence feature approved for that variable;
3. semantic novelty rather than a paraphrase or repeated reason;
4. a direction supported by that variable's increase/decrease definition;
5. an available cross-family update budget.

One utterance, clause, or exact evidence span may support multiple state
candidates when it has genuinely different, variable-specific causal
consequences for the environment character. Each candidate must independently
satisfy the construct definition, direction, evidence feature, and ownership
test. A generic cooperation, respect, threat, or commitment signal cannot be
mechanically cloned across loosely related states, and one state cannot change
merely because a correlated state changed. The ordinary/decisive cross-family
budgets remain unchanged.

## 3. Fast and slow transitions

Timescale is defined per variable, not solely per family. Every relationship
variable has an explicit ontology default. A scenario may override a selected
variable through `initialization_notes.state_timescales`; the validator applies
the effective per-scenario value and still requires at least one
turn-responsive and one genuinely slow relationship construct.

- Fast variables may update on one direct novel event.
- Medium variables update on a concrete new decision, disclosure, constraint,
  mitigation, or performed interactional move.
- Slow variables update after either one verified decisive event or two
  independent consistent evidence events across turns.

There is no automatic decay, forced oscillation, forced coverage, or
state change inserted to satisfy a metric.

An ordinary event may apply at most two independently supported cross-family
updates. A decisive event may apply at most three. Per-family caps still apply.

Appraisal v15 may expose up to two relationship candidates when they target
different variables and use distinct verbatim evidence spans. This is a
candidate-recall allowance so a turn-responsive construct cannot hide an
independently supported slow construct. It does not change the calibrator:
at most one relationship update may be applied in a turn, and the ordinary
two-update budget plus the slow-evidence rule remain binding.

The private appraisal payload includes each selected variable's
scenario-specific increase/decrease examples from `state_transition_plan`.
These examples guide construct matching only: they are never treated as
observed evidence, and every candidate still needs a substantively matching
exact span from the current evaluated action. Before applying candidate caps,
the appraiser independently checks every selected state path so a salient
construct cannot silently hide another supported family.

## 4. Anti-convergence

Repeated promises, reasons, cooperation signals, respectful phrasing,
pressure, or stylistic paraphrases do not accumulate as fresh evidence.

Routine same-direction evidence reaches a reinforcement plateau at two points
from S0. Further outward movement requires decisive new evidence. Values 0 and
10 are never reached through routine reinforcement. A reversal requires fresh
contrary evidence.

The following are separately audited:

- duplicate-evidence accumulation;
- multiple variables moved by one evidence span;
- unrelated variables moving from a generic feature;
- final-state concentration at 0 or 10;
- one-sided direction imbalance across the population;
- pairwise co-movement not justified by independent evidence.

## 5. Correctness and realization coverage

State correctness and trajectory coverage are separate outputs. Correctness
requires that every applied delta has eligible variable-specific evidence,
respects direction, ownership, timescale, boundaries, family caps, and update
budgets. No relevant evidence therefore makes persistence the correct result.

For a naturally ending 10–20-turn trajectory, the following remain dataset
richness targets rather than per-trajectory correctness gates:

- all four families realize at least one non-zero update;
- at least one fast transition occurs from direct novel evidence;
- at least one slow transition satisfies the slow-evidence rule.

A trajectory with correct updates but insufficient opportunities is reported as
`coverage_sufficient=false`; it is not labeled a state-transition error and is
not repaired by forcing a delta. Dataset-level sampling may seek additional
coverage, while retaining every attempt and without selecting only trajectories
that happened to change.

## 6. Metrics

Raw label invariance remains reported but is not used alone. With ten state
variables over twenty turns, ten legitimate updates still imply 95% unchanged
state labels.

Gate evidence therefore reports all of:

- raw unchanged labels / all labels;
- all-time-static scenario-variable series;
- family-level realized transition coverage;
- evidence-conditioned response rate;
- no-evidence false-change rate;
- fast-transition latency;
- slow-transition evidence compliance;
- duplicate-evidence suppression;
- direction correctness;
- boundary concentration;
- per-variable and per-family update distributions.

E4/E6 continue to report union-of-changed and both-changed subsets separately.
Zero-zero agreement is never allowed to hide changed-item instability.

## 7. Review and rollout policy

State reauthoring is model-assisted and remains human_review=pending until a
human approves ownership, construct selection, S0 values, bidirectional
evidence plans, and trigger compatibility.

GPT and Claude use the same ontology, calibrator, validation rules, and Gate
metrics. Their scenario state layers are versioned separately, and old rollout
evidence remains frozen rather than overwritten.

Every v3 API rollout must explicitly declare
`socialflux_state_transition_standard_v3`. Each runtime revision is
inseparably bound by the runtime validator to its declared appraisal prompt,
response prompt, calibration profile, and horizon contract; mixing components
from different revisions fails before provider construction. Runtime v3.0/v3.1
remains frozen as historical exact-20 evidence. Runtime v3.2 uses
`environment_response_v27`, the natural 10–20 contract, and optional
opportunities at turns 6, 10, 14, and 18.

Runtime v3.3 uses `environment_response_v28` with the same unchanged
calibrator and Gate thresholds. Its optional opportunities occur at turns 4,
7, 10, 13, 16, and 19 so a rollout that naturally ends at turn 10 has two
opportunities that can still influence a later evaluated action. When no slow
candidate exists, the early opportunities rotate eligible slow constructs;
when an unresolved candidate exists, the next opportunity uses a different
non-leading public situation or trade-off for the same construct.

Runtime v3.4 keeps the v3.3 response opportunity cadence, calibration
profile, state budgets, and Gate thresholds unchanged, but binds
`environment_appraisal_v16`. V16 requires every impact to cite a compatible
non-zero event feature and explicitly audits observable behavioral readiness
such as executable choices, disclosure commitments, verification requests,
and enforced boundaries. This repairs missed behavioral evidence; it does not
require a behavioral candidate, force family coverage, or turn an unsupported
utterance into a state change. Old v3.2/v3.3 evidence remains frozen.

Runtime v3.5 and `environment_appraisal_v17` are frozen as failed diagnostic
artifacts. They improved recall on a small behavioral sample but could treat
the evaluated participant's self-description (for example, willingness to
disclose) as if it directly described the environment character's own
disposition. V3.5 is not approved for native rollout or Gate evidence.

Runtime v3.6 and `environment_appraisal_v18` are frozen as a second failed
diagnostic. They made state ownership explicit, but fixed-sample evidence still
mirrored evaluated-agent disclosure and evidence seeking into the Environment
character's behavioral disposition. V3.6 is not approved for native rollout or
Gate evidence.

Runtime v3.7 is the current repair candidate. It binds
`environment_appraisal_v19`, `environment_response_v28`, and
`evidence_causal_hysteretic_v5`. The appraiser must first name the mutable
state owner (`environment_agent`) and event producer (`evaluated_agent`),
then establish a scenario-specific causal bridge to the Environment
character's next behavior. Explicit evaluated-agent self-description cannot be
mirrored across agents. A single utterance or exact span may nevertheless
support multiple distinct Environment effects when every variable has its own
valid causal mechanism. V3.7 retains the v3 ordinary/decisive update budgets,
feature thresholds, timescale rules, anti-convergence rules, and 10--20-turn
horizon.

Runtime v3.2.1 freezes the stable environment-owned appraisal and causal
calibrator repair. Runtime v3.2.2 adds decision/commitment continuity to the
response and evaluated-policy prompts while retaining the earlier sparse
opportunity cadence. Both remain reproducible historical candidates.

Runtime v3.2.3 is the event-driven opportunity candidate. It binds
`environment_appraisal_v15_environment_owned`,
`evidence_causal_hysteretic_v5`, and
`environment_response_v29_event_driven`. It has no configured opportunity
turns and does not preselect a state path or direction. Until a compliant slow
transition is realized, the response model receives a private neutral menu of
eligible slow constructs and unresolved-candidate counts on every turn. The
model may surface at most one non-leading issue only when that issue already
follows naturally from the latest action, public history, active commitments,
state/dynamics, persona, or goal; otherwise it must ignore the menu and may
close normally. Authored increase/decrease examples are not supplied to this
response prompt. Once any compliant slow transition is realized, the private
opportunity context is disabled.

Runtime v3.2.4 and v3.2.5 are frozen diagnostic prompt attempts. Fixed-input
probes showed that they still allowed turn-responsive relationship candidates
to crowd out a supported slow trust candidate, including on a synthetic
decisive action. They are not scale candidates.

Runtime v3.2.6 binds `environment_appraisal_v22_slow_first`. Appraisal first
checks every slow construct against current exact words and scenario-specific
evidence, then reserves one relationship candidate slot only when slow evidence
is actually supported. Candidate recall remains distinct from state change; the
unchanged calibrator still applies decisive-or-two-independent-evidence rules.

Runtime v3.2.7 adds direction-neutral scenario evidence patterns to the
event-driven response context. Runtime v3.2.8 binds
`environment_response_v31_contrastive_event_driven`: when a public semantic
event makes a slow construct relevant, Environment may raise one grounded,
non-leading contrastive choice. It must not invent logistics, expose a state
direction, use a fixed turn schedule, or keep probing after a compliant slow
transition. A single retained GPT50_002 pilot passed all machine State-v3
realization checks; this is development evidence, not permission to scale or a
substitute for human review.

Runtime v3.2.9 is the frozen implementation target for both GPT and Claude. It
retains the v3.2.8 response and unchanged calibrator, and binds
`environment_appraisal_v23_feature_consistent_slow_first`. Each impact's cited
evidence feature must be non-zero in the same appraisal. Invalid output is
rejected for model rewrite or candidate omission; Python never promotes a zero
feature, creates evidence, or inserts a delta. Full multi-scenario validation
remains required before scale. Until that validation completes, "frozen
implementation target" must not be reported as "scale-approved" or as a
completed rollout migration. Further prompt or threshold changes require new
retained failure evidence; ordinary pilot variance is handled as measurement,
not by redesigning the state contract.

All opportunity profiles are private construction aids. The earlier direction
is not disclosed, examples are never observations, and the evaluated
participant may support, contradict, or leave the construct ambiguous. A slow
update still requires one decisive event or two independent consistent events.
No state delta is forced and no threshold is relaxed. A configuration mismatch
fails before provider construction and therefore before any API request.

Runtime provenance records the causal stage order as evaluated action →
environment appraisal → deterministic calibration → environment state update
→ environment response. At trajectory completion, Section 5 requirements are
recorded in `state_v3_metrics`. An under-realized trajectory remains a failed
evidence item; the runtime never adds a delta, relaxes a threshold, or silently
promotes it to accepted.

Runtime v3.2.23 is the state-judgment-primary repair candidate. It keeps the
v3.2.22 prompts, numeric delta mapping, per-turn budgets, family caps,
anti-convergence rule, and natural horizon. The per-variable state judgment is
the sole semantic eligibility source: dialogue diagnostics and deterministic
surface-duplicate detection are interaction diagnostics only, while generic
event features remain logged as auxiliary interface diagnostics and cannot veto
a supported variable-specific judgment. Decisive evidence is a direct exact
span labeled decisive by the state appraisal. Ordinary slow evidence uses the
current turn event ID, is consumed after an update, and pending evidence in the
opposite direction is cleared. V3.2.23 also separates update-integrity admission
from realization coverage; neither status is a substitute for human semantic
review or scale approval.
