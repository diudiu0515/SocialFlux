# T3 Specification v1

从一条自然轨迹的真实 checkpoint 构造 2–4 个局部合理、语义不同的自由文本候选行动。所有 branch restore 同一 private snapshot，先执行 candidate，再使用与源 trajectory 匹配的同一自由模型配置继续默认 5 轮、最多 10 轮。

主任务只提供公开 history/checkpoint/actions/horizon，不提供 oracle state、实际未来 branch、hidden intention、appraisal 或 trigger logic。被测输出合同为 `schemas/task_t3_output.schema.json`。Simulator branch 是 validation evidence，不自动成为 ground truth；正式 immediate/delayed 方向需独立人类标注与多 seed 稳定性检查。
