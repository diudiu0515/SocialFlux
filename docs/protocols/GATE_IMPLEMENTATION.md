# SocialFlux gate.md Execution Contract

gate.md is enforced as an executable data contract, not a recommendation
checklist.

## Pool stages

- development may use --allow-unreviewed; it never becomes final benchmark.
- formal_raw requires all scenario quality gates approved and the initial state
  human_frozen; the runtime dynamics seed is machine-validated, uses an isolated
  rollout root, and contains exactly one logical
  natural trajectory per scenario. Transport/schema retries may repair the same
  logical call; failed trajectories are never replaced by another seed.
- formal_selected is only materialized after quality and history gates pass.
  Gate 3 admits or rejects the sole trajectory and never performs best-of-N selection.

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
reported and merged conservatively. Judge sampling is derived from the
trajectory ID, so running one item alone or in another batch order cannot
change its score merely by shifting the random stream.

For development-pool cleanup, `scripts/repair_failed_rollouts.py` accepts a
four-gate report and replaces only IDs whose Gate 3 audit is explicitly
`rejected`. Every candidate must pass structural checks and the configured independent
semantic prefilters before publication. The active manifest is replaced before the
old file is moved into `rollouts/rejected/`, and every failed candidate is
preserved as an observable-dialogue JSONL audit record. A historical non-quality replacement recorded as `t2_pairing_rebalance` remains audit evidence only. Production task construction no longer replaces or retains trajectories to balance source models.

## Corpus diversity

Outcomes are assigned only after rollout. They are descriptive audit labels,
not predefined policies. Diversity is audited across scenarios and must come
from the scenario design matrix and natural histories, not from best-of-N
trajectory search. Model family remains provenance, never a selection quota.

## History dependence

The same selected checkpoint is probed under full observable history,
recent-k history, and full history with a causally critical event removed.
Probe records compare both the evaluated participant's next action and the
environment's appraisal/state-delta interpretation, identify removed turn IDs,
and preserve persona, state and current action. A trajectory without completed
evidence cannot enter formal_selected. Intervention strength is independent
evidence and never overwrites the six-dimension judge score. Full, recent-k and
critical-removed policy actions are regenerated with the same model
configuration and seed; comparing an old rollout sample with a new sample is
not accepted as controlled evidence. History and judge evidence merge tools
require exact coverage of current manifest IDs after any replacement.

`formal_selected` manifests bind the exact trajectory IDs to exact all-passing
quality-audit IDs. Missing, extra or mismatched files block task construction.

Gate 4 first runs the shared instance_quality_judge_v2 LLM pre-screen over every T1--T3 candidate; this remains machine evidence and cannot sign human acceptance.
Gate 4 uses a task-specific human checklist rather than a generic approval:
T1 checks current-only shortcuts and history evidence; T2 checks natural paired
histories, byte-identical shared observation/media and causal divergence; T3
checks plausible trade-offs, common continuation and simulator stability.

## Ground truth boundary

Automatic judges filter and pre-check only. Frozen simulator state and branches
produce machine label proposals. Gate 4 sends the same deterministic 10% sample
within each task type to two independent humans; only disagreements need a
third adjudicator. Neither an LLM nor an automated script may sign those human
reviews. `release_audited_machine_labels.py` releases the complete proposal
population only after all four gates and the sampled double audit pass, and
keeps its machine origin explicit. The older three-annotator full-manual route
remains available as a legacy, higher-cost alternative.

## Reproduction

Use `python -m pipeline rollout|gate3|tasks|t4|audit`. The final `audit`
command emits the strict Gate 1–4 report and fails with `--strict` while any
required evidence is pending or rejected. Private
raw trajectories, judgments and selected trajectories live under data/formal
and are excluded from Git.

The active baseline routes Policy, Appraisal, Response, construction and judge
roles through independent `claude-fable-5` requests. Each scenario has one
rollout slot; Gate 3 is pass/fail and does not use model identity. Historical
local, multi-model and multi-seed runs remain diagnostic evidence only.

The end-to-end command order is fixed in [`FORMAL_ROLLOUT_RUNBOOK.md`](../operations/FORMAL_ROLLOUT_RUNBOOK.md).
`scripts/verify_gate_md.py --strict` maps concrete artifacts back to all twelve
sections of `gate.md` and refuses release while any section is incomplete.
