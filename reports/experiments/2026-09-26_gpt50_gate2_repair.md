# GPT50 Gate 2 repair record

Record date: 2026-09-26 UTC

Status: **not passed**. Machine reruns are incomplete because the Claude
environment provider is returning HTTP 429 overloads. All human items remain
`pending`; no model output is recorded as human review. No additional video was
generated.

## 1. Population and turn-count contract

The earlier Gate 2 percentages used the **50-item retained mixed cohort**, not
only the 31 accepted rollouts. That was wrong for a primary GPT50 accepted-only
result. The corrected diagnostic population is 31 accepted trajectories; the
other statuses are reported separately and are excluded from the new primary
packets and reruns.

| source status | count | turn distribution | use after repair |
|---|---:|---|---|
| accepted under the original batch screen | 31 | 10×26, 11×3, 13×2 | accepted-only diagnostics and targeted machine rerun |
| machine_rejected | 15 | 10×13, 11×2 | baseline/error analysis only |
| generation_error | 4 | 2×2, 3×1, 6×1 | partial/error analysis only; never a completed rollout |
| total retained | 50 | 2–13 turns | old mixed-cohort baseline only |

There is a separate contract drift: the active batch configuration and
operations note admitted natural 10–20-turn trajectories, while
`SocialFlux_Rollout_Screening_Protocol_v1.md` requires continuous `t1..t20`
and a turn-20 `max_turns` ending. Therefore 31 are accepted under the old batch
screen, but **0/31 satisfy the explicit exact-20 contract**. This is retained
as a hard release blocker; existing status labels were not rewritten. The
future GPT50 rollout configuration now sets the minimum to 20.

## 2. E1 and E9: where the apparent invariance comes from

### Before repair

- E1 mixed-50 packet: 100 sampled transitions, 788 state labels, 737 unchanged,
  50 increases, 1 decrease; unchanged = **93.53%**.
- The accepted subset of that old packet: 62 transitions, 490 labels, 457
  unchanged; unchanged = **93.27%**.
- E9 mixed-50 one-variable-per-family sample: 142/200 never changed = **71%**.
- Accepted-only full variable population: 173/245 never changed = **70.61%**,
  so the E9 result is not caused only by the old 50-item mixing or by selecting
  one successful sample.

### Corrected accepted-only packets

- E1 uses a stable hash sample of 40 transitions from the 31 accepted
  trajectories, independent of direction: 294/316 unchanged = **93.04%**,
  21 increases, 1 decrease.
- E9 uses a stable hash review sample of 40 variables, independent of observed
  outcome: 27/40 unchanged = **67.5%**. The accompanying full-population result
  remains the primary diagnostic: 173/245 = **70.61%**.

Full accepted-only E9 population by state family / expected time scale:

| state family | time-scale prior | variables | never changed | fraction |
|---|---|---:|---:|---:|
| emotion | fast | 42 | 42 | 100.00% |
| behavioral_disposition | medium | 75 | 13 | 17.33% |
| relationship | slow | 57 | 54 | 94.74% |
| consequence_risk | context_dependent | 71 | 64 | 90.14% |

Across every turn of the 31 accepted trajectories (319 turns), the private
state contains 2,521 per-dimension deltas, of which only 145 are nonzero
(5.75%). The family-level unchanged fractions are 82.57% behavioral,
98.90% risk, 100% emotion, and 99.49% relationship. Dynamics are less inert:
coordination stability is unchanged on 53.27% of its observations,
information asymmetry on 79.31%, and negotiation openness on 74.25%.

### Appraisal → calibration → update trace

For the 319 accepted turns, the old v11/sparse-v1 trace contains:

- 982 appraisal state-impact candidates: 756 increase and 226 decrease.
- 610 receive a positive calibrated level; 372 are calibrated to zero.
- 312 are selected by the event budget; 298 positive candidates are suppressed
  by the budget.
- Selected directions are 307 increase and only 5 decrease.
- Only 145 selections become nonzero state deltas: 140 increases and 5
  decreases. The other 167 selections are bounded no-ops.
- Every selected no-op is an increase at current value 10:
  cooperation_readiness 94, boundary_assertion 38, evidence_seeking 22,
  resolve 9, disclosure_willingness 4.

