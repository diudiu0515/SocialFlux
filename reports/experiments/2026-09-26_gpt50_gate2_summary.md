# GPT50 Gate 2 detailed experiment record

> **Pre-repair baseline only.** This file describes the original 50-item mixed
> retained cohort (31 accepted, 15 machine-rejected, 4 generation-error) and
> must not be read as the accepted-only Gate 2 result. The corrected cohort,
> diagnosis, code fixes, and targeted-rerun status are recorded in
> `2026-09-26_gpt50_gate2_repair.md`. The live manifest now rejects these old
> E3-E7/E6 artifacts as `cohort_matches=false`.

Record date: 2026-09-26 (UTC)

Formal status: **not passed / incomplete**. This is an evidence audit record,
not a declaration that Gate 2 passed.

Generated from the materialized evidence under `data/gpt50/experiment/gate2`.
This summary distinguishes machine evidence from required human attestation.

## Cohort caveat

Gate 2 contains one retained trajectory for each of 50 scenarios, but only 31
are canonical accepted rollouts. The audit cohort also contains 15
machine-rejected trajectories and 4 deepest retained trajectories whose latest
generation status is `generation_error`. Results therefore characterize the
full retained audit cohort; they do not establish that GPT50 has 50 accepted
rollouts.

## E1-E9 results

| Check | Materialized evidence | Current result |
|---|---|---|
| E1 state-transition agreement | 100 sampled transitions | Packet ready; all 100 items await a named human reviewer, so agreement is not yet computed. |
| E2 full-trajectory plausibility | 50 trajectories | Packet ready; persona consistency, history sensitivity, state continuity, response-state consistency, and overall scores all await human review. |
| E3 history intervention | 49 matched checkpoints; 32 automatic screens passed | Machine screen passed. Human validation of the matched intervention effect remains pending. |
| E4 paraphrase robustness | 49 pairs | Machine screen passed. Overall direction consistency is 0.9190; state agreement 0.9503; dynamics agreement 0.8694; true sign-reversal rate 0.0031. Human approval remains pending. |
| E5 local counterfactual | 49 matched checkpoints; 40 automatic screens passed | Machine screen passed. Human same-checkpoint validity judgment remains pending. |
| E6 backbone sensitivity | 50 GPT/Claude matched checkpoints | Aggregate metrics clear their numeric thresholds: direction agreement 0.7817, severe reversal fraction 0.14, and record pass fraction 0.86. Both backbones are active, but 7 replay failures keep the evidence record at `passed=false`. |
| E7 persona-only intervention | 49 matched checkpoints; 47 automatic screens passed | Machine screen passed. Human confirmation that state/history/action stayed fixed remains pending. |
| E8 video-state consistency | 40 selected nodes; 4 original videos and 2 replacements generated | Five items have a preliminary visual pass. One provider failure was replaced. Human audiovisual review, speech/lip-sync review, and the remaining review set are pending; machine screen remains false. |
| E9 timescale validity | 200 candidates covering 50 fast, 50 medium, 50 slow, and 50 context-dependent variables | Coverage is non-degenerate, but 0 variables have human matches. Direction consistency and final pass/fail remain pending human review. |

## Run identity and provenance

- Audit cohort: 50 retained trajectories from 50 scenarios.
- Canonical status at audit time: 31 accepted, 15 machine-rejected, and 4
  deepest retained trajectories ending in `generation_error`.
- Environment-intervention model: Claude Fable 5, temperature 0, seed 16100.
- Construction/appraisal model: GPT-6 Astra, temperature 0, seed 17100.
- Prompt families: v11 state prompts plus calibrator, paraphrase, persona, and
  local-counterfactual intervention prompts.
- Text evidence was materialized on 2026-09-25 18:34–18:36 +08; E8 was
  materialized on 2026-09-26 01:15 +08.
- Environment-intervention execution logged 63 attempt records and 14 errors:
  10 missing provider text responses, 3 appraiser JSON/schema failures, and 1
  HTTP 502. Errors by scenario were GPT50_005: 3, GPT50_009: 2,
  GPT50_019: 6, GPT50_022: 1, GPT50_025: 1, and GPT50_029: 1.
- GPT50_019 produced no common matched record for E3, E4, E5, or E7.

## Detailed findings

