# SocialFlux Project Progress

更新时间：2026-09-03

| 模块 | 状态 | 证据/限制 |
|---|---|---|
| v2 架构迁移 | 已完成 | 自由 action、单一环境、自然 rollout、局部 intervention |
| Hybrid scenario source | 结构已完成 | 15 narrative-derived + 5 synthetic-script；来源真实性、原创性与质量仍待真人复核 |
| 两阶段 scenario 创建 | 已完成 | source quality approval → normalization → candidate S0/D0 |
| 20 个 scenario bundle | 候选完成 | 保留原 10 个并新增 10 个影视结构启发场景；全部带 JSON、同名 Markdown、coverage，S0/D0 尚未 human_frozen |
| Prompt catalog | 已完成 | 21 个版本化 prompt、SHA-256 manifest、职责与边界审计 |
| Provider/model pool | 已完成 | OpenAI-compatible、Anthropic、Gemini、vLLM；真实密钥/endpoint 由本地配置提供 |
| 自然 rollout | 开发 pilot 已运行 | IA_PIPE_011：Qwen3.5-9B × 2 seeds × 6 turns；scenario 未 human-freeze，不能作为正式数据 |
| T1/T2/T3 builders | 已完成 | natural checkpoint、natural divergent history + O*、local branch |
| Instance 质量审计 | 已完成并实测 | Qwen pilot 提取 T1=4/T2=2/T3=1；6/7 过结构门，1 个 T2 因重复历史拒绝；2/2 完整轨迹未过重复门 |
| GPT–Qwen rollout 对照 | GPT 侧受凭据阻塞 | 官方 Qwen3.5-9B 已下载并完成 pilot；匹配配置、同模型 T2 分层和盲审已就绪；当前环境未设置 `OPENAI_API_KEY`，不能宣称胜负 |
| T4 | 核心交互已完成 | 与离线共用环境；正式 judge/human 校准待完成 |
| Talking Head | trigger/spec 已完成 | 稀疏 threshold/crossing 与安全 media spec；真实视频生成/人工检查待接入 |
| 九项验收 | 框架已完成 | 当前正式结果为 pending；需要自然轨迹、模型实验与真人评审 |
| 网站 | 已完成 | 只读展示当前 scenario、自然轨迹、状态与 trigger |
| 清理 | 已完成 | 删除 demo、controlled policy、旧 world benchmark、旧 prompt/schema/build |
| 测试 | 已通过 | core 54/54、web 4/4；20 scenario paired Markdown、prompt/scenario manifests 全部一致 |

## Qwen3.5-9B 开发 pilot（IA_PIPE_011）

- 主轨迹：2 条，每条 6 轮；模型为官方 `Qwen/Qwen3.5-9B`，base seeds 101/202，组件调用按 base seed + call index 推进。
- 离线实例：T1 4、T2 2、T3 1；T3 有 3 个候选行动、3 个即时分支和每分支 5 轮延迟 continuation。
- 结构质量：6/7 通过，均无 private-state 泄漏；未通过项是 1 个含精确重复回合的 T2 history。
- 完整轨迹：0/2 通过严格无重复门；action 唯一率分别 0.8333/1.0，response 唯一率 0.8333/0.5，latent 边界占比分别 0.4167/0.3333。
- Qwen 自盲审均分：T1 4.85、T2 4.8、T3 5.0，但它漏判了重复历史，只能记录为偏乐观的 diagnostic，不能作为模型胜负或 human GT。
- 九项 gate：Local Action Intervention 与 Seed Robustness 为 `evidence_ready`；其余（含 Full-Trajectory Plausibility）保持 `pending`；总自动门为 false。

本地可再生产物位于 `build/model_comparison/qwen35_pilot/`，轨迹与 `dialogues.md` 位于 `configs/scenarios/scenario_011/rollouts/`；两处按 `.gitignore` 不提交 private/generated 数据。

## 不能提前宣称完成的研究工作

- 20 个 scenario 的来源、质量门与 S0/D0 人工审核；
- 多模型、多 seed 的真实自然 rollout pool；
- 30–50 transition 的三人 state-update 标注；
- 15–20 完整轨迹的三人 plausibility 评审；
- Persona、Paraphrase、History、Neutral、Response-State 和 Seed 实验结果；
- T1/T2/T3 正式 human ground truth 与 T4 judge 校准；
- Talking Head 实际资产及 temporal/semantic 人工检查。

工程完成与研究验收分开记录；没有证据时状态保持 pending。
