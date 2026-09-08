# SocialFlux Formal Rollout Runbook

This runbook is the only supported order for producing `formal_selected`
trajectories and formal T1/T2/T3 ground truth under [`gate.md`](../protocols/gate.md).

## 0. Human freeze (blocking prerequisite)

Generate or refresh the unsigned worksheet:

```bash
python scripts/prepare_scenario_review.py
```

A real reviewer inspects all 20 JSON/Markdown scenario pairs, updates each
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
the six independent evidence files under `data/formal/environment/`:

- `state_transition_agreement.json`: 30–50 sampled transitions, three named humans;
  collapsed direction agreement must be at least 0.70.
- `trajectory_plausibility.json`: 15–20 complete trajectories, three named humans;
  overall at least 4.0 and each named dimension at least 3.5.
- `history_intervention.json`: same persona/state/action with the causally
  relevant event removed.
- `paraphrase_robustness.json`: human-approved paraphrases with at least 80%
  direction consistency.
- `local_counterfactual.json`: same real checkpoint with plausible free-text
  alternatives and human validity judgment.
- `backbone_sensitivity.json`: matched checkpoint/action replayed by different
  environment model families.

Every human evidence record includes unique reviewer IDs, a timezone-bearing
UTC timestamp and `human_attestation=true`. The automated backbone experiment
can be run on the existing development pool:

```bash
python scripts/run_backbone_sensitivity.py \
  --raw-root configs/scenarios \
  --config configs/backbone_sensitivity.local.example.json \
  --output data/formal/environment/backbone_sensitivity.json

python scripts/run_quality_gates.py \
  --environment-evidence data/formal/environment \
  --review-registry reviews/scenario_review.signed.json
```

The first command does not approve Gate 2 by itself. E1/E2 and the human parts
of E3–E5 remain real-reviewer work. Formal rollout refuses to start unless all
E1–E6 evidence records pass.

## 1. Start four isolated local model services

Install the optional serving stack and download the three formal chat-model
repositories (the existing Qwen3.5 environment directory is reused):

```bash
pip install -r requirements-formal-rollout.txt
modelscope download --model ZhipuAI/glm-4-9b-chat-hf \
  --local_dir .local_models/formal/glm-4-9b-chat-hf
modelscope download --model Qwen/Qwen3-32B-AWQ \
  --local_dir .local_models/formal/qwen3-32b-awq
modelscope download --model deepseek-ai/DeepSeek-V2-Lite-Chat \
  --local_dir .local_models/formal/deepseek-v2-lite-chat
```

Model directories are ignored by Git. Verify that every shard listed in each
`model.safetensors.index.json` exists before starting a service.

```bash
CUDA_VISIBLE_DEVICES=0 python scripts/local_transformers_chat_server.py \
  --model .local_models/formal/glm-4-9b-chat-hf --port 8300
CUDA_VISIBLE_DEVICES=1 python scripts/local_transformers_chat_server.py \
  --model .local_models/formal/qwen3-32b-awq --port 8301
CUDA_VISIBLE_DEVICES=2 python scripts/local_transformers_chat_server.py \
  --model .local_models/formal/deepseek-v2-lite-chat --disable-cache --port 8302
CUDA_VISIBLE_DEVICES=3 python scripts/local_transformers_chat_server.py \
  --model /root/autodl-tmp/models/Qwen3.5-9B-modelscope \
  --architecture image_text --port 8303
```

The Qwen3.5-9B service is the stateful environment/construction backbone. The
rollout policies are Qwen3-32B-AWQ, GLM-4-9B and DeepSeek-V2-Lite-Chat, four seeds
each. No repair/neutral/escalation policy is supplied.

This is the reproducible local baseline, not a claim that 9B is the best policy.
Before the formal run, execute a matched pilot that replaces GLM-4-9B with a
quantized GLM-4-32B deployment if it fits and passes service tests. Keep
Qwen3-32B as the Qwen family, and keep four DeepSeek-family seeds; up to 30% of
the total raw pool may use a larger DeepSeek API model only when credentials and
provenance are available. Qwen3.5-9B remains environment-only in every formal
variant. Compare models using the same scenario, seeds, sampling budget, Judge
contract and human blind review; parameter count is not a selection score.

Do not silently substitute a 235B/671B MoE model into this four-service layout.
Activated parameters describe per-token computation, while serving still needs
the full model weights distributed across devices. Record GPU memory, parallel
layout, quantization, throughput and failures for any larger-model pilot before
changing `configs/formal_rollout_pool.local.json`.

## 2. Generate isolated raw trajectories

```bash
python scripts/run_pipeline.py \
  --rollout-config configs/formal_rollout_pool.local.json \
  --review-registry reviews/scenario_review.signed.json \
  --environment-evidence data/formal/environment \
  --rollout-root data/formal/raw \
  --output data/formal/raw_run
```