### E1 — state-transition agreement

- Packet: 100 sampled transitions; 0 named annotators; all labels are pending;
  agreement is `null`.
- Machine-derived direction labels across all variable fields: 737 similar, 50
  increase, and 1 decrease (788 labels because transitions have varying state
  dimensionality).
- Formal validator requires 1 named human reviewer, **30–50 transitions**, and
  agreement >= 0.70.
- Finding: the current 100-item packet is not merely unlabeled; it is also
  outside the formal validator's allowed sample-size range. A conforming 30–50
  item packet must be sampled and reviewed.

### E2 — full-trajectory plausibility

- Packet: 50 trajectories; 0 named annotators; all five score families remain
  `null` (persona consistency, history sensitivity, state continuity,
  response-state consistency, and overall plausibility).
- Turn-count distribution: 2 turns ×2, 3 ×1, 6 ×1, 10 ×39, 11 ×5, and 13 ×2.
- Formal validator requires **15–20 trajectories**, overall mean >= 4.0, and
  each other dimension >= 3.5.
- Finding: the 50-item packet is outside the formal sample-size range and must
  be reduced to a conforming reviewed sample.

### E3 — history intervention

- 49 matched records; GPT50_019 missing.
- Per-record automatic criterion: `change_score >= 0.15`.
- 32 records pass and 17 fail. Failures:
  GPT50_002, GPT50_005, GPT50_006, GPT50_007, GPT50_009, GPT50_014,
  GPT50_017, GPT50_025, GPT50_029, GPT50_032, GPT50_035, GPT50_039,
  GPT50_041, GPT50_043, GPT50_044, GPT50_046, and GPT50_048.
- Failure scores range from 0.0621 to 0.1466.
- Important interpretation: `machine_screen_passed=true` is a batch-coverage
  result (at least 10 passing records), not evidence that all 49 records pass.
  Named human validation remains pending.

### E4 — paraphrase robustness

- 49 pairs; GPT50_019 missing; all 49 pass the strict-equivalence precheck.
- Aggregate metrics: direction consistency 0.9190, state agreement 0.9503,
  dynamics agreement 0.8694, change/no-change agreement 0.9221, true sign
  reversal 0.0031, and mean ordinal distance 0.1181.
- Per-record criterion is direction consistency >= 0.80. Five failures:
  GPT50_010/t10 0.7692; GPT50_018/t10 0.7692; GPT50_023/t11 0.7500;
  GPT50_035/t10 0.7692; GPT50_037/t10 0.7273.
- Aggregate machine metrics pass, but human confirmation of semantic
  equivalence is still required.

### E5 — local counterfactual

- 49 same-checkpoint records; GPT50_019 missing.
- Per-record criterion: at least 2 branches and at least 2 distinct direction
  signatures.
- 40 pass and 9 fail because only one distinct signature was observed:
  GPT50_003, GPT50_011, GPT50_022, GPT50_025, GPT50_029, GPT50_030,
  GPT50_041, GPT50_045, and GPT50_048.
- `machine_screen_passed=true` again denotes sufficient batch coverage, not a
  clean 49/49 pass. Human same-checkpoint validity review remains pending.

### E6 — backbone sensitivity

- 50 matched GPT-6 Astra / Claude Fable 5 checkpoints.
- Aggregate metrics: mean direction agreement 0.7817 (threshold 0.70), severe
  reversal fraction 0.14 (maximum 0.20), record pass fraction 0.86 (threshold
  0.80), and mean ordinal distance 0.9748.
- Activity: GPT changes state on 27/50 records and 30/547 dimensions (active
  fraction 0.54); Claude changes state on 31/50 records and 47/547 dimensions
  (active fraction 0.62). Both clear the 0.25 activity threshold.
- Evidence remains `passed=false` because the validator requires zero replay
  failures. The seven failures are:
  - GPT50_002/t6 — GPT/OpenAI timeout.
  - GPT50_005/t2 — Claude returned empty content.
  - GPT50_009/t6 — GPT/OpenAI timeout.
  - GPT50_013/t6 — GPT/OpenAI timeout.
  - GPT50_019/t4 — GPT/OpenAI timeout and Claude empty content.
  - GPT50_036/t6 — GPT/OpenAI timeout.
  - GPT50_049/t6 — GPT/OpenAI timeout.

