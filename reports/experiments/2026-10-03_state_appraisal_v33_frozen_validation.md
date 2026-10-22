# State appraisal v33 frozen validation record

Status: **target validation failed; no rollout or scale authorized**
Human review: **pending**

## Frozen baseline

- v33 prompt remained unchanged throughout its validation.
- Prompt SHA-256: `383d186d2bda4017b8d95605040ad6eb27c3865bc9e819982ed791336bd19c08`.
- GPT v33 config SHA-256: `5af1bc70a2bd921093db5e1775b28cae3f6d3d6d8bb36a63990b2e230d3f690b`.
- Calibration SHA-256: `eb7bc2d34a25159e5aa7babf12af3e17ffcf4f8cba7740665ec0f51b10ee0b9f`.
- The Gate rules, calibration thresholds, update budgets, scenario files, and natural 10–20 turn contract were not relaxed.
- Before the first v33 call, the target, regression, and eight-case fresh holdout order was preregistered in `data/gpt50/experiment/state_v3_validation/v3220_safety_scope_gpt_appraisal_selection/manifest.json`.

## v33 target result

Result: **4/5 passed; rejected before regression and fresh holdout**.

| Case | Expected | Observed | Result |
|---|---|---|---|
| Claude008 t15 | safety, direct, strength 2, respect 2 | exact match; moderate safety increase | pass |
| Claude008 t13 | no safety candidate | safety, direct, strength 1; no delta | fail |
| GPT002 t3 | trust, direct, strength 2 | exact match; moderate trust increase | pass |
| GPT002 t4 | no trust candidate | responsiveness only | pass |
| GPT002 t10 | trust, direct, strength 1; no trust delta | exact match; no trust delta | pass |

The t13 failure is an **evidence-strength/eligibility-floor error**: a generic conditional future notice should have been omitted, but was retained as a strength-1 safety candidate. It is not a numeric update error because calibration correctly produced no state delta.

Evidence: `data/gpt50/experiment/state_v3_validation/v3220_safety_scope_gpt_appraisal_selection/target_outcome.json`.

## Isolated repair and comparison results

### v34: evidence eligibility only, GPT low reasoning

- Added only the rule that notification sequencing without concrete protected content, boundary, exposure, retaliation risk, or containment is omitted rather than downgraded to strength 1.
- Calibration and Gate rules were unchanged.
- Completed targets before protocol stop:
  - Claude008 t15: safety found, but strength drifted from 2 to 1 — **evidence-strength error**.
  - GPT002 t3: trust omitted — **variable omission**.
  - GPT002 t4: passed.
  - t13 and t10 were interrupted after the candidate was already rejected.

Evidence: `data/gpt50/experiment/state_v3_validation/v3221_safety_eligibility_gpt_appraisal_selection/target_outcome_low_reasoning.json`.

### v34: higher reasoning only

- Prompt and calibration were frozen; only `reasoning_effort` changed from `low` to `medium`.
- GPT002 t3 passed.
- Claude008 t15 emitted responsiveness strength 1 and omitted safety — **variable omission / safety-responsiveness confusion**.
- The remaining targets were not run.

Evidence: `data/gpt50/experiment/state_v3_validation/v3222_safety_eligibility_medium_reasoning_selection/critical_outcome.json`.

### v35: short adjacent-variable recheck, GPT low reasoning

- Restored low reasoning and did not enable an independent audit.
- Appraisal was instructed to evaluate safety and responsiveness separately against their own semantics and evaluated-agent history.
- Both candidates could coexist only with independent, distinct exact spans.
- The existing calibration budget remained at most one relationship update per turn; no state change was forced.
- Claude008 t15 emitted no state candidate at all — **variable omission**.
- GPT002 t3 was interrupted after the first critical failure.

Evidence: `data/gpt50/experiment/state_v3_validation/v3223_adjacent_variable_recheck_selection/critical_outcome.json`.

### Independent cross-backbone audit

- The frozen v34 prompt and calibration were reused.
- Claude performed a separate appraisal call without seeing the GPT output.
- This was an automated diagnostic audit, not human review, and was not integrated into runtime state updates.
- Claude008 t15 passed.
- GPT002 t3 passed.
- Claude008 t13 again emitted safety strength 1 — **evidence-strength/eligibility-floor error**.
- GPT002 t4/t10 were interrupted after rejection.

Evidence: `data/gpt50/experiment/state_v3_validation/v3224_claude_independent_appraisal_audit_selection/critical_outcome.json`.

## Root cause

The remaining failure is not in numeric state update code. Across identical frozen context and unchanged calibration, the appraisal model is unstable at the semantic boundary between:

- a concrete, binding protection before escalation (`t15`), which must be decisive safety evidence; and
- a generic conditional heads-up before a possible future reply (`t13`), which must not be a safety candidate.

The observed errors alternate between:

1. **evidence eligibility/strength error** — retaining t13 as strength-1 safety; and
2. **variable omission** — omitting t15 safety or replacing it with responsiveness.

No evidence showed candidate displacement by deterministic calibration: the failing variable was absent or misclassified in the raw appraisal. No evidence showed numeric update error: whenever strength-1 safety leaked through, calibration correctly left state unchanged; whenever a valid strength-2 candidate was produced, the update was correct.

## Code and configuration changes

- v33 was not edited.
- v34 and v35 were added as versioned experimental candidates; neither is selected for rollout.
- v34 added only safety evidence eligibility wording.
- v35 added only the adjacent safety/responsiveness recheck and candidate-coexistence wording.
- Runtime registrations and versioned GPT/Claude configs were added for reproducible diagnostics.
- A Claude audit-only config was added for the independent comparison; it is not a production rollout config.
- Prompt/runtime regression coverage increased to 133 passing tests.
- GPT 50-scenario and Claude 150-scenario readiness checks passed for the versioned configs.

## Phase disposition

- Existing development regression after the new candidates: **not run**, because target phases failed.
- Old holdout: **regression-only** because it informed prompt changes.
- Eight-case fresh holdout: **not exposed** to v33/v34/v35 or the audit, because earlier phases failed.
- Complete GPT rollout: **not run**.
- Complete Claude rollout: **not run**.
- Full scale: **not authorized**.
- Human review: **pending**.

Short probes remain diagnostic only. No short-probe result is being represented as complete-trajectory or Gate acceptance evidence.