Root cause is a combination of (a) the intentionally sparse one-state-impact
ordinary budget, (b) strongly increase-skewed appraisals, (c) early saturation
at 10, and (d) a confirmed implementation bug: a top-ranked boundary no-op
consumed the state budget and prevented a lower-ranked eligible impact from
being considered. The repair skips a boundary no-op before consuming budget
and records `suppressed_by=state_boundary_noop`; it does **not** fabricate a
delta. The Gate 2 rerun remains on the existing v11/sparse-v1 profile—no larger
change budget is used to force movement.

## 3. E3 history-intervention failures

The old mixed-cohort result had 17 failures (11 accepted, 5 machine-rejected,
1 generation-error). The old selector maximized historical state magnitude,
which usually chose t1 even when the checkpoint memory had retrieved recent
turns. In 16/17 failures the removed event was absent from the checkpoint's
`memory_view.relevant_turn_ids`.

Primary classification:

- **Invalid intervention target (15):** GPT50_002, 006, 007, 009, 014, 017,
  025, 029, 032, 039, 041, 043, 044, 046, 048. The deleted turn was not in the
  memory actually used at the checkpoint, so lack of change does not establish
  environment history insensitivity.
- **Metric dilution (1):** GPT50_035. Removing t1 changed one state direction
  (`state_direction_agreement=0.875`), but averaging it with seven unchanged
  state dimensions produced only 0.125, below 0.15.
- **Possible environment capability failure (1):** GPT50_005. t1 was actually
  relevant, yet state/dynamics directions stayed identical and the score was
  0.1217. This trajectory is itself in the generation-error cohort, so it is
  excluded from the accepted-only rerun and not treated as a clean valid
  failure.

The old score was also vulnerable in the other direction: 12/32 old automatic
passes had state and dynamics direction agreement of 1.0 and crossed 0.15 only
because of lexical differences in serialized appraisal JSON. The repair keeps
the 0.15 threshold but changes the intervention and measurement: prefer an
actually retrieved relevant turn, compare active changed dimensions, and use
structural appraisal fields (social act, nonzero event features, state/dynamics
impact directions) rather than JSON text similarity. Every new record logs the
relevant turn IDs and whether the removed event was among them.

## 4. E5 local-counterfactual failures

All nine old failures were evaluated at terminal t10. Candidate texts were
distinct and their appraisal impact sets differed, but the sparse/saturated
updater collapsed the three branches to one direction signature: eight cases
had no nonzero state/dynamics update in any branch; GPT50_029 produced the same
`information_asymmetry=-2` in all three branches.

| scenario | source status | branch output | primary diagnosis |
|---|---|---|---|
| GPT50_003 | accepted | 0 / 0 / 0 changed dimensions | environment update capability at settled terminal checkpoint |
| GPT50_011 | machine_rejected | 0 / 0 / 0 | same; excluded from accepted rerun |
| GPT50_022 | accepted | 0 / 0 / 0 | environment update capability |
| GPT50_025 | machine_rejected | 0 / 0 / 0 | same; excluded from accepted rerun |
| GPT50_029 | accepted | identical information_asymmetry decrease | environment maps distinct appraisals to the same effect |
| GPT50_030 | accepted | 0 / 0 / 0 | environment update capability |
| GPT50_041 | accepted | 0 / 0 / 0; all actions commitments | weak intervention plus environment suppression |
| GPT50_045 | accepted | 0 / 0 / 0 | environment update capability |
| GPT50_048 | machine_rejected | 0 / 0 / 0; all actions requests | weak intervention plus environment suppression; excluded |

There is no metric-only excuse for the nine: requiring at least two distinct
direction signatures is a reasonable machine sensitivity check, and the
social validity decision remains human. The old artifact did, however, hide
that appraisal structures differed. New records add distinct candidate-action
and structural-appraisal counts without changing the E5 criterion. The
checkpoint is now selected by a deterministic 70%-of-horizon rule (t7 for a
10-turn trajectory), fixed independently of outcome, to avoid testing only a
settled terminal exchange.

Spot-checks of old passing accepted items found mechanically plausible
directions: GPT50_002 split coordination stability +1 from cooperation
readiness +2; GPT50_004 split information asymmetry -1, no change, and fairness
+1 plus information asymmetry -1; GPT50_006 separated information asymmetry
-2 from goal-failure risk/deadline pressure +2; GPT50_007 separated disclosure
+2/information asymmetry -2 from information asymmetry -2 and no change. These
are diagnostic checks only; social plausibility still requires a human.

