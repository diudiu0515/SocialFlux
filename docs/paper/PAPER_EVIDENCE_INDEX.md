# SocialFlux Paper Evidence Index

该索引把论文可能使用的主张绑定到可复核文件，避免写作时从中间轮次或旧 Prompt 误取结论。

| 论文部分 | 权威说明 | 实现/证据 | 当前边界 |
|---|---|---|---|
| Problem & construct | [`Framework Definition`](../../EmoTree_Framework_Definition_v4.md) | [`Architecture`](../architecture/ARCHITECTURE.md) | 架构已实现，正式研究验收未完成 |
| Scenario construction | [`Pipeline`](../architecture/PIPELINE.md) | `configs/scenarios/scenario_NNN/{json,md}` | 20 个 candidate bundle；S0/D0 待真人冻结 |
| Prompt design | [`Prompt Audit`](../prompts/PROMPT_AUDIT.md) | [`prompts/`](../../prompts/) + manifest + schemas | 24 个 catalog Prompt；v1 Judge 仅 legacy |
| Rollout screening | [`Screening Protocol v1`](../protocols/SocialFlux_Rollout_Screening_Protocol_v1.md) | [`screening execution log`](../../reports/experiments/2026-09-07_rollout_screening_protocol_v1.md) | 184 条开发库存、20 条 provisional winner；未人工 freeze |
| Formal rollout pool | [`gate.md`](../protocols/gate.md) | [`Formal Runbook`](../operations/FORMAL_ROLLOUT_RUNBOOK.md) | 20×12 formal raw 尚未生成 |
| Development Gate filtering | [`filtering log`](../../reports/experiments/2026-09-06_gate_filtering_log.md) | [`final development report`](../../reports/experiments/2026-09-06_four_gate_final_development.md) | 只代表开发池，不是 formal clean pool |
| T1/T2/T3 source selection | [`selection iteration`](../../reports/experiments/2026-09-07_task_selection_iteration.md) | [`source audit`](../../reports/experiments/2026-09-07_task_source_selection_audit.md) | 180 个开发实例；正式 Gate 4/GT 未完成 |
| Human review UI | [`web README`](../../web/README.md) | `web/server.py`, `web/static/` | 展示所有人工项；浏览器草稿不是签名证据 |
| Talking Head | [`source note`](../source-notes/talkinghead_generation.md) | `media/talking_head/manifest.json` | 40 个视频机器验收通过，语义/时序待真人 |
| Multimodal revision | [`multimodel proposal`](../source-notes/multimodel.md) | `environment/multimodal.py` 已实现 priority/单轮单事件 | 三事件 scenario/schema/资产尚未迁移 |

## 可引用的当前数字

- 20 个 scenario：10 narrative-derived、10 synthetic-script。
- 开发 active pool：60 条；完整可恢复筛选库存：184 条。
- Protocol v1 自动判定：PASS 64、REVIEW 108、REJECT 12。
- 每场景 1 条自动推荐：20 条，状态为 provisional pending human comparative review。
- 开发任务：T1=120、T2=40、T3=20，共 180。
- Talking Head：40 条机器媒体验收通过；人工表达、时序、语音和多模态效用未验收。

这些数字必须与 `PROJECT_PROGRESS.md` 和最新机器报告交叉核对。不得把 `evidence_ready`、自动 PASS、结构通过或 provisional winner 写成真人通过或正式 benchmark 结论。

## 历史实验

开发筛选的 round-by-round JSON/Markdown 与 candidate attempts 保留在 [`reports/experiments/archive/development-filtering/`](../../reports/experiments/archive/development-filtering/)。它们用于复现失败、替换和阈值演化，不应作为论文主结果；主文优先引用当前结论级报告。
