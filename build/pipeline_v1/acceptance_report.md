# SocialFlux Pipeline Acceptance

本报告由 scripts/run_acceptance.py 生成。自动通过不等于替代人工语义验收。

| 验收项 | 状态 | 结果 |
|---|---|---|
| 1. State Update Validity | passed | 210/210 checks |

One-turn numeric transitions match every configured semantic state_delta direction.

| 2. Persona Sensitivity | failed | see JSON details |



原因：The default RuleBasedStateUpdater reads action_effects but does not apply persona-conditioned modifiers. ModelStateUpdater receives persona through the centralized appraisal prompt, but no provider-backed behavioral run is configured in this acceptance.

后续：Add calibrated persona modifiers or run a provider-backed model transition set, then compare interpretable deltas.

| 3. Paraphrase Robustness | partial | 30/30 checks |

Exact robustness holds when the structured action_id is fixed. This is not yet an end-to-end natural-language paraphrase test because the full pipeline has no action normalization/interpreter component.

后续：Add a versioned action interpreter/normalizer and test paraphrase pairs before state update.

| 4. Controlled Policy Sensitivity | passed | 10/10 scenarios |

Repair, neutral and escalation produce configured directional divergence across all scenarios.

| 5. Full Trajectory Plausibility | pending_human_judgment | 10/10 scenarios structurally valid |

Automated structural checks pass; human reviewers must judge semantic plausibility.

## Gate

- Automated engineering checks: passed
- Research acceptance: not accepted until persona, paraphrase end-to-end, and human trajectory review are complete.

完整逐项 evidence 保存在同目录的 acceptance_report.json。
