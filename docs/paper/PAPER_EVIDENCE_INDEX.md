# SocialFlux Paper Evidence Index

该索引把论文可能使用的主张绑定到可复核文件，避免写作时从中间轮次或旧 Prompt 误取结论。

| 论文部分 | 权威说明 | 实现/证据 | 当前边界 |
|---|---|---|---|
| Problem & construct | [Design Contract](../../DESIGN_CONTRACT.md) | [Architecture](../architecture/ARCHITECTURE.md) | 架构已实现，正式研究验收未完成 |
| Scenario construction | [`Pipeline`](../architecture/PIPELINE.md) | `configs/scenarios/scenario_NNN/{json,md}` | 20 个 candidate bundle；S0/D0 待真人冻结 |
| Prompt design | [`Prompt Audit`](../prompts/PROMPT_AUDIT.md) | [`prompts/`](../../prompts/) + manifest + schemas | 30 个 catalog Prompt；当前长程版本为 action v4、response v5、T4 judge v2 |
| Rollout screening | [`Screening Protocol v1`](../protocols/SocialFlux_Rollout_Screening_Protocol_v1.md) | [`screening execution log`](../../reports/experiments/2026-09-07_rollout_screening_protocol_v1.md) | 184 条旧六轮库存全部REJECT；无20轮winner |
| Formal rollout pool | [`gate.md`](../protocols/gate.md) | [`Formal Runbook`](../operations/FORMAL_ROLLOUT_RUNBOOK.md) | 20×3 quality-candidate pool 正在生成，尚未完成 Gate 3 人审 |
| Development Gate filtering | [`filtering log`](../../reports/experiments/2026-09-06_gate_filtering_log.md) | [`final development report`](../../reports/experiments/2026-09-06_four_gate_final_development.md) | 只代表开发池，不是 formal clean pool |
| T1/T2/T3 source selection | [`selection iteration`](../../reports/experiments/2026-09-07_task_selection_iteration.md) | [`source audit`](../../reports/experiments/2026-09-07_task_source_selection_audit.md) | 180个旧六轮来源实例仅作历史审计；20轮版本待重建 |
| Human review UI | [`web README`](../../web/README.md) | `web/server.py`, `web/static/` | 展示所有人工项；浏览器草稿不是签名证据 |
| Talking Head | [`source note`](../source-notes/talkinghead_generation.md) | `media/talking_head/manifest.json` | 60个视频机器验收通过，语义/时序待真人 |
| Multimodal revision | [`multimodel proposal`](../source-notes/multimodel.md) | `environment/multimodal.py`、scenario/schema和60条资产 | 每场景3事件已迁移；人工语义验收待完成 |
| T4 long-horizon smoke | [`smoke log`](../../reports/experiments/2026-09-08_long_horizon_t4_smoke.md) | `scripts/run_t4_evaluation.py`、`evaluation/t4_evaluation.py` | 20轮执行已验证；结果因质量问题排除，judge-human校准待完成 |

## 可引用的当前数字

- 20 个 scenario：10 narrative-derived、10 synthetic-script；全部配置20轮和3个视频事件。
- 旧筛选库存184条：全部只有6轮，因此当前Protocol v1自动判定REJECT=184，provisional winner=0。
- 旧开发任务T1=120、T2=40、T3=20仅供历史审计；不得作为新版20轮任务质量结论。
- 新开发池目标20×3=60条、每条最多20轮且主候选自然结束在10–20轮，生成进度以`build/rollout_20turn_3candidate/progress.json`为准；模型族只记录 provenance，不设配额。
- Talking Head：60条机器媒体验收通过；人工表达、时序、语音和多模态效用未验收。

这些数字必须与 `PROJECT_PROGRESS.md` 和最新机器报告交叉核对。不得把 smoke、结构通过、机器预检或自动评分写成真人通过或正式 benchmark 结论。

## 历史实验

开发筛选的 round-by-round JSON/Markdown 与 candidate attempts 保留在 [`reports/experiments/archive/development-filtering/`](../../reports/experiments/archive/development-filtering/)。它们用于复现失败、替换和阈值演化，不应作为论文主结果；主文优先引用当前结论级报告。
