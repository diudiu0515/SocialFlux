# SocialFlux Project Progress

更新时间：2026-09-06

| 模块 | 状态 | 证据/限制 |
|---|---|---|
| v2 架构迁移 | 已完成 | 自由 action、单一环境、自然 rollout、局部 intervention |
| Hybrid scenario source | 结构已完成 | 15 narrative-derived + 5 synthetic-script；来源真实性、原创性与质量仍待真人复核 |
| 两阶段 scenario 创建 | 已完成 | source quality approval → normalization → candidate S0/D0 |
| 20 个 scenario bundle | 候选完成 | 保留原 10 个并新增 10 个影视结构启发场景；全部带 JSON、同名 Markdown、coverage，S0/D0 尚未 human_frozen |
| Prompt catalog | 已完成 | 21 个版本化 prompt、SHA-256 manifest、职责与边界审计 |
| Provider/model pool | 已完成 | OpenAI-compatible、Anthropic、Gemini、vLLM；真实密钥/endpoint 由本地配置提供 |
| 自然 rollout | 20 场景开发运行已完成 | Qwen3.5-9B；每 scenario 3 seeds × 6 turns，共 60 条自然轨迹；scenario 未 human-freeze，不能作为正式数据 |
| T1/T2/T3 builders | 已完成 | natural checkpoint、natural divergent history + O*、local branch |
| Instance 质量审计 | 20 场景已完成 | T1=120、T2=40、T3=20，共 180/180 通过结构门；严格清洗与定向重采样后 60/60 轨迹通过机器质量门，人工 plausibility 仍待评审 |
| GPT–Qwen rollout 对照 | GPT 侧受凭据阻塞 | 官方 Qwen3.5-9B 已下载并完成 pilot；匹配配置、同模型 T2 分层和盲审已就绪；当前环境未设置 `OPENAI_API_KEY`，不能宣称胜负 |
| T4 | 核心交互已完成 | 与离线共用环境；正式 judge/human 校准待完成 |
| Talking Head | 机器生成与验收已完成 | EchoMimicV2 四卡生成 40/40 MP4；音轨、时长、分辨率与帧率自动校验通过，表达—状态与时序自然度待真人检查 |
| 九项验收 | 框架已完成 | 当前正式结果为 pending；需要自然轨迹、模型实验与真人评审 |
| 网站 | 已完成 | 只读展示 scenario、自然轨迹、完整对话、T1/T2/T3 人工抽查文档、状态、trigger 与 Talking Head 视频 |
| 清理 | 已完成 | 删除 demo、controlled policy、旧 world benchmark、旧 prompt/schema/build |
| 测试 | 已通过 | core 74/74、web 4/4；20 scenario paired Markdown、40 media request/video、prompt/scenario manifests 全部一致 |

## Qwen3.5-9B 20-scenario 开发运行

- 主轨迹：20 个 scenario × 3 个 seeds × 6 轮上限，共 60 条；模型为官方 `Qwen/Qwen3.5-9B`，base seeds 101/202/303，组件调用按 base seed + call index 推进。
- 离线实例：每 scenario T1=6、T2=2、T3=1；全量 T1=120、T2=40、T3=20。每个 T3 有 3 个候选行动、3 个即时分支和每分支 5 轮延迟 continuation。
- 人工抽查材料：20/20 scenario 均在自身 `rollouts/` 下包含完整自然语言 `dialogues.md` 与逐 instance 的 `tasks.md`；bundle audit 为 20/20 ready。
- 结构质量：180/180 instance 通过合同、角色、泄漏、历史形状和 branch 完整性检查。初次 T2 有 10 个拒绝项，已通过非重复 history 检索与 `t2_shared_observation_v3` speaker lock 定向重建。
- 完整轨迹：初版仅 22/60 通过精确重复门；加强近重复、舞台指示和角色标签检查后，对 47 条不合格轨迹定向重采样，当前 60/60 通过机器 clean-pool gate。Full-Trajectory Plausibility 仍须真人评审，不能把机器 clean 等同于研究验收通过。
- 九项 gate：Local Action Intervention 与 Seed Robustness 为 `evidence_ready`；其余（含 Full-Trajectory Plausibility）保持 `pending`；research acceptance 为 false。

本地可再生产物位于 `build/pipeline_v2/`，轨迹、`dialogues.md` 与 `tasks.md` 位于各 `configs/scenarios/scenario_NNN/rollouts/`；两处按 `.gitignore` 不提交 private/generated 数据。

## 不能提前宣称完成的研究工作

- 20 个 scenario 的来源、质量门与 S0/D0 人工审核；
- 多模型、多 seed 的真实自然 rollout pool；
- 30–50 transition 的三人 state-update 标注；
- 15–20 完整轨迹的三人 plausibility 评审；
- Persona、Paraphrase、History、Neutral、Response-State 和 Seed 实验结果；
- T1/T2/T3 正式 human ground truth 与 T4 judge 校准；
- Talking Head temporal/semantic 人工检查（实际 40 条资产和机器媒体验收已完成）。

工程完成与研究验收分开记录；没有证据时状态保持 pending。
