# SocialFlux Tasks v1

T1/T2/T3 都从自然模型轨迹派生，未标注 candidate 的 `ground_truth` 必须是 `null`。Simulator private state 只能支持环境诊断，不能自动成为正式 human ground truth。

- T1：自然 checkpoint 的 latent social state estimation。
- T2：自然分化历史 + 完全相同 O* 的 history-conditioned comparison。
- T3：真实 checkpoint 上 2–4 个自由文本行动的 immediate/delayed effect。
- T4：直接进入同一 canonical environment 的在线自由互动，定义见 framework 与 prompts。

各目录保留对应概率统计工具。当前输出合同在 `schemas/task_t1_output.schema.json`、`task_t2_output.schema.json` 与 `task_t3_output.schema.json`；固定模型 prompt 位于 `prompts/`。

## Private Persona boundary

Public T1/T2/T3/T4 instances never contain the environment character's stable Persona, hidden intention, S/D values, appraisal, or deltas. Author-side environment generation and machine answer-proposal LLMs receive the stable Persona through a separate private context. They may use it to condition interpretation but may not cite it as public evidence or serialize it into the benchmark instance or answer. The evaluated model receives only public identity, role, explicit goal, scenario facts, observable history, and observable expression.
