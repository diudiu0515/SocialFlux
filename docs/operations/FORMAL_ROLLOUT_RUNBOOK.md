# SocialFlux Formal Rollout Runbook

This runbook is the only supported order for producing `formal_selected`
trajectories and formal T1/T2/T3 ground truth under [`gate.md`](../protocols/gate.md).

## 0. Human freeze (blocking prerequisite)

Generate or refresh the unsigned worksheet:

```bash
python scripts/prepare_scenario_review.py
```

A real reviewer inspects every JSON/Markdown scenario pair listed in the active
run manifest, updates each
scenario's quality checklist and `construction_status`, regenerates docs, then
records their identity, UTC time, exact scenario SHA-256 and all six truthful
attestations in a separate signed registry. A model or script cannot perform
this step. `formal_raw` refuses unsigned, stale, incomplete or model-authored
records.

The same record contains all six 1–5 Gate 1 human quality scores. Social
plausibility, trade-off quality and history necessity must each be at least 4;
the other dimensions must each be at least 3 and the overall mean at least 4.0.

## 0.5 Environment validity and freeze (blocking prerequisite)

Use the development trajectories—not future formal trajectories—to assemble
the nine independent evidence files under `data/formal/environment/`:

- `state_transition_agreement.json`: the manifest-declared stratified transition sample, one named human;
  collapsed direction agreement must be at least 0.70.
- `trajectory_plausibility.json`: the manifest-declared complete-trajectory sample, one named human;
  overall at least 4.0 and each named dimension at least 3.5.
- `history_intervention.json`: same persona/state/action with the causally
  relevant event removed.
- `paraphrase_robustness.json`: human-approved paraphrases with at least 80%
  direction consistency.
- `local_counterfactual.json`: same real checkpoint with plausible free-text
  alternatives and human validity judgment.
- `backbone_sensitivity.json`: matched checkpoint/action replayed by different
  environment model families.
- `persona_intervention.json`: same state/history/action with a persona-only
  intervention and a human interpretation of the resulting difference.
- `video_state_consistency.json`: important-node video safety plus human review
  of expression/state fit, continuity, identity and lip sync.
- `timescale_validity.json`: human-reviewed fast/medium/slow state-variable
  change-rate evidence, with consequence risk reviewed as context-dependent.

Every human evidence record includes unique reviewer IDs, a timezone-bearing
UTC timestamp and `human_attestation=true`. The automated backbone experiment
can be run on the existing development pool:

```bash
python scripts/run_backbone_sensitivity.py \
  --raw-root configs/scenarios \
  --config configs/backbone_sensitivity.local.example.json \
  --output data/formal/environment/backbone_sensitivity.json
```

The manifest records the sample counts and deterministic selection seed; the
protocol does not hard-code a catalog size. The first command does not approve
Gate 2 by itself. E1/E2 and the human parts
of E3–E5 and E7–E9 remain real-reviewer work. Formal rollout refuses to start unless all
Gate 1 records pass. Gate 2 is checked before canonical selection by
`python -m pipeline gate3`; it never mutates pending evidence into a pass.

Generate the controlled E3/E4/E5/E7 experiments and all browser-facing packets:

```bash
python scripts/run_environment_interventions.py --resume
python scripts/prepare_human_review_workspace.py
```

The first script fixes the checkpoint/persona/state/action controls and writes
machine screens incrementally. One named Gate 2 reviewer still checks E1/E2,
paraphrase equivalence, history-intervention validity, counterfactual action
plausibility, persona-only sensitivity, video-state consistency and timescale
validity before setting `human_attestation=true`.

## 1. Validate the active routed runtime

The active baseline uses the authorized AutoDL Anthropic Messages endpoint via
`providers/anthropic.py`. The API key is read from `AUTODL_API_KEY` or the
server-private key file referenced by `configs/model_routes.frontier_api.json`;
it must never be copied into a config, manifest, report, or Git commit. The
production route bypasses server HTTP proxies. Claude Code CLI is a connectivity
diagnostic only and is not the dataset generation client.

```bash
python -m pipeline preflight
```

This offline preflight requires one versioned route-table hash and
`claude-fable-5` for every active role. Policy, task generation, judges,
Structured Appraisal, and Response use separate requests. Appraisal and Response
remain separate environment stages with deterministic Python calibration and
numeric update between them. Historical local-model and model-comparison configs
are diagnostic evidence only and cannot be mixed into this run.

## 2. Generate isolated raw trajectories

```bash
python -m pipeline rollout \
  --review-registry reviews/scenario_review.signed.json \
  --output data/formal/raw \
  --workers 4 --retry-limit 1 --resume
```

This creates exactly one free-form trajectory per approved scenario and deliberately creates zero task
instances: task extraction is blocked until Gate 3 admission. A rejected or failed
trajectory remains denominator evidence and is not replaced. Existing
development rollouts under `configs/scenarios/` are not read or copied.

## 3. Quality judge, history intervention and second judge

