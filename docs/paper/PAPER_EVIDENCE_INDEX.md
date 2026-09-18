# SocialFlux Paper Evidence Index

| 论文部分 | 权威说明 | 当前实现/证据 | 边界 |
|---|---|---|---|
| Construct | [Design Contract](../../DESIGN_CONTRACT.md) | [Architecture](../architecture/ARCHITECTURE.md) | 正式 Gate 尚未完成 |
| Scenario construction | [Pipeline](../architecture/PIPELINE.md) | `configs/scale300_v1/CLAUDE_AUTHORING.md`、scenario schema | Claude 直建；Gate 1 必须真人完成 |
| Runtime | [Pipeline](../architecture/PIPELINE.md) | `pipeline/`、`environment/`、`rollout/` | Appraisal → Python update → Response |
| Gate 2 | [Gate protocol](../protocols/gate.md) | `2026-09-09_gate2_environment_interventions.md` | 旧 pilot 只支撑方法，新 Scale300 证据待生成 |
| T1/T2/T3 | [Task specs](../../tasks/README.md) | `2026-09-07_task_selection_iteration.md`、`2026-09-16_t2_expression_history_dev.md` | 旧结果不是正式数据 |
| Model routing | [API record](../../api.md) | `2026-09-17_autodl_board_model_selection.md` | 当前统一为 Fable baseline |
| Human review UI | [Web README](../../web/README.md) | `web/server.py`、`web/static/` | 浏览器草稿不是签名 |
| Talking Head | [Architecture](../architecture/ARCHITECTURE.md) | `media/talking_head/manifest.json` | 资产保留，人工多模态审核待完成 |

当前可引用的确定事实只有：catalog 目标为 300 个 scenario、每场景 3 个 rollout
seed、最多 20 轮、Gate 3 每场景选择 1 条 canonical trajectory，以及所有正式
Gate 仍为 pending。旧开发结果不得写成当前 Scale300 或 Fable 正式结果。
