# T2 Specification v1

从唯一自然 rollout A 中选择一个有共享前史的 checkpoint，在锚定区间内受控改写
History B。B 保留角色、background、分叉前历史和已成立事实，不得再生成第二条
自然 rollout，也不得新增区间外事件来制造差异。

A/B 都从各自分叉 checkpoint 经过正式 Structured Appraisal → Python 确定性更新
→ Response 路径独立重放；B 不能沿用 A 的后续 private state。随后注入一个对两侧
都自然的完全相同 O*。O* 的 text、expression、media 与 metadata 必须字节级一致，
并通过真人 compatibility 与 leakage 检查。

被测模型只依据公开 History A/B 与 O* 输出 pairwise direction、双方 evidence、
causal relevance 与 confidence，合同为 `schemas/task_t2_output.schema.json`。
Source trajectory IDs 和 persona 只留在 construction/private answer metadata，
不进入 model input。正式答案必须经过 Gate 4 人工抽查。