```bash
python scripts/run_rollout_quality_judge.py \
  --raw-root data/formal/raw \
  --review-config configs/review_models.json \
  --judge-role primary \
  --output data/formal/judgments.primary.json

python scripts/merge_rollout_judgments.py \
  --raw-root data/formal/raw \
  --primary data/formal/judgments.primary.json \
  --output data/formal/secondary_selection.json

python scripts/run_rollout_quality_judge.py \
  --raw-root data/formal/raw \
  --review-config configs/review_models.json \
  --judge-role secondary \
  --trajectory-id-file data/formal/secondary_selection.json \
  --output data/formal/judgments.secondary.json

python scripts/merge_rollout_judgments.py \
  --raw-root data/formal/raw \
  --primary data/formal/judgments.primary.json \
  --secondary data/formal/judgments.secondary.json \
  --output data/formal/judgments.merged.json

python scripts/run_history_dependence.py \
  --raw-root data/formal/raw \
  --rollout-config configs/formal_rollout_pool.json \
  --output data/formal/history_dependence.json \
  --resume
```

The primary judges every trajectory. The current single-model baseline uses a
separate seeded Claude request for the secondary audit; this is request
independence, not model-family independence. The secondary receives a
deterministic audit subset plus all primary hard-reject/borderline cases.
Missing required second judgments keep the bundle
incomplete. Judge input contains only observable dialogue/expression. The
history probe generates Full, Recent-k and Critical-event-removed policy actions
with the same model configuration and seed. It separately restores the same
private checkpoint and action to compare environment appraisal and
state/dynamics directions. The response-generation call is intentionally
skipped in that environment-only probe because it occurs after, and cannot
change, the recorded appraisal/delta. Results are written after every
trajectory and `--resume` validates completed IDs before continuing. This
intervention score does not replace the judge's History Dependence rating.

If an interrupted or repaired pool needs targeted evidence, repeat
`--trajectory-id TRAJECTORY_ID` for the new active IDs and write to a separate
file. Merge only after replacement with:

```bash
python scripts/merge_history_dependence.py \
  --raw-root data/formal/raw \
  --input data/formal/history_dependence.before_repair.json \
  --input data/formal/history_dependence.replacements.json \
  --output data/formal/history_dependence.json

python scripts/merge_rollout_quality_evidence.py \
  --raw-root data/formal/raw \
  --input data/formal/judgments.primary.before_repair.json \
  --input data/formal/judgments.primary.replacements.json \
  --output data/formal/judgments.primary.json
```

Run the equivalent command for secondary evidence, then rerun
`merge_rollout_judgments.py`. Both evidence merge tools require exact coverage
of the active manifest and refuse missing IDs. Candidate prefilter judgments
from `repair_failed_rollouts.py` are audit traces, not substitutes for these
formal primary/secondary files.

## 4. Formal selection

```bash
python -m pipeline gate3 \
  --raw-root data/formal/raw \
  --judgments data/formal/judgments.merged.json \
  --history-evidence data/formal/history_dependence.json \
  --environment-evidence data/formal/environment \
  --review-registry reviews/scenario_review.signed.json \
  --output data/formal/gate3_report.json \
  --selected-root data/formal/selected
```

The sole trajectory must pass all six independent dimensions and every hard-reject check. Gate 3 performs no ranking, diversity selection, seed comparison, or replacement sampling: it admits or rejects that trajectory. Outcome labels remain post-hoc diagnostics. Rejection evidence stays in the audit archive. `selected` is not written unless the complete formal gate passes.

## 5. Build tasks and audit machine-proposed labels

```bash
python -m pipeline tasks \
  --review-registry reviews/scenario_review.signed.json \
  --environment-evidence data/formal/environment \
  --rollout-root data/formal/selected \
  --gate3-report data/formal/gate3_report.json \
  --output data/formal/tasks
```

Generate the deterministic, hash-bound Gate 4 sample. The builder derives
machine proposals from the frozen source state/branch and never writes them as
human ground truth:

```bash
python scripts/prepare_human_review_workspace.py \
  --pipeline-root data/formal/tasks \
  --task-review-output data/formal/task_reviews.sample.json \
  --output data/formal/human_review_workspace.json
```

Gate 4 samples 10% independently within T1/T2/T3 (minimum two per type). Two
distinct humans review the exact same blind sample. Every decision requires a
timezone-bearing UTC time, `human_attestation=true`, the unchanged instance
SHA-256 and the complete task checklist. Agreement is final; a distinct third
human adjudicates only disagreements. Then Gate 4 must pass:

```bash
python -m pipeline audit --strict \
  --scenario-root path/to/frozen-scenarios \
  --raw-root data/formal/selected \
  --rollout-stage selected \
  --pipeline-output data/formal/tasks \
  --environment-evidence data/formal/environment \
  --judgments data/formal/judgments.merged.json \
  --history-evidence data/formal/history_dependence.json \
  --human-task-review data/formal/task_reviews.sample.json \
  --review-registry reviews/scenario_review.signed.json \
  --output data/formal/four_gate_report.json

python scripts/release_audited_machine_labels.py \
  --instances data/formal/tasks/instances.jsonl \
  --machine-proposals data/formal/machine_task_proposals.json \
  --four-gate-report data/formal/four_gate_report.json \
  --output data/formal/annotations/formal_gt.json

python scripts/verify_gate_md.py --strict
```

`verify_gate_md.py --strict` is the final 12-clause release gate. Missing human
signatures, model evidence, selected trajectories or released labels is a hard
non-zero result, never an implicit pass.
