# SocialFlux Pipeline

当前生产主链只有一条，公开入口只有 `python -m pipeline`：

```text
300 Scenario
  → Gate 1：Scenario / S0-D0 冻结
  → 每场景 3 个 seed 的自然 rollout
      Policy 自由文本 action
      → Appraisal LLM
      → Python 确定性状态更新
      → Response LLM
      → Ledger / 下一轮 observation
  → Gate 2：Environment validity
  → Gate 3：Trajectory 筛选与 canonical selection
  → T1 / T2 / T3 构建；T4 在线评测
  → Gate 4：任务实例与答案抽查
```

## 运行时边界

- 唯一场景目录：`configs/scale300_v1/scenarios`，必须恰好包含 300 个 scenario 及同名 Markdown。
- 每个 scenario 恰好有 3 个独立 seed，各生成一条自然候选轨迹。
- Policy 只输出自由文本 action，不读取 action transition table。
- Appraisal 和 Response 是独立语义调用；二者之间只有 Python 负责确定性状态更新。
- Ledger 保存已发生的公开事件、模型 action/response 和下一轮 observation，不暴露 hidden intention、persona、S/D、appraisal 或 delta。
- 所有 active 语义角色统一路由到 `claude-fable-5`。业务模块不写死 provider，也不允许 policy 级 environment override。
- `pipeline/runtime.py` 是 Fable provider、policy 和 environment factory 的唯一组装位置。

## 四个 Gate

| Gate | 阻断条件 | 通过后的产物 |
|---|---|---|
| Gate 1 | scenario 未 approved，或 S0/D0 未 human_frozen | 可生成的 frozen scenario |
| Gate 2 | environment 的 E1–E6 证据不足或失败 | environment-valid trajectories |
| Gate 3 | 结构、自然结束、语义质量或 history/Judge 证据不足 | 每场景 1 条 canonical trajectory |
| Gate 4 | T1/T2/T3 实例或答案人工抽查未通过 | 可发布任务与答案 |

`pending` 不能被程序改写成 `passed`。`--allow-unreviewed` 只用于诊断，不能产出正式数据。

## 唯一运行顺序

```bash
# 300 scenarios × 3 seeds 与 Fable-only 路由检查
python -m pipeline preflight

# Gate 1 已冻结后，生成 900 个 raw candidate slots
python -m pipeline rollout \
  --review-registry reviews/scale300_scenario_review.json \
  --output data/formal/raw --workers 4 --retry-limit 3 --resume

# Gate 2 通过后执行 Gate 3 审计、筛选与 canonical materialization
python -m pipeline gate3 \
  --raw-root data/formal/raw \
  --stage formal \
  --review-registry reviews/scale300_scenario_review.json \
  --environment-evidence data/formal/environment_evidence \
  --judgments data/formal/judgments.json \
  --history-evidence data/formal/history.json \
  --output data/formal/gate3_report.json \
  --selected-root data/formal/selected

# 只消费 Gate 3 选出的 canonical trajectories
python -m pipeline tasks \
  --rollout-root data/formal/selected \
  --review-registry reviews/scale300_scenario_review.json \
  --environment-evidence data/formal/environment_evidence \
  --gate3-report data/formal/gate3_report.json \
  --output data/formal/tasks

# T4 复用同一个 stateful environment
python -m pipeline t4 --output data/formal/t4

# Gate 4 与最终严格审计
python -m pipeline audit \
  --rollout-stage selected \
  --raw-root data/formal/selected \
  --pipeline-output data/formal/tasks \
  --review-registry reviews/scale300_scenario_review.json \
  --environment-evidence data/formal/environment_evidence \
  --judgments data/formal/judgments.json \
  --history-evidence data/formal/history.json \
  --human-task-review data/formal/gate4_review.json \
  --output data/formal/four_gate_report.json --strict
```

`scripts/generate_long_rollout_pool.py`、`scripts/run_quality_gates.py`、
`scripts/run_pipeline.py` 和 `scripts/run_t4_evaluation.py` 是各阶段的内部 worker，
不再是并列的用户入口。历史配置、旧 20 场景和旧 rollout 仅用于诊断与复现实验，
不参与 active pipeline。

正式运行和人工证据格式见
[Formal Rollout Runbook](../operations/FORMAL_ROLLOUT_RUNBOOK.md)；
全部不可变约束见 [DESIGN_CONTRACT](../../DESIGN_CONTRACT.md)。
