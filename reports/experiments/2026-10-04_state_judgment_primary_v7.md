# State judgment primary v7 repair

Status: implementation and deterministic validation complete; eight human labels confirmed; the original fixed set and the single allowed prompt correction both failed the gate; unseen validation, trajectory generation, and scale remain stopped.

## Changes

- Added calibration profile `state_judgment_primary_hysteretic_v7` and runtime binding `v3.2.23`; v6 remains frozen.
- Per-variable state judgments now determine semantic eligibility and ordinary/decisive strength. Dialogue diagnostics and same-speaker surface-duplicate IDs are recorded but cannot veto v7 state or dynamics updates.
- Generic event features are auxiliary diagnostics. A new-evidence judgment may set `evidence_feature` to null when no generic feature accurately represents the variable-specific evidence.
- Fixed legacy global-suppression diagnostics so `selected`, `selection_reason`, `suppressed_by`, and `final_delta` agree with the applied delta.
- Slow evidence now uses the current turn event ID, consumes pending consistent evidence after an update, and clears pending evidence in the opposite direction.
- Every relationship variable has an explicit default timescale, and `initialization_notes.state_timescales` can override selected variables per scenario under validator checks.
- Split state-update correctness from trajectory realization coverage. Missing four-family/fast/slow coverage remains reported but no longer makes a semantically correct no-change trajectory fail admission.

## Deterministic tests

The user-reported trust construction now gives `moderate_increase` under all four perturbations:

| Changed input only | v7 result |
|---|---|
| dialogue label `new_decision`, feature 2 | +2 |
| dialogue label `new_explanation`, feature 2 | +2 |
| no dialogue diagnostics, feature 2 | +2 |
| dialogue label `new_decision`, feature 1 | +2 |

Additional tests cover feature 0/mismatch/null, semantic `none`, surface duplicates, legacy log consistency, slow-evidence consumption, opposite-direction clearing, and scenario timescale overrides. Relevant local regression: 153 state/runtime tests plus 19 rollout-admission tests passed.

## Frozen-output replay

Source: `fixed_set_correction_results.json`; model calls: 0. The replay changes calibration only and retains the saved Astra state appraisals.

- state judgment match against pre-registered, human-pending labels: 2/8;
- final update correctness: 5/8;
- among the two matching judgments, final update correctness: 2/2.

Thus the deterministic calibrator behaves correctly when the supplied state judgment is correct, but it cannot recover variables or decisive strength that Astra did not identify. This is below the scale gate and the labels still require human confirmation.

## Pending-request interface audit

The zero-call audit artifact is `data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/interface_consistency_audit.json`.

- The configured independent state prompt is `environment_state_appraisal_v3_variable_evidence_primary`; it makes the generic feature optional/auxiliary, permits all-zero features, and contains no feature-magnitude or dialogue-diagnostic update gate.
- The interaction prompt explicitly excludes state/dynamics/feature judgment. The response prompt runs only after Python's single deterministic update.
- The configured v7 profile uses the per-variable state judgment as the decisive-strength source, treats features as auxiliary, and disables the dialogue-diagnostic gate.
- The old combined v36 prompt still requires a nonzero feature, requires magnitude 2 for strength 2, and contains dialogue diagnostics. It is therefore a frozen baseline reference only and is prohibited from new v7 fixed-set calls.

The new runner `scripts/run_state_judgment_primary_fixed_validation.py` enforces these conditions before constructing providers. It accepts only a fully human-confirmed manifest, calls only the independent state/interaction pair, preserves every fixed/retest result, refuses accidental overwrite, and reports variable recognition, four-class judgment, strength, false positives/negatives, final update, and call completeness separately. Passing only authorizes unseen-example and small-rollout validation; it never authorizes full scale directly.

The label importer `scripts/confirm_state_fixed_labels.py` binds the reviewer export to the current v7 packet hash, requires all eight annotations to be complete, validates verbatim evidence spans, records ambiguity, and preserves disagreements from the old preregistered labels instead of treating those pending labels as ground truth. The v7 packet removes human feature/delta labeling and hides the target response and all future turns; its SHA-256 is `e08ba7fda16c204baa6e969de277bb40fb03ecbcce10c097652f59e2dffeff5a`.

## External validation authorization

The user explicitly approved transferring complete private scenarios, histories, ledgers, and pre-update snapshots to Astra. The confirmed-label original run and the one allowed corrected run were executed and retained separately below.

Neither passed the fixed-set gate, so scale remains stopped before unseen examples or complete trajectories.

## Human-confirmed labels

Reviewer `diudiu` confirmed all eight cases against packet SHA-256 `e08ba7fda16c204baa6e969de277bb40fb03ecbcce10c097652f59e2dffeff5a`. Six labels differ from the old preregistered, human-pending labels. The confirmed manifest is `data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/human_confirmed_fixed_set.json`.

