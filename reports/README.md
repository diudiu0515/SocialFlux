# SocialFlux Experiment Reports

`experiments/` 顶层只放当前结论级或论文需要直接引用的报告；中间迭代进入 `experiments/archive/`。移动到 archive 不表示删除，轨迹替换、Judge 变化和失败尝试仍可追溯。

## 当前报告

- `2026-09-06_final_development_pool_audit.json`：开发 active pool 最终库存审计。
- `2026-09-06_final_instance_quality.{json,md}`：开发 T1/T2/T3 质量汇总。
- `2026-09-06_four_gate_final_development.{json,md}`：四 Gate 开发状态；总体不是正式通过。
- `2026-09-06_gate_filtering_log.md`：修复与替换过程摘要。
- `2026-09-07_rollout_screening_protocol_v1.md`：旧184条六轮库存按新20轮合同重筛，184条全部REJECT且无winner。
- `2026-09-08_long_horizon_t4_smoke.md`：20轮T4与raw生成 smoke、失败分析、Prompt hash和排除决定。
- `2026-09-07_task_selection_iteration.md`：任务专项选源迭代。
- `2026-09-07_task_source_selection_audit.{json,md}`：T1/T2/T3 选源审计。

## 归档

`experiments/archive/development-filtering/` 保存各轮 four-gate 快照、双 Judge/history 修复结果和 candidate-attempt JSONL。论文主文不直接采用其中的中间计数；需要解释筛选过程或失败分析时通过最终日志定位具体轮次。