### E7 — persona-only intervention

- 49 matched records; GPT50_019 missing.
- Per-record criterion: `change_score >= 0.10`.
- 47 pass; 2 fail: GPT50_016/t10 at 0.0822 and GPT50_029/t10 at 0.0923.
- Batch coverage passes, but a human must still confirm that state, history,
  and action were held fixed while only persona changed.

### E8 — video-state consistency

- 40 nodes selected. Original run state: 4 generated, 1 provider failure, and
  35 request-ready but not submitted.
- Original generated items: GPT50_029/t1 pass; GPT50_022/t1 pass;
  GPT50_032/t2 structural pass but visual failure from visible subtitles;
  GPT50_007/t3 pass. GPT50_010/t1 hit a provider copyright false positive.
- Two paid replacements were generated: a copyright-neutral GPT50_010 version
  and a zero-text GPT50_032 version. Both pass coarse structural and preliminary
  visual checks.
- Effective preliminary visual passes: 5. Human audiovisual and lip-sync
  review is pending. Formal completion requires 40 generated items plus a named
  human review, so E8 is incomplete.
- Replacement audit: `data/gpt50/experiment/multimodal/replacements/audit.json`.

### E9 — timescale validity

- 200 candidates: 50 fast, 50 medium, 50 slow, and 50 context-dependent;
  coverage is non-degenerate.
- Change distribution: 142 have no changed turns; 58 have at least one.
  Changed-turn counts are 0×142, 1×18, 2×20, 3×10, 4×8, 5×1, and 6×1.
  Three candidates contain reversals; maximum single-turn ordinal change is 2.
- Human matches: 0; direction consistency is therefore `null`.
- Formal validator requires at least 10 human matches and direction consistency
  >= 0.70. E9 cannot yet receive a formal pass/fail judgment.

## Formal-validator compatibility

| Check | Blocking condition |
|---|---|
| E1 | 0 human labels, and packet size 100 is outside the required 30–50 range. |
| E2 | 0 human scores, and packet size 50 is outside the required 15–20 range. |
| E3/E4/E5/E7 | Machine evidence exists, but named human attestation is absent; individual failures must not be hidden by batch coverage flags. |
| E6 | Seven replay failures violate the zero-failure requirement. |
| E8 | Only 5 effective preliminary visual passes; 40 generated and human-reviewed items are required. |
| E9 | 0 human matches versus the minimum of 10. |

## Required remediation before a Gate 2 pass claim

1. Produce validator-conforming E1 and E2 samples, then obtain named human
   judgments and compute the prescribed metrics.
2. Complete named human review for E3, E4, E5, and E7; explicitly adjudicate
   the listed per-record failures.
3. Replay or adjudicate all seven E6 provider failures and regenerate the
   aggregate evidence.
4. Complete the remaining E8 generation set and named audiovisual/lip-sync
   review.
5. Add at least 10 E9 human matches and recompute direction consistency.
6. Regenerate `gate2/manifest.json`; the current manifest predates E8 and
   incorrectly says the E8 evidence is absent.

## Overall conclusion

Gate 2 has substantial machine evidence, but it is not complete and has not
passed formally. E3, E4, E5, and E7 pass their automatic screens. E6 needs its
seven replay failures resolved or explicitly adjudicated. E8 is only a partial
video canary with human audiovisual review pending. E1, E2, E3, E4, E5, E7,
E8, and E9 still lack required named human attestation.

The existing `gate2/manifest.json` predates the current
`video_state_consistency.json` and incorrectly reports E8 as absent. The
evidence file, not that stale field, is used in this summary.

## Evidence files

- `data/gpt50/experiment/gate2/state_transition_agreement.json`
- `data/gpt50/experiment/gate2/trajectory_plausibility.json`
- `data/gpt50/experiment/gate2/history_intervention.json`
- `data/gpt50/experiment/gate2/paraphrase_robustness.json`
- `data/gpt50/experiment/gate2/local_counterfactual.json`
- `data/gpt50/experiment/gate2/backbone_sensitivity.json`
- `data/gpt50/experiment/gate2/persona_intervention.json`
- `data/gpt50/experiment/gate2/video_state_consistency.json`
- `data/gpt50/experiment/gate2/timescale_validity.json`
