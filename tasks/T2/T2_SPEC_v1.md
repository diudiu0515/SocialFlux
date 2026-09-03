# T2 Specification v1

从同 scenario、同深度的自然轨迹中检索历史不同且 private state 有分化的 A/B，再注入一个对双方都合理的完全相同 O*。O* 的 text、expression、media 与 metadata 必须一致；需要真人 compatibility 与 leakage 检查。

被测模型只依据公开 History A/B 与 O* 输出 pairwise direction、双方 evidence、causal relevance 与 confidence，合同为 `schemas/task_t2_output.schema.json`。Source trajectory IDs 只留在 construction metadata，不进入 model input。正式答案来自独立人类标注。
