# State v3 repair status — GPT50 and Claude150

## Scope

The confirmed design standard is recorded in:

- docs/protocols/STATE_TRANSITION_STANDARD_V3.md
- DESIGN_CONTRACT.md section 4

The old GPT and Claude rollout pools remain frozen. They are evidence of the
pre-v3 state design and are not eligible to be mixed into a v3 run.

## Full-population readiness audit

Machine-readable evidence:
reports/experiments/2026-09-27_state_v3_readiness_audit.json

### GPT50

- 50/50 scenarios require state-layer reauthoring.
- 45 scenarios select eight states, four select seven, and one selects six.
- Emotion coverage is below v3 in all scenarios: 33 select one emotion and 17
  select two.
- Nine scenarios select only one relationship state.
- All 50 lack a turn-responsive relationship construct under the v3 ontology.
- Ten target sets do not cover all four families.
- Six S0 assignments use fewer than four distinct numeric levels.
- Conservative actor-ownership triage flags nine scenarios for review.
- Selection is highly concentrated: trust appears in 49/50 scenarios and
  anxiety in 45/50; trust is a task target in 44/50.

### Claude150

- 150/150 scenarios require state-layer reauthoring.
- Every scenario selects exactly eight states and exactly two emotions, below
  the confirmed 3–4 emotion requirement.
- All 150 lack a turn-responsive relationship construct under the v3 ontology.
- Seventy target sets do not cover all four families.
- Target count is below six in 149/150 scenarios.
- Five S0 assignments use fewer than four distinct numeric levels.
- Two scenarios lack a variable-specific rationale in the old representation.
- Conservative actor-ownership triage flags 12 scenarios for review.
- Selection is highly concentrated: trust appears in 148/150 scenarios and
  anxiety in 145/150; trust is a task target in 140/150.

The actor heuristic is intentionally conservative and is not an exhaustive
ownership check. Manual inspection already confirms additional failures it did
not flag. In CF150_001, the environment character is Raymond Moss but the S0
rationales describe Yuki's preserved files, visa vulnerability, prior
non-disclosure, and willingness to testify. In CF150_003, several rationales
likewise describe the evaluated subordinate while the environment character is
the supervisor. These records must be reauthored rather than patched by scalar
adjustment.

## Transition evidence motivating v3

Across the completed pre-v3 repaired rollouts available at audit time:

- relationship.trust changed zero times in both GPT and Claude samples;
- GPT final S0 paths reached 0/10 in 30.56% of observed scenario-variable
  endpoints, led by repeated cooperation, evidence-seeking, and boundary
  reinforcement;
- Claude final endpoints reached 0/10 in 12.04%;
- repeated generic signals caused some behavioral states to move repeatedly in
  one direction, while slow relationship and risk states often never moved.

This is why v3 changes both selection and calibration. Merely adding variables
or increasing the update budget would not address ownership, evidence
specificity, or convergence.

## Implemented locally

- Four-family S0 standard: emotion 3–4; behavioral, relationship, and risk 2–3
  each; total 9–13 and normally 10–11.
- Five additional approved constructs:
  decision_readiness, perceived_responsiveness, role_legitimacy,
  decision_error_risk, and autonomy_loss_risk.
- Per-variable evidence-feature compatibility.
- Per-variable timescales, including turn-responsive relationship states.
- V3 calibration with two ordinary cross-family updates and at most three on a
  decisive event.
- Slow-state rule: one decisive event or two independent consistent events.
- Anti-convergence reinforcement plateau and boundary protection.
- State-only reauthoring contract that keeps public scenario content frozen,
  requires owner/path/value-bound S0 rationales, evaluated-action-to-
  environment-state causal evidence plans, and regenerated trigger metadata.
- Deterministic reauthoring checks now reject family-owner inversion,
  relationship-direction inversion, post-update evidence, incomplete evidence
  plans, abbreviated actor names, and malformed trigger expressions.
- Rejected generation attempts retain their raw validation diagnostics in the
  batch manifest; semantic pilot failures are versioned under
  rejected_evidence rather than counted as passes.
- Human review remains pending; no model-generated state layer is labeled as
  human-approved.
- The API rollout runtime now has an explicit v3 contract binding appraisal
  v13, hysteretic calibration v3, the exact 20-turn horizon, and the causal
  action→appraisal→calibration→state-update→response stage order. Mismatches
  fail before provider construction.
