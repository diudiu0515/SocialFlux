# Gate 2 environment experiments — 20-scenario pilot

Date: 2026-09-09

## Model under test

Structured appraisal and visible response are two separate calls to
`Qwen3.5-9B` from `/root/autodl-tmp/models/Qwen3.5-9B-modelscope`.
Deterministic calibration and the numeric state/dynamics update occur between
those calls. E6 compares the resulting transition directions against
`GLM-4-9B-Chat-HF`. The 20-turn quality-first candidate policy is the separate
Qwen3-32B-AWQ model with three seeds per scenario.

## Results

| Experiment | Coverage | Machine result | Human status | Decision |
|---|---:|---:|---|---|
| E1 State-update agreement | 40 transitions, 2/scenario | prepared | pending, 1 reviewer | pending |
| E2 Full-trajectory plausibility | 20 trajectories, 1/scenario | prepared | pending, 1 reviewer | pending |
| E3 History intervention | 32 matched checkpoints; 18 passed change screen | machine screen passed | pending, 1 reviewer | pending human |
| E4 Paraphrase robustness | 20 strict matched-seed pairs; 20/20 equivalence precheck | overall/state/dynamics direction 0.9400/0.9429/0.9333; true reversal 0; threshold 0.80 | pending, 1 reviewer | machine passed, pending human |
| E5 Local action counterfactual | 20 checkpoints; 20 passed; 60 branches | machine screen passed | pending, 1 reviewer | pending human |
| E6 Backbone sensitivity | 20 matched checkpoints | exact direction 0.7078; change/no-change 0.7128; true reversal 0.005; ordinal distance 0.5333; record pass 1.0; 0 replay failures | automated | passed |

E3 reuses matched history-removal evidence and keeps zero-change records; it
does not retain only favorable outputs. E4 regenerates both the original and
strict paraphrase through fresh factories with the same configured seed and
call index. A deterministic precheck rejects changes in numbers, urgency,
politeness, pressure, conditions, commitment, negation, or question force. E5
uses the same real checkpoint for each set of three alternative actions. E6
also requires non-degenerate activity: Qwen changes 34/199 dimensions over
19/20 checkpoints and GLM changes 33/199 over 17/20, so all-similar output
cannot pass on agreement alone.

## Decision

E4 and E6 now pass their unchanged machine thresholds on the same deterministic
20-scenario pilot. The environment still cannot be frozen or scaled to 150
scenarios until E1/E2 and the E3–E5 samples receive the assigned human review,
and the new complete-rollout naturalness/state-distribution regression is
accepted. Failed repetitive rollout attempts remain archived rather than being
counted as evidence.

The stricter R3 rerun currently has 0 accepted trajectories, so R4 is marked
`insufficient_after_samples` rather than reporting a misleading distribution
improvement. Manual inspection rejected apparent machine passes for repeated
future-meeting deferral, document/task churn, repeated closure of an already
resolved issue, treating promises as completed actions, and silently swapping
first-person task ownership. These patterns are now deterministic hard-reject
checks. The 20-scenario R3 target remains pending; no low-quality trajectory was
promoted merely to meet the count.

No human attestation has been synthesized. Every evidence file remains pending
until the assigned reviewer signs it.