All eight confirmed labels are ordinary or decisive new evidence, so this set has no human-confirmed no-evidence/repeated negative control. Zero false positives here is not a balanced false-positive test. Human update opinions are optional metadata; Python owns slow accumulation, budgets, and final delta.

## Original v7 Astra fixed set

Artifact: `data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/human_confirmed_fixed_set_results.json`. Conditions: Astra, low reasoning, temperature 0, state seed 46100, prompt SHA-256 `071cd924805e73e8b2d7243f2a2fea0f3f93765ac010efadc4808a6a9db42d38`.

| Metric | Base | Boundary | All counted |
|---|---:|---:|---:|
| Call complete | 8/8 | 4/4 | 12/12 |
| Variable recognition | 4/8 | 3/4 | 7/12 |
| Exact four-way judgment | 3/8 | 2/4 | 5/12 |
| Evidence strength | 3/8 | 2/4 | 5/12 |
| False negatives | 4 | 1 | 5 |
| Nonzero final updates | 0/8 | 0/4 | 0/12 |

The decisive trust case was ordinary twice. Astra's own rationale recognized costly honesty but incorrectly required verified follow-through too. Same-topic but materially new acceptances and decisions were also often classified repeated.

## Single allowed correction

Prompt `environment_state_appraisal_v4_definition_grounded`, SHA-256 `c7b3a75e22c0bf1cc2a2bd4d0b1d2a2817bf2e1601fa51967332ed1be6f44d1a`, received one general correction:

- evidence examples joined by “or” are alternatives, not cumulative requirements;
- repetition requires the same behavioral evidence, not merely the same topic;
- pragmatic acts are judged under role and power context, not literal keyword matching.

No scenario ID, target span, desired label, or sentence-specific exception was added. The separate interface audit is `interface_consistency_audit_single_correction.json`; 17 local regression tests passed.

Corrected artifact: `data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/human_confirmed_fixed_set_results_single_correction.json`.

| Metric | Base | Boundary | All counted |
|---|---:|---:|---:|
| Call complete | 7/8 | 4/4 | 11/12 |
| Variable recognition | 5/8 | 3/4 | 8/12 |
| Exact four-way judgment | 4/8 | 2/4 | 6/12 |
| Evidence strength | 4/8 | 2/4 | 6/12 |
| False negatives | 2 | 1 | 3 |
| Nonzero final updates | 0/7 completed | 0/4 | 0/11 completed |

The correction improved three decisions, but did not meet the gate.

Remaining observed failures:

- decisive trust stayed ordinary in base and retest because Astra again added verified follow-through;
- the second GPT002 trust case stayed no-evidence;
- the GPT003 follow-up was ordinary in base but no-evidence on identical retest input;
- the manager's pressure question stayed no-evidence for interpersonal safety;
- one safety-positive base call failed after three complete interaction-appraisal responses used invalid ledger `assertion_mode` values; the runner correctly reported `StructuredOutputError`.

Completed ordinary slow cases correctly remained unchanged in this isolated runner because each case starts a fresh calibrator without reconstructed pending evidence. Final-update integrity therefore checks diagnostic/application agreement, not sequential two-event accumulation. The only decisive case would have updated immediately, but Astra classified it ordinary twice.

## Final gate decision

`fixed_set_passed` is false and `gate_decision` is `stop_and_report_fixed_set_evidence`. The single permitted correction is consumed. No unseen sample, six-trajectory batch, or full scale was started.

Remaining blockers: semantic under-recognition and under-strength, instability on identical input, one structured interaction-appraisal failure, missing human-confirmed negative controls, and no sequential slow-evidence fixture. They require a newly authorized validation round, not continued tuning on this set.

## Authorized reasoning-effort comparison

The follow-up comparison froze v7, corrected state prompt v4 (SHA-256
`c7b3a75e22c0bf1cc2a2bd4d0b1d2a2817bf2e1601fa51967332ed1be6f44d1a`),
the eight human-confirmed labels, sampling, complete inputs, and all Python
selection rules. The only independent variable was Astra
`reasoning_effort: low` versus `medium`. Each case was called twice in a
predeclared counterbalanced order. Interaction appraisal was not called.

Preregistration:
`data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/reasoning_effort_comparison_preregistration.json`.
Complete result artifact:
`data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/reasoning_effort_comparison_results.json`,
SHA-256 `30e8b2b8a32922eb2aa726a1daf8a1235facccfec9d6907cf85049325cbc51c2`.

