# SocialFlux Paper Evidence Index

| 论文部分 | 权威说明 | 当前实现/证据 | 边界 |
|---|---|---|---|
| Construct | [Design Contract](../../DESIGN_CONTRACT.md) | [Architecture](../architecture/ARCHITECTURE.md) | 正式 Gate 尚未完成 |
| Scenario construction | [Pipeline](../architecture/PIPELINE.md) | scenario schema、版本化 authoring contract | Gate 1 必须真人完成 |
| Runtime | [Pipeline](../architecture/PIPELINE.md) | `pipeline/`、`environment/`、`rollout/` | Appraisal → Python update → Response |
| Gate 2 | [Gate protocol](../protocols/gate.md) | environment evidence contract | 新批次证据待生成 |
| T1/T2/T3/T4 | [Task specs](../../tasks/README.md) | task builders 与 online runtime | 小规模闭环尚待验证 |
| Model routing | [API record](../../api.md) | 版本化 route table | 模型是 provenance，不是选择配额 |
| Human review UI | [Web README](../../web/README.md) | `web/server.py`、`web/static/` | 浏览器草稿不是签名 |
| Talking Head | [Architecture](../architecture/ARCHITECTURE.md) | `media/talking_head/manifest.json` | 资产保留，多模态审核待完成 |

当前可引用的事实是：每场景只生成一条 rollout，最多 20 轮；Gate 3 对唯一轨迹作准入或淘汰；所有正式人工 Gate 和正式 GT 仍为 pending。旧 Qwen/Scale300 结果已归档，不得写成当前结果。GPT 小规模批次只用于端到端设计审计；其结果通过人工复核后，才决定 Claude 主批次的扩量。
