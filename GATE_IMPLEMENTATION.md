# SocialFlux gate.md Execution Contract

gate.md is enforced as an executable data contract, not a recommendation
checklist.

## Pool stages

- development may use --allow-unreviewed; it never becomes final benchmark.
- formal_raw requires all scenario quality gates approved and S0/D0
  human_frozen, uses an isolated rollout root, at least three local model
  families, at least 12 raw trajectories per scenario, no more than 30% API
  trajectories, and no policy/environment model identity.
- formal_selected is only materialized after quality, history and diversity
  gates pass. Each scenario retains 4–6 trajectories; selection does not keep
  only one highest-scoring trajectory.

## Per-trajectory gate

The six scored dimensions are dialogue coherence, history dependence,
character consistency, state–response consistency, interaction progression
and naturalness. Every dimension must be at least 3/5 and the normalized mean
must be at least 0.70.

Hard rejects are hidden-state leakage, malformed output, repetitive loop,
severe character contradiction, broken dialogue logic, meaningless premature
ending, nonsensical state oscillation and implementation-induced state
saturation.

Machine structural checks cannot silently replace independent judgment.
Missing dimension scores or history evidence yields pending_evidence, never
passed.

The primary judge covers the whole raw pool. A deterministic stratified subset
plus every borderline or primary-rejected case goes to a second judge from a
different model family. The merge remains incomplete if any required second
judgment is missing; material score/reject disagreements are explicitly
reported and merged conservatively.

## Diversity

Outcomes are assigned only after rollout. They are descriptive audit labels,
not predefined policies. Greedy selection prioritizes quality while adding
model-family and observed-outcome coverage and rejecting near duplicates.

## History dependence

The same selected checkpoint is probed under full observable history,
recent-k history, and full history with a causally critical event removed.
Probe records compare both the evaluated participant's next action and the
environment's appraisal/state-delta interpretation, identify removed turn IDs,
and preserve persona, state and current action. A trajectory without completed
evidence cannot enter formal_selected. Intervention strength is independent
evidence and never overwrites the six-dimension judge score.

`formal_selected` manifests bind the exact trajectory IDs to exact all-passing
quality-audit IDs. Missing, extra or mismatched files block task construction.

Gate 4 uses a task-specific human checklist rather than a generic approval:
T1 checks current-only shortcuts and history evidence; T2 checks natural paired
histories, byte-identical shared observation/media and causal divergence; T3
checks plausible trade-offs, common continuation and simulator stability.

## Ground truth boundary

Automatic judges filter and pre-check only. Formal T1/T2/T3 labels require
human annotation, agreement and adjudication. Neither an LLM nor an automated
script is permitted to sign a human freeze or formal ground truth record.
Each blinded packet embeds a task-specific discrete annotation contract:
canonical target-state coverage for T1/T2, canonical action/state coverage for
T3, enumerated intensity/direction labels, and explicit evidence fields.
Arbitrary JSON cannot be finalized as ground truth.

## Reproduction

See scripts/run_pipeline.py, scripts/audit_formal_rollout_pool.py and
scripts/run_quality_gates.py. The latter emits the strict Gate 1–4 report and
fails with --strict while any required evidence is pending or rejected. Private
raw trajectories, judgments and selected trajectories live under data/formal
and are excluded from Git.

The reproducible local policy pool is Qwen3-32B-AWQ, GLM-4-9B-Chat-HF and
DeepSeek-V2-Lite-Chat. These are three independently released model
families; four seeds per family yield 12 raw trajectories per scenario. The
Qwen3.5-9B environment backbone is a different model and the old Qwen3.5
development trajectories are not reused. The 32B policy satisfies the
20–40B-capacity priority while the other two families preserve family
diversity within four 48GB GPUs. API share is zero when credentials are absent
and can be raised, but never above 30%.

The end-to-end command order is fixed in `FORMAL_ROLLOUT_RUNBOOK.md`.
`scripts/verify_gate_md.py --strict` maps concrete artifacts back to all twelve
sections of `gate.md` and refuses release while any section is incomplete.
