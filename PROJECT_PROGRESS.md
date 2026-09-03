# SocialFlux Project Progress

更新时间：2026-09-03

| 模块 | 状态 | 证据/限制 |
|---|---|---|
| v2 架构迁移 | 已完成 | 自由 action、单一环境、自然 rollout、局部 intervention |
| Hybrid scenario source | 结构已完成 | 15 narrative-derived + 5 synthetic-script；来源真实性、原创性与质量仍待真人复核 |
| 两阶段 scenario 创建 | 已完成 | source quality approval → normalization → candidate S0/D0 |
| 20 个 scenario bundle | 候选完成 | 保留原 10 个并新增 10 个影视结构启发场景；全部带 JSON、同名 Markdown、coverage，S0/D0 尚未 human_frozen |
| Prompt catalog | 已完成 | 20 个版本化 prompt、SHA-256 manifest、职责与边界审计 |
| Provider/model pool | 已完成 | OpenAI-compatible、Anthropic、Gemini、vLLM；真实密钥/endpoint 由本地配置提供 |
| 自然 rollout | 待运行 | 仓库没有伪造 API 轨迹；需先完成 scenario review 与模型配置 |
| T1/T2/T3 builders | 已完成 | natural checkpoint、natural divergent history + O*、local branch |
| T4 | 核心交互已完成 | 与离线共用环境；正式 judge/human 校准待完成 |
| Talking Head | trigger/spec 已完成 | 稀疏 threshold/crossing 与安全 media spec；真实视频生成/人工检查待接入 |
| 九项验收 | 框架已完成 | 当前正式结果为 pending；需要自然轨迹、模型实验与真人评审 |
| 网站 | 已完成 | 只读展示当前 scenario、自然轨迹、状态与 trigger |
| 清理 | 已完成 | 删除 demo、controlled policy、旧 world benchmark、旧 prompt/schema/build |
| 测试 | 已通过 | core 45/45、web 4/4，20 scenario JSON Schema 与 paired Markdown 全通过 |

## 不能提前宣称完成的研究工作

- 20 个 scenario 的来源、质量门与 S0/D0 人工审核；
- 多模型、多 seed 的真实自然 rollout pool；
- 30–50 transition 的三人 state-update 标注；
- 15–20 完整轨迹的三人 plausibility 评审；
- Persona、Paraphrase、History、Neutral、Response-State 和 Seed 实验结果；
- T1/T2/T3 正式 human ground truth 与 T4 judge 校准；
- Talking Head 实际资产及 temporal/semantic 人工检查。

工程完成与研究验收分开记录；没有证据时状态保持 pending。
