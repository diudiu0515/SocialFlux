# SocialFlux Tasks

新增 [v2 能力框架与任务合同](../docs/protocols/OFFLINE_T1_T3_CHOICE_V2.md)，当前默认是 [50 场景新版题库](examples/offline_scenarios_v2/examples.md)：每场景 T1/T2/T3 各 2 题。网站 `/offline-demo` 可按场景查看、试答与筛选能力／难度。另保留 [24 道首批题型示例](examples/offline_design_v2/examples.md)和旧 460 题迁移记录；v1 生成配方及历史资产用于复现。

当前新版开发题采用 `socialflux_offline_choice_v2`；[旧 v1 选择题协议](../docs/protocols/OFFLINE_T1_T3_CHOICE_V1.md)继续兼容。主回答只需 `{"answer":"B"}`，证据为独立诊断模式，下述概率合同保留用于旧资产复现。新版尚待人工核验，不据机器一致性自动变成正式真值。

Git 中保存了 2026-10-10 的 [60 题完整可读样例](examples/offline_t1_t3_dev60/examples.md)、
[机器可读题目](examples/offline_t1_t3_dev60/items.jsonl)及 [来源与哈希](examples/offline_t1_t3_dev60/snapshot.json)。
这是待人工审核的开发快照，4 道 T3 尚缺完整回放，不是正式真值集。网站仍读取
`data/offline_t1_t3_dev60/` 的工作数据；Git 快照不参与运行时加载，原始调用、
环境快照、视频与个人标注不包含在其中。

T1/T2/T3 都从自然模型轨迹派生，未标注 candidate 的 `ground_truth` 必须是 `null`。Simulator private state 只能支持环境诊断，不能自动成为正式 human ground truth。

- T1：自然 checkpoint 的 latent social state estimation。
- T2：自然分化历史 + 完全相同 O* 的 history-conditioned comparison。
- T3：真实 checkpoint 上 2–4 个自由文本行动的 immediate/delayed effect。
- T4：直接进入同一 canonical environment 的在线自由互动，定义见 framework 与 prompts。

各目录保留对应概率统计工具。当前输出合同在 `schemas/task_t1_output.schema.json`、`task_t2_output.schema.json` 与 `task_t3_output.schema.json`；固定模型 prompt 位于 `prompts/`。

## Private Persona boundary

Public T1/T2/T3/T4 instances never contain the environment character's stable Persona, hidden intention, S/D values, appraisal, or deltas. Author-side environment generation and machine answer-proposal LLMs receive the stable Persona through a separate private context. They may use it to condition interpretation but may not cite it as public evidence or serialize it into the benchmark instance or answer. The evaluated model receives only public identity, role, explicit goal, scenario facts, observable history, and observable expression.
