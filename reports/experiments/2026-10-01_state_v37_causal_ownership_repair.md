# State v3.7 causal ownership repair

Recorded: 2026-10-01 UTC

## Status

Runtime v3.7 is the active repair candidate. Runtime v3.5 and v3.6 are
frozen diagnostic failures and are not native-rollout or Gate acceptance
evidence. Human review remains pending.

Two single-first-pass native pilots were started in independent directories:

- GPT policy with Claude environment:
  `data/gpt50/experiment/runs/gpt50_state_v37_native_20261001T080434Z`
- Claude policy and environment:
  `data/claude150_v1/state_v3_validation/state_v37_native_20261001T080434Z`

Both use a natural 10--20-turn horizon, one trajectory, no replacement
sampling, and retained machine rejections. Incremental Gate preparation runs
locally without provider calls. The pre-fix Claude pool remains paused and is
not resumed in place.

## Root cause and evidence

V3.6 correctly declared that mutable state belongs to
`environment_agent`, but its appraiser still mirrored evaluated-agent
behavior into Environment behavioral disposition:

- Claude t6 treated “草稿我会给您看” as Raymond's
  `disclosure_willingness increase`.
- Claude t7 treated Yuki's request for Raymond's account as Raymond's
  `evidence_seeking increase`.

The frozen evidence is:

- `data/claude150_v1/state_v3_validation/state_v36_behavioral_targeted_probe.json`
- `data/gpt50/experiment/state_v3_validation/state_v36_behavioral_targeted_probe.json`

A separate issue in the written standard was too restrictive: it prohibited
one evidence span from supporting multiple states. A single action may
reasonably affect several Environment states through distinct causal
mechanisms. The invalid pattern is generic signal cloning without a
variable-specific causal bridge, not shared text itself.

## V3.7 changes

V3.7 binds:

- `environment_appraisal_v19`
- `evidence_causal_hysteretic_v5`
- `environment_response_v28`

The appraiser now applies an Environment-next-behavior causal test and explicit
cross-agent counterexamples. The calibrator permits one event/span to support
distinct cross-family effects, while retaining all existing evidence
requirements and update budgets.

No Gate threshold, feature threshold, fast/slow rule, anti-convergence rule,
family cap, ordinary two-update budget, decisive three-update budget, or
10--20-turn horizon was relaxed.

## Fixed-sample validation

Artifacts:

- `data/gpt50/experiment/state_v3_validation/state_v37_causal_smoke.json`
- `data/claude150_v1/state_v3_validation/state_v37_causal_smoke.json`

Machine diagnostic results:

- GPT t1: `hope +1`, `cooperation_readiness +2`, and
  `perceived_responsiveness +2`. The three effects use distinct causal
  meanings and remain within the decisive-event budget.
- Claude t6: no disclosure-increase mirroring from “show you my draft”.
  The firm commitment not to proactively record the private discussion
  instead produced a scenario-consistent Raymond
  `disclosure_willingness decrease`.
- Claude t7: no behavioral-disposition candidate. The voluntary written
  preview affected `perceived_responsiveness`, not Raymond
  `evidence_seeking`.

All three appraisal requests completed without generation errors. These files
are diagnostic-only and do not substitute for native rollout evidence or human
review.

## Verification

The focused state suite completed 125/125 tests. Both v3.7 configurations load
with the exact binding above and minimum natural turn count 10.

## Pending

- Complete both native pilots and inspect every selected state change for
  Environment ownership, direction, timescale, and evidence grounding.
- Prepare machine Gate 1/2 packets from the completed trajectories.
- Keep formal human Gate 1, E1, E2, and E9 fields pending; model output must not
  be recorded as human approval.
- Decide whether Claude quality is adequate before scaling. If it is not,
  retain Claude as Environment and use GPT for later evaluated-agent rollout,
  as previously agreed.