| Metric | Low | Medium |
|---|---:|---:|
| Logical calls completed | 16/16 | 16/16 |
| Complete final responses | 16/16 | 16/16 |
| Variable recognition | 12/16 | 11/16 |
| Exact four-way judgment | 10/16 | 9/16 |
| Evidence strength | 10/16 | 9/16 |
| Direction match | 12/16 | 11/16 |
| Directness match | 12/16 | 11/16 |
| False negatives | 4 | 5 |
| Costly honesty judged decisive | 0/2 | 0/2 |
| Same-topic new conduct recognized | 0/4 | 0/4 |
| Power-context pressure recognized | 2/2 | 2/2 |
| Repeat-stable cases | 8/8 | 7/8 |
| Nonzero final update in empty-accumulator cases | 0/16 | 0/16 |
| Underlying provider requests / failed attempts | 22 / 6 | 21 / 5 |
| Total provider request duration | 8320.6 s | 8798.0 s |

Medium did not improve Astra. It retained both core trust errors, scored lower
overall, and changed the fairness delay-cost case from no evidence to ordinary
new evidence between identical repeats. The predeclared medium semantic gate
and material-improvement gate both failed.

The zero final-update count above is not evidence that the slow-state threshold
is unreachable. Each comparison observation deliberately starts with an empty
accumulator. The separate deterministic full-history replay now proves: first
ordinary evidence is retained, a second independent same-direction event
produces `mild_increase`, both event IDs are consumed, and replaying a consumed
event cannot update or re-enter the pending pool. Artifact:
`data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/continuous_slow_evidence_replay.json`.

Decision: do not advance to unseen examples, six trajectories, or scale on
this result. Per the preregistration, the next eligible experiment is the same
material with a different appraiser backbone, with definitions, prompt,
calibrator, and labels unchanged. The two negative controls remain pending
human confirmation and therefore are not counted as ground truth yet.

## Immediate-update calibration revision (2026-10-05)

The update rule was revised after human direction that ordinary versus
decisive evidence may affect magnitude but must not determine whether a valid
new-evidence judgment updates.

- no_relevant_evidence and repeated_evidence_only remain unchanged.
- Every valid ordinary or decisive per-variable new-evidence judgment updates
  immediately; ordinary evidence receives at least a mild directional delta.
- Slow-variable accumulation and the reinforcement plateau no longer veto a
  new-evidence judgment.
- Generic features and dialogue diagnostics remain non-gating.
- State candidate budgets and family caps no longer suppress a valid v7
  per-variable judgment. Numeric bounds still apply, and consumed event IDs
  still prevent the same slow-variable event from updating twice.

Local regression: 56 state/appraisal/ontology/transition tests passed.
The no-model replay
data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/immediate_new_evidence_replay.json
proves that the first ordinary event updates by +1, a second distinct ordinary
event also updates by +1, replaying the consumed event produces zero, and an
empty accumulator does not block a valid new event.

The 32 saved Astra observations were replayed without API calls in
immediate_update_reasoning_replay.json:

| Metric | Low | Medium |
|---|---:|---:|
| Target recognized | 12/16 | 11/16 |
| Recognized target updated | 12/12 | 11/11 |
| Mean variables judged new | 8.375 | 8.000 |
| Mean variables actually selected | 8.250 | 8.000 |

Thus calibration now meets the requested conditional invariant: every
recognized valid target changes. The remaining blocker is appraisal quality:
Astra still misses 4/16 or 5/16 target changes and marks roughly eight state
variables as new per observation. Removing the selector veto exposes this
over-recognition instead of hiding it.

A one-pass state-only Fable probe was preregistered before calls: eight
human-confirmed positives plus one irrelevant and one repeated-evidence
control, one logical observation each, no interaction appraisal and no
outcome-driven reruns. The user confirmed both negative labels and explicitly
authorized transfer of all ten complete payloads to the Fable endpoint.

Artifact:
data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/fable_state_only_probe_results.json
(SHA-256 b93765f3b4b6ead2842ecdc549dd21325b44ded113c5a6375e8cf7b7823b68af).

| Metric | Fable |
|---|---:|
| Scheduled logical observations | 10 |
| Completed | 8 |
| Call failures | 2 |
| Positive target recognition | 4/8 |
| Recognized positive target updated | 4/4 |
| Confirmed negative controls correct | 0/2 |
| Mean variables judged new (completed calls) | 8.125 |
| Mean variables selected (completed calls) | 7.875 |
| Actual provider requests | 15 |
| Complete provider responses | 15/15 |
| Total provider request duration | 407.833 s |

The irrelevant copy-edit control failed structured output validation after
three complete responses. The exact repeated-evidence control was incorrectly
judged ordinary new evidence, changed trust by +1, and marked seven state
variables as new. One fairness positive received two complete refusals and
failed without a text response. The two negative controls initially hit a
local pre-provider action-shape error; this was the single evidence-backed
engineering correction. Those two payloads had not been transmitted, so only
their missing planned calls were executed; the original failures and
correction log remain in the artifact. The fairness refusal was not rerun.

Fable fails the positive, negative, and call-completeness gates and is more
over-inclusive than Astra. Do not run unseen examples, complete trajectories,
or scale from this result.
