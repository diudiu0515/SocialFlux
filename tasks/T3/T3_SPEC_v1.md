# T3 Specification v1

当前主评测见 [offline 选择题协议](../../docs/protocols/OFFLINE_T1_T3_CHOICE_V1.md)。本文件描述旧概率接口；新协议只需一个答案，证据另行诊断。

从一条自然轨迹的真实 checkpoint 构造 2–4 个局部合理、语义不同的自由文本候选行动。所有 branch restore 同一 private snapshot，先执行 candidate，再使用与源 trajectory 匹配的同一自由模型配置继续默认 5 轮、最多 10 轮。

主任务只提供公开 history/checkpoint/actions/horizon，不提供 persona、oracle state、
实际未来 branch、hidden intention、appraisal 或 trigger logic。被测输出合同为
`schemas/task_t3_output.schema.json`。这些 2–4 条 branch 是从同一 snapshot
出发的受控 task intervention，不是额外自然 rollout，也不做多 seed 投票。
Simulator branch 是可审计 machine proposal；正式 immediate/delayed 方向必须经过
Gate 4 的同样本双人抽查。
