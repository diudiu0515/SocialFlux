# Task-specific source-selection iteration log

日期：2026-09-07

## 目标

把旧的模型家族均衡、同模型 T2 配对和按轮询/最早 turn 取样，替换为统一质量门后的 T1/T2/T3 独立择优。模型身份只保留为 provenance，不进入分数，也不设入选配额。

## 实验观察与修正

1. 旧 20 个 T3 全部来自 `t1`，公开历史长度为 0。结论：结构上存在 T3 不代表它能测长期选择影响；新构建禁止无历史 checkpoint。
2. 第一版 T3 深度分数单调增加，因而总是先试 `t6`。IA_PIPE_007 与 IA_PIPE_009 的 `t6` 都因 continuation 重复而被拒绝，回退到较早 checkpoint 后成功。对应逐次证据写入各场景 `validation/t3_selection_attempts.json`。
3. 环境 response 的 strict distinct-text 门原为内层最多 12 次，完整 branch 又外层重放 6 次，单 checkpoint 最坏 72 次无效生成。先修正为内层 4 次、外层 2 次；随后 IA_PIPE_016 长时间回退实验发现生成阈值 0.72 与最终结构门 0.92 不一致。最终将生成阈值对齐为 0.92，同时继续拒绝完全重复、格式错误与无依据的场外事实；这是门限一致性修复，不是跳过质量门。
4. T3 checkpoint utility 改为在 episode 约 `2/3` 位置达峰，兼顾已有历史和后续演化空间。对 6-turn rollout 优先 `t4`，随后按 utility 与来源专项质量排序。
5. 旧 T1 虽按 trajectory 排名，仍固定抽每条最早两轮。修正为来源专项质量 0.75 + 历史深度 0.15 + 本轮 state information 0.10；私有 state information 只参与抽样，不写入公开 instance。

## 固定评分

- T1 source：state–response consistency 0.40、history dependence 0.25、dialogue coherence 0.20、character consistency 0.15。
- T2 source：history dependence 0.35、state–response consistency 0.25、dialogue coherence 0.15、naturalness 0.15、character consistency 0.10。Pair 总分为来源质量 0.55 + 归一化 private-state divergence 0.45。
- T3 source：interaction progression 0.30、state–response consistency 0.25、dialogue coherence 0.20、naturalness 0.15、character consistency 0.10；source 占 checkpoint 总分 0.90，checkpoint utility 占 0.10。

最终全量结果、模型实际分布与逐 scenario 来源由 `2026-09-07_task_source_selection_audit.json/.md` 生成；该分布是结果，不是目标配额。

## 最终开发包结果

- 20/20 scenario 完成专项选源；T1=120、T2=40、T3=20，共 180 个唯一实例，结构 180/180。
- T1 历史长度 1–6、均值 4.72；T2 为 1–5、均值 3.70；T3 公开历史最少 4、均值 8.4 条。
- 20 个 T3 共 60 条分支，均为 5-turn delayed continuation；18 个被拒 checkpoint 保留失败原因和顺序。
- 按任务实际使用的唯一来源统计，T1 为 Qwen3.5/Qwen3-32B/GLM = 38/9/2，T2 = 32/12/1，T3 = 15/4/1，DeepSeek = 0。该分布是结果，不是目标配额。
- `scripts/audit_task_source_selection.py` 最终为 20/20 PASS；180 个实例与 20 个自然语言 `tasks.md` 都记录实际来源，public JSON 未暴露 T1 state-information 或 T2 private-state distance。
- 边界：当前开发 active pool 只有每场景 3 条；正式 12-run raw pool、4–6 selected 和真人 Gate 仍未完成，不得把本结果标作 formal clean pool。
