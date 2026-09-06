# Four-Gate development filtering log — 2026-09-06

## Scope and non-claims

This run screens the 20-scenario **development** pool. It does not turn that
pool into `formal_raw` or `formal_selected`: Gate 1 still requires signed human
scenario/S0-D0 review, Gate 2 E1–E5 require named human evidence and E6
currently fails, and the development pool has 3 rather than 12 raw trajectories
per scenario. No script or LLM signed those human-only records.

## Fixed filters

- Structural trajectory checks: at least five turns, non-empty and concise
  dialogue, no exact/near loops, valid single-speaker dialogue format, and
  bounded-state diagnostics.
- Semantic checks: six 1–5 dimensions from `gate.md`; conservative mean of a
  Qwen3-32B primary judge and GLM-4-9B secondary judge; union of hard rejects.
- Final review coverage: 60/60 primary plus 60/60 cross-family secondary.
- History check: the same checkpoint is probed under Full History, Recent-k,
  and Critical Event Removed. All three policy actions use the same model
  configuration and seed. The environment probe restores the same private
  snapshot/action and compares appraisal plus numeric state/dynamics deltas.
- Thresholds were not lowered during repair. A candidate failing any active
  filter was not published into the active manifest.

## Iterations and findings

| Evidence | Result | Action |
|---|---:|---|
| `2026-09-06_four_gate_after_dual_judge.json` | 26 rejected / 34 pending | Added strict candidate prefilter and targeted repair. |
| `...after_repair_round1.json` | 16 rejected / 44 pending | Replaced explicit rejects only. |
| `...after_repair_round2.json` | 12 rejected / 48 pending | Added cross-family candidate review. |
| `...after_repair_round3.json` | 9 rejected / 51 pending | Tightened semantic repetition and unsupported-fact constraints. |
| `...after_repair_round10.json` | 5 rejected / 55 pending | Made judge seeds trajectory-ID-stable and order-independent. |
| `...after_repair_round12.json` | 1 rejected / 59 pending | Continued model-family replacement rather than changing thresholds. |
| `...after_full_dual_round14.json` | 3 rejected / 57 pending | Replaced IA_PIPE_002/004/010; IA_PIPE_002 required a GLM policy experiment after Qwen retries failed. |
| `...after_full_dual_round18.json` | 0 semantic rejects / 60 pending history | Completed 100% Qwen + GLM review. |
| `...after_history_round19.json` | 57 passed / 3 history rejected | Replaced IA_PIPE_003/011/014 and reran only the new IDs. |
| `...after_history_repair_round21.json` | 60 trajectory audits passed | History and dual-judge evidence exactly covered active IDs. |
| `...after_t2_rebalance_round23.json` | 60 trajectory audits passed | Rebalanced IA_PIPE_014 to preserve within-source-model T2 pairing, then reran both filters. |

The first history implementation compared an observed rollout action against a
new intervention sample. That can confound history with sampling. Seven pilot
records were retained as
`history_dependence_pre_controlled_full_probe.json`; they are not used as final
evidence. The corrected run regenerates Full/Recent/Removed actions under an
identical seed and stores the original action only as
`observed_checkpoint_action`.

## Candidate and archive accounting

- Candidate attempt logs: 80 records total — 22 accepted, 35 semantic rejects,
  and 23 generation/validator rejects.
- Every attempt log contains scenario/policy/attempt IDs, observable turns,
  structural audit, both judge records when available, semantic audit, status,
  and error text when generation failed.
- Active pool: 60 trajectories — Qwen3.5-9B 42, Qwen3-32B-AWQ 16, GLM-4-9B 2.
- Audit archive: 123 displaced trajectories — 75 `four_gate_rejected`, 1
  `t2_pairing_rebalance`, and 47 earlier structural-cleaning records predating
  the explicit reason field.
- Rejected files are removed from active manifests and moved under each
  scenario's `rollouts/rejected/`; they are retained only to satisfy the
  requested experimental audit trail.

## Final development evidence

- `data/formal/experiments/development_gate3_final/judgments.primary.json`
- `data/formal/experiments/development_gate3_final/judgments.secondary.json`
- `data/formal/experiments/development_gate3_final/judgments.merged.json`
- `data/formal/experiments/development_gate3_final/history_dependence.json`
- `reports/experiments/2026-09-06_four_gate_after_t2_rebalance_round23.json`
- `reports/experiments/2026-09-06_four_gate_final_development.json`
- `reports/experiments/2026-09-06_final_development_pool_audit.json`
- `reports/experiments/2026-09-06_final_instance_quality.json`

The four-gate report correctly remains non-research-ready. Its 60 per-trajectory
Gate 3 audits pass, while the Gate 3 pool contract rejects this development pool
for formal-release shortfalls (three model families, 12 raw trajectories per
scenario, and policy/environment separation). Gate 2 reports E1–E5 as pending
and the measured Qwen–GLM E6 backbone sensitivity as failed.

After the final active IDs were frozen, all downstream tasks and human-readable
descriptions were rebuilt. The merged manifest contains exactly 20 scenarios,
60 trajectories, 120 T1, 40 T2 and 20 T3 instances (180 total). Instance
structural checks pass 180/180, scenario bundles are ready for human spot-check
20/20, core tests pass 138/138 and web tests pass 4/4. Reusable T3 records were
accepted only when their source trajectory remained active and their complete
branch structure passed a fresh audit; all other T3 records were regenerated.
