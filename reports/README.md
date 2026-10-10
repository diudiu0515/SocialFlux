# SocialFlux Experiment Reports

报告只用于方法选择、失败分析和审计，不能替代当前批次的 Gate 证据。

## 当前交付与实验入口

- [2026-10-10 Offline T1–T3 开发题](experiments/2026-10-10_offline_t1_t3_dev60.md)：60 题设计、56 题完成回放、真实试答、局限与网站标注验证。
- [2026-10-08 T4 GPT50 结果](experiments/2026-10-08_t4_gpt50_results.txt)：该次 T4 运行结果；与 offline 题库分开统计。
- [2026-10-08 视频覆盖修正](experiments/2026-10-08_gpt50_video_coverage_correction.txt)：批次媒体覆盖与来源核查。
- 项目当前配置、运行路径和清理记录见[架构文档](../docs/architecture/ARCHITECTURE.md)；历史报告中的“当前”指报告当时的状态。

## 仍支撑当前方法，保留

- `2026-09-07_task_selection_iteration.md`：质量优先、任务专项选源、不设模型配额。
- `2026-09-09_gate2_environment_interventions.md`：现行 Gate 2 E1–E6 实验结构。
- `2026-09-13_development_six_natural_interaction.md`：自然结束、最多 20 轮和两阶段环境的失败边界。
- `2026-09-16_t2_expression_history_dev.md`：T2 受控历史差异、共享 ending 和证据合同。
- `2026-09-17_autodl_board_model_selection.md`：当前 Fable route table 的选型依据。

这些报告中的模型计数和开发结果不是当前 GPT50/Claude150 的正式结果；当前结果必须由
对应 run manifest 和 Gate 证据给出。

## 历史复现与审计记录

- 2026-09-06 的六轮 development pool、instance 和 four-gate 报告；
- 2026-09-07 的旧 184 条筛选结果及 source-selection 结果快照；
- 2026-09-08 的旧 prompt / 多模型 T4 smoke；
- 2026-09-10 至 09-11 的 R3/Qwen 迭代与 ablation；
- 2026-09-17 早期 API role/integrated/task-model 对照；这些已被 Fable board
  selection 取代；
- `experiments/archive/development-filtering/` 的旧六轮逐轮快照。

上述文件保留为可审计历史，不作为活跃数据入口。本轮整理不删除实验结论或失败证据；
即使部分内容完全相同，不同轮次的来源记录也不按普通重复文件处理。
