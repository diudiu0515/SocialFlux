# Online multimodal website and scale readiness — 2026-09-30

## Outcome

- Review site: `http://127.0.0.1:8000/multimodal`
- Review API: `/api/online-multimodal-review`
- Active structurally valid assets: 75 across 48 scenarios.
- Playback: 32 loudness-normalized review copies and 43 original audiovisual files.
- Human review: 75 pending; no machine result is promoted to human approval.
- Full scale decision: hold. A one-scenario bounded batch is prepared but not submitted.

## Trigger presentation

Each event-family card exposes its versioned `online_multimodal_v2` conditions:
state family and variable, direction, operator and threshold, runtime cooldown/cap
policy, and any actual hit from the saved-trajectory replay. Scenario and batch panels
show first-fire latency, event count, condition-hit rate, fire-given-hit rate, state-family
coverage, scheduling blockers, and the diagnostic difficulty band.

The replay is explicitly labeled counterfactual and diagnostic. It reuses saved
`state_before` / `state_after` snapshots, makes zero model calls, does not regenerate
responses, and does not establish that the tested model alone caused a state change.

## Triggerability evidence

Source: `data/gpt50/experiment/gate2/all50_rollout_inputs` (50 historical trajectories).
Detailed evidence: `reports/experiments/2026-09-30_online_multimodal_triggerability_v1.json`.

- At least two events: 45/50 (90%).
- At least three events: 18/50 (36%).
- Median event count: 2 (pre-existing target: 3).
- Median first-fire turn: 1.
- Diagnostic bands: 45 easy, 5 moderate.
- Fired-event state sources: emotion 1, behavioral disposition 99,
  relationship 7, consequence risk 9.

The tested policy therefore reaches a trigger early, but trigger source coverage is
strongly skewed toward behavioral disposition. Early firing must not be reported as
healthy four-dimensional coverage.

## Evaluation rule

Trigger ease is reported as a vector rather than a single success rate:

1. Exposure: evaluable turns and condition-hit turns.
2. Actual firing: events and `fire / eligible turn` after scheduling constraints.
3. Latency: first condition hit and first emitted event.
4. Near miss: minimum state-point distance to a condition when no condition hits.
5. Blockers: global cooldown, event-family cooldown, per-trigger cap, episode cap,
   and one-event-per-turn priority budget.
6. Coverage: distinct event families and all four source-state families.

The website's diagnostic labels are versioned as follows: easy means at least two
fires with the first by turn 3; moderate means at least one fire; for zero-fire
trajectories, near-miss means a condition came within one state point. These labels
are not Gate thresholds. The existing scale reachability target remains unchanged:
at least 90% of scenarios with two events and median event count at least 3.

## Scale state

The finalizer recovered 75 already-downloaded assets without API calls; all 75 passed
local duration, stream, audio, and checksum validation. GPT50_036 and GPT50_045 still
lack active anchors.

For the next bounded step, GPT50_006 reuses its existing anchor and has five dependent
requests in `prepared` state. They have no provider task IDs and were not submitted.
Submission requires explicit approval to send the scenario-derived prompts and local
anchor video to the external Seedance/Doubao video API and incur charges.