- GPT and Claude launchers now use versioned `scenarios_state_v3`,
  `rollout.state_v3.json`, and `rollouts_state_v3` paths. They require a real
  signed state review registry and leave Gate/video downstream stages disabled
  by default.
- Exact-20 trajectories are machine-checked for realized changes in all four
  families plus at least one fast and one compliant slow change. Under-realized
  trajectories remain failed denominator evidence; no delta is fabricated.

The current state/runtime/metrics/prompt regression subset passes: 77 tests.

## Pilot evidence after explicit API authorization

The user explicitly authorized sending the complete GPT50/Claude150 scenario
payloads to https://www.autodl.art for state-only reauthoring. Video generation
and old rollouts remain paused.

Claude CF150_001 exposed four successive contract defects during the pilot:

1. abbreviated environment name instead of the exact actor name;
2. evidence plans covering targets rather than every selected variable;
3. string-valued trigger expressions instead of schema objects;
4. deeper owner inversion that passed structural validation: behavioral plans
   described the evaluated participant's readiness, relationship states were
   reversed, and risk sometimes changed the person at risk.

The first three are retained in manifest validation diagnostics. A structurally
valid but owner-inverted artifact is retained at
data/claude150_v1/scenarios_state_v3_pilot/rejected_evidence/owner_inversion_v1.
It is not a successful sample.

The first GPT50_001 request used the earlier contract, took roughly half an
hour across failover candidates, and failed all four schema attempts. Because
that process predated diagnostic persistence, its generic failure manifest is
retained under rejected_evidence/old_contract_no_diagnostics. A later GPT
diagnostic returned a semantically strong candidate with three explicit format
errors (leaf paths in selection, one initially active trigger, and missing
relationship owner clauses); its raw output and reasons are retained under
rejected_evidence/leaf_prefix_and_trigger_v1. A subsequent request saw all six
GPT routes time out at 300 seconds and is retained under
rejected_evidence/all_six_transport_timeout_v1. The GPT state-author route is
therefore not reliable enough for a 50-scenario construction job.

State authoring is configuration construction rather than the evaluated
rollout backbone. Both pools now use the same claude-fable-5 authoring route,
prompt, ontology, and deterministic validator; GPT50 rollouts remain GPT and
Claude150 rollouts remain Claude. The dedicated route fixes the provider to the
chat candidate that returned valid pilot outputs, avoiding the generic route's
rotation into repeatedly timing-out protocol/credential pairs. Every artifact
records the authoring model and route hash.

Final-contract generalization samples now pass deterministic validation and
manual semantic spot-checks:

- GPT50: 3/3 candidates; every candidate has 12 states (3 per family), five
  distinct S0 levels, 8-9 targets covering all four families, and 24 complete
  owner/direction-bound evidence routes.
- Claude150: 3/3 candidates; every candidate has 12 states (3 per family),
  respectively 6, 5, and 7 distinct S0 levels, 8-9 targets covering all four
  families, and 24 complete evidence routes.

Transport failures during this sample were recorded in the batch denominator
and retried only by scenario ID through resume; no replacement scenario was
sampled. All six current candidates remain human_review=pending.

An optional model semantic triage packet was also tested. It produced several
clear false positives after explicit temporal correction, so it is retained as
reviewer suggestions only. It is not a release gate, not ground truth, and not
human review.

Full state-only reauthoring started at 2026-09-27T08:14:36Z in tmux session
state_v3_reauthor. It runs GPT50 first and Claude150 second with one request at
a time. Up to five resume passes are allowed; every pass manifest is archived.
On complete coverage it writes unsigned scenario review registries with all
human fields pending. Video and rollout generation remain disabled.

## Not yet complete

The full-population candidate job is still running. No v3 exact-20 rollout has
started, and neither backbone has passed the small rollout pilot yet.

The remaining order is:

1. finish all 50+150 versioned state candidates and unsigned human-review
   packages;
2. audit the complete machine-valid population for selection diversity, S0
   concentration, owner markers, trigger reachability, and failure coverage;
3. run a small exact-20-turn pilot
   for both backbones;
4. inspect family transition coverage, false changes, slow evidence compliance,
   and boundary concentration;
5. keep human approval pending until an actual human completes it.