## 5. E4/E6 unchanged-dimension inflation and service failures

Recomputing the old records on dimensions where either side changed shows that
the headline consistency was dominated by zero/zero matches.

| check and cohort | successful records | zero/zero dimensions | active dimensions | active direction agreement | both changed / sign agreement |
|---|---:|---:|---:|---:|---:|
| E4 old mixed | 49 | 559/623 = 89.73% | 64 | 21.88% | 16 / 87.5% |
| E4 accepted subset | 31 | 355/395 = 89.87% | 40 | 17.50% | 7 / 100% |
| E6 old mixed, service-success only | 43 | 484/547 = 88.48% | 63 | 22.22% | 14 / 100% |
| E6 accepted subset, service-success only | 27 | 307/344 = 89.24% | 37 | 27.03% | 10 / 100% |

The old E4 headline `0.9190` and E6 headline `0.7817` therefore cannot be used
as changed-item robustness. E4/E6 now report both all-dimension diagnostics and
active-union metrics; unchanged/unchanged dimensions no longer raise the Gate
agreement numerator.

E6 had 7 failed records and 8 individual service errors in the mixed cohort:
GPT50_002, 005, 009, 013, 019 (two failures), 036, 049. The accepted-only subset
contains four failed records: GPT50_002, 009, 036, 049. A failed replay is now
excluded from agreement/reversal denominators instead of being encoded as
direction agreement 0, reversal 1, and ordinal distance 6. It remains a
zero-tolerance hard blocker, and the artifact separately records total matched,
successful matched, failed records, and individual replay errors.

## 6. Code and evidence changes

- Fixed boundary no-op budget consumption in `environment/calibration.py`.
- Added zero/zero, active-union, and both-changed metrics in
  `evaluation/transition_metrics.py`; E6 uses them in
  `evaluation/backbone_sensitivity.py`.
- Fixed relevant-event selection and structural E3 scoring in
  `scripts/run_history_dependence.py` and
  `scripts/run_environment_interventions.py`.
- Moved E3/E4/E5/E7 to a deterministic 70% checkpoint and removed the old
  code that appended only positive E3 records to reach the minimum.
- Bound E3-E7 and E6 artifacts logically to the accepted-only
  scenario/trajectory cohort. The manifest rejects old mixed evidence with
  `cohort_matches=false`.
- Rebuilt E1/E2/E9 to formal-sized stable samples (40/20/40), independent of
  observed success/change, and added E9 full-population splits by state family,
  time scale, and source status.
- Changed future GPT50 minimum turns to 20; the existing 31 trajectories are
  not retroactively called exact-20 compliant.
- Preserved the original mixed E3-E7/E6 files and SHA-256 hashes under
  `data/gpt50/experiment/gate2/baseline_mixed50_20260926/`.

The final consolidated Gate 2 regression suite passed 110/110 tests; focused
quality-gate, failover, and E6 follow-up suites also passed. The full
repository suite exposed unrelated pre-existing failures in other dirty
worktree areas; no failing targeted Gate 2 test remains.

## 7. Targeted rerun and remaining work

The accepted-only E3/E4/E5/E7 rerun is resumable and currently has 0 successful
new records. The first clean attempts received repeated Claude environment
HTTP 429 overload responses; after three consecutive overloads the runner
pauses and retries with backoff. The rerun now uses the repository's existing
same-model `claude-fable-5` multi-credential/chat+messages failover route; this
changes transport resilience only, not the environment model, prompt,
calibration, thresholds, or cohort. A full six-candidate failover cycle also
ended in HTTP 429, so the evidence points to a model-service-pool overload,
not a single credential or protocol failure. Provider errors are recorded rather than
treated as experiment failures. E6 will run after E3-E7 attempts complete. Until new
accepted-only artifacts exist, the live manifest correctly reports old
E3-E7/E6 evidence as cohort-mismatched or zero-coverage.

Still required:

1. Complete the accepted-only E3-E7 and E6 service reruns and regenerate the
   manifest; do not substitute old mixed records or select only successes.
2. Regenerate full exact-20 development rollouts after environment freeze if
   this batch is to satisfy the formal rollout protocol.
3. A named human must complete E1, E2, E3, E4, E5, E7, and E9 review packets.
   E8 remains pending with no new video generation in this repair.

No Gate 2 pass is claimed by this record.