This creates 20 × 12 free-form trajectories and deliberately creates zero task
instances: task extraction is blocked until formal selection. Existing
Qwen3.5 development rollouts under `configs/scenarios/` are not read or copied.

## 3. Quality judge, history intervention and second judge

```bash
python scripts/run_rollout_quality_judge.py \
  --raw-root data/formal/raw \
  --provider-config configs/rollout_quality_judge.local.example.json \
  --judge-role primary --model-family qwen \
  --output data/formal/judgments.primary.json

python scripts/merge_rollout_judgments.py \
  --raw-root data/formal/raw \
  --primary data/formal/judgments.primary.json \
  --output data/formal/secondary_selection.json

python scripts/run_rollout_quality_judge.py \
  --raw-root data/formal/raw \
  --provider-config configs/rollout_quality_judge.secondary.local.example.json \
  --judge-role secondary --model-family glm \
  --trajectory-id-file data/formal/secondary_selection.json \
  --output data/formal/judgments.secondary.json

python scripts/merge_rollout_judgments.py \
  --raw-root data/formal/raw \
  --primary data/formal/judgments.primary.json \
  --secondary data/formal/judgments.secondary.json \
  --output data/formal/judgments.merged.json

python scripts/run_history_dependence.py \
  --raw-root data/formal/raw \
  --rollout-config configs/formal_rollout_pool.local.json \
  --output data/formal/history_dependence.json \
  --resume
```

The primary judges every trajectory. The secondary is a different model
family and receives a deterministic stratified subset plus all primary hard
reject/borderline cases. Missing required second judgments keep the bundle
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
python scripts/audit_formal_rollout_pool.py \
  --stage formal \
  --raw-root data/formal/raw \
  --judgments data/formal/judgments.merged.json \
  --history-evidence data/formal/history_dependence.json \
  --environment-evidence data/formal/environment \
  --review-registry reviews/scenario_review.signed.json \
  --output data/formal/gate_report.json \
  --selected-root data/formal/selected
```

Only trajectories passing six independent dimensions and all hard rejects are
eligible. Outcome labels are inferred after rollout. Near-duplicate filtering ranks candidates and keeps exactly one human-confirmed canonical trajectory per scenario. All candidates and rejection evidence remain in the audit archive; model family is reported but never quota-enforced. Afterward T1/T2/T3 rank eligible sources independently; one model may win none or all tasks. `selected` is not written unless the complete formal gate passes.

## 5. Build tasks and establish human-only GT

```bash
python scripts/run_pipeline.py --build-only \
  --rollout-config configs/formal_rollout_pool.local.json \
  --review-registry reviews/scenario_review.signed.json \
  --environment-evidence data/formal/environment \
  --rollout-root data/formal/selected \
  --output data/formal/tasks
```

Before preparing GT packets, generate hash-bound blind Gate 4 review records,
then independent humans must approve every candidate:

```bash
python scripts/prepare_task_review.py \
  --instances data/formal/tasks/instances.jsonl \
  --output data/formal/task_reviews.jsonl
```

Every approval requires a real reviewer identity, timezone-bearing UTC time,
`human_attestation=true`, the unchanged instance SHA-256, and every boolean in
the task-specific T1/T2/T3 review checklist set truthfully to true. Then Gate 4
must pass:

```bash
python scripts/run_quality_gates.py --strict \
  --scenario-root configs/scenarios \
  --raw-root data/formal/selected \
  --rollout-stage selected \
  --pipeline-output data/formal/tasks \
  --environment-evidence data/formal/environment \
  --judgments data/formal/judgments.merged.json \
  --history-evidence data/formal/history_dependence.json \
  --human-task-review data/formal/task_reviews.jsonl \
  --review-registry reviews/scenario_review.signed.json \
  --output data/formal/four_gate_report.json

python scripts/formal_ground_truth.py prepare \
  --instances data/formal/tasks/instances.jsonl \
  --quality-gate-report data/formal/four_gate_report.json \
  --output data/formal/annotations/packets.jsonl
```

`formal_ground_truth.py prepare` refuses a missing/failed Gate 4 report or a
different instance count.

Three independent humans annotate each blinded packet. Every vote records the
annotator ID, timezone-bearing UTC timestamp, `human_attestation=true` and the
exact `packet_sha256`; its label must satisfy the embedded T1/T2/T3 annotation
contract, including complete canonical state/action coverage and evidence
fields. Disagreement requires a named, timestamped human
adjudicator bound to the same packet hash. After those files exist:

```bash
python scripts/formal_ground_truth.py finalize \
  --packets data/formal/annotations/packets.jsonl \
  --annotations data/formal/annotations/annotations.jsonl \
  --adjudications data/formal/annotations/adjudications.jsonl \
  --output data/formal/annotations/formal_gt.json

python scripts/verify_gate_md.py --strict
```

`verify_gate_md.py --strict` is the final 12-clause release gate. Missing human
signatures, model evidence, selected trajectories or formal GT is a hard
non-zero result, never an implicit pass.
