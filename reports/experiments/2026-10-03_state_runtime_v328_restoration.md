# State runtime v3.2.8 restoration

Recorded: 2026-10-03 UTC

## Decision

The formal GPT50 and Claude150 State-v3 rollout entries are restored to the
runtime v3.2.8 environment contract:

- appraisal: `environment_appraisal_v22_slow_first`
- appraisal model: `claude-fable-5`
- deterministic calibration: `evidence_causal_hysteretic_v5`
- response: `environment_response_v31_contrastive_event_driven`
- policy prompt: `task_rollout_action_v2_decision_continuity`
- horizon: natural 10--20 turns, maximum 20

The GPT50 and Claude150 launch scripts now write to new
`rollouts_state_v328_restored` roots. Existing rollout and v36 evidence is not
overwritten or reclassified.

V36 remains registered for audit evidence only. It is not referenced by either
formal `rollout.state_v3.json` entry.

## Why v3.2.8 was changed originally

V3.2.8 was not replaced because its accepted native trajectory had invalid
state evolution. That retained GPT50_002 trajectory completed naturally at 10
turns, changed all four state families, and applied one compliant slow
`relationship.trust +2` update from direct `commitment_signal=2` evidence.

Development continued because the evidence base was still narrow:

1. Only one native scenario had demonstrated the desired complete-trajectory
   behavior.
2. A separate v3.2.8 appraisal emitted a trust candidate while its cited
   feature was zero. V3.2.9 added feature-consistency rejection.
3. Ordinary two-event slow changes and negative-direction slow changes had not
   yet been demonstrated.
4. Later investigations found state-owner confusion in another runtime branch
   and weak slow-variable recall across scenarios.

Subsequent candidates attempted to address those legitimate gaps. The process
error was failing to keep the successful v3.2.8 trajectory as a mandatory
regression anchor while changing prompt structure and, later, moving appraisal
to GPT. The later branch regained multi-variable coverage but regressed the
scenario-specific slow-state mapping demonstrated by v3.2.8.

## Restoration fingerprints

Pre-restoration formal entry hashes:

- GPT50 `rollout.state_v3.json`: `880954a4386f9010d2c6c0fbb2dc8269b3a3640a3e020a9c927c2f6eb182f6d9`
- Claude150 `rollout.state_v3.json`: `acdbc837699997420d3aa71eb5b6f1b61597a1cd4f5c29943163ff88a708b61f`

Restored formal entry hashes:

- GPT50 `rollout.state_v3.json`: `61c9c02f3f74a72f1b8f27a9a2a14d1b96692e974e3333c32bd85d624970f2c9`
- Claude150 `rollout.state_v3.json`: `2986007e1882c78cab66c20a3455afe07a363ca045602b86d2f90b3d75cef01f`
- frozen original GPT v3.2.8 config: `d979ebaecc66b1ba2f8ea276c3a99f854bf52e56ba39e464fe4fd60704b03cd2`
- appraisal prompt v22: `a6a49d29bb5d4bcf0175ecb81ab35e888c5c9991ccac2408a20486947c54232e`
- response prompt v31: `2f10034b53910485a6cfa428dcfb66c8987f60b9653dc0a16d8d0d43e228a614`
- policy prompt v2: `647951998cc0fd57bf5c4713b9cbf4f7efa9489dd636ce0dacbd5c5ff9753bba`
- calibration implementation: `eb7bc2d34a25159e5aa7babf12af3e17ffcf4f8cba7740665ec0f51b10ee0b9f`

The active GPT config uses the same v3.2.8 runtime binding and sampling as the
frozen original while resolving providers through the maintained route file.
The Claude config applies the same environment contract to the Claude pool.

## Verification

- GPT50 readiness: 50 scenarios and 50 rollout slots; zero network requests.
- Claude150 readiness: 150 scenarios and 150 rollout slots; zero network
  requests.
- Focused prompt, runtime, appraisal-normalization, and environment suite:
  135/135 passed.
- V22 retains its original family-cap branch. V36's no-family-cap behavior is
  prompt-specific and does not affect v3.2.8.

## Status

Configuration restoration is complete. No new provider rollout has been
started by this restoration. The historical accepted GPT50_002 trajectory is
the regression anchor; additional small native validation remains required
before scale. Human review remains pending.

## Post-restoration four-scenario diagnostic

The pre-registered positive stage covered GPT50 scenarios 002, 003, and 026
plus Claude150 scenario 030. All four appraisal calls completed, but zero cases
met the complete registered requirement:

- GPT50_002 emitted trust at strength 2 but scored `commitment_signal=1` and
  selected role legitimacy instead. The historical anchor had scored the same
  action at `commitment_signal=2` and applied trust +2.
- GPT50_003 emitted a fully decisive trust candidate, but calibration v5's
  one-relationship budget selected the equally ranked responsiveness candidate.
- GPT50_026 emitted fairness with `respect_signal=2`, but rated fairness itself
  strength 1 and selected role legitimacy.
- Claude150_030 omitted safety and selected responsiveness.

Four of five provider requests ended with `max_tokens` under the historical
3,500-token appraisal output budget. This establishes output-length pressure
as a concrete instability risk, not yet as the sole cause.

The restored configuration therefore recovers the old design but does not
establish robust behavior. The current diagnosis has three layers: appraisal
feature/strength instability, variable omission, and deterministic candidate
displacement in calibration v5. Negative cases and native rollout were not
started after the positive-stage failure. Detailed evidence is in
`data/gpt50/experiment/state_v3_validation/v3226_v328_restored_multiscenario/positive_stage_decision.json`.
