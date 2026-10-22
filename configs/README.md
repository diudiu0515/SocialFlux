# SocialFlux 配置索引

配置按用途区分；文件存在、版本号较大或名字含 `candidate`，都不表示它已成为默认配置。实际生效值由入口参数、所选配置和该次 run manifest 共同决定。

## 当前开发入口

| 用途 | 配置或入口 | 说明 |
|---|---|---|
| 当前场景题库 v2 | [`offline/scenario_v2.py`](../offline/scenario_v2.py)、[发布 manifest](../tasks/examples/offline_scenarios_v2/manifest.json) | 50 场景，T1/T2/T3 各 100 题；生成参数由批次产物保存 |
| 历史 Offline 60 题 | [`offline_choice_dev60.json`](offline_choice_dev60.json) | 固定 5 个场景；保留来源、路由和延迟窗口 |
| 历史 GPT50 T1/T3 扩展 | [`offline_gpt50_t1_t3.json`](offline_gpt50_t1_t3.json) | 旧 50 场景、目标 400 题配置；不是当前 v2 题库计数 |
| T4 41 场景批次 | [`t4_multimodal_experiment.reliable41_20261021.json`](gpt50_experiment/t4_multimodal_experiment.reliable41_20261021.json) | GPT、Claude × 41 场景 × text/video，共 164 个槽位；使用冻结运行目录 |
| GPT50 开发与当前轨迹 | [`gpt50_experiment/README.md`](gpt50_experiment/README.md)、[批次手册](../docs/operations/ACTIVE_BATCH_PIPELINE.md) | 当前来源由批次 manifest 绑定，不将所有 rollout.* 候选合并 |
| Claude150 批次 | [`claude150_v1/README.md`](claude150_v1/README.md) | 独立的场景、路由、产物与恢复记录 |
| 网站进程 | [`web.supervisord.conf`](web.supervisord.conf) | 监听 127.0.0.1:8000，服务环境与日志在 build/web-service |
| 多模态资产 | [`multimodal_delivery.json`](multimodal_delivery.json)、[`online_multimodal_assets.json`](online_multimodal_assets.json) | 素材按批次与 SHA 绑定，具体覆盖以 manifest 为准 |

Offline 当前显式引用 `gpt50_experiment/rollout.state_observed_evidence_v6_candidate.json` 和 `gpt50_experiment/model_routes.hybrid.v3_2.json`。这些引用用于复现既有数据，本轮目录整理没有切换模型、状态语义或采样参数。

## 通用正式默认值

[`pipeline/constants.py`](../pipeline/constants.py) 仍将以下文件作为通用正式命令的默认值；这是保留的 Fable 基线，并不代表所有开发实验使用同一模型。

| 文件 | 职责 |
|---|---|
| [`model_routes.frontier_api.json`](model_routes.frontier_api.json) | 默认模型角色路由 |
| [`formal_rollout_pool.json`](formal_rollout_pool.json) | 每个已批准场景一条自然 rollout |
| [`review_models.json`](review_models.json) | 轨迹与任务的模型审核 |
| [`t4_evaluation.json`](t4_evaluation.json) | 通用 T4 环境、策略与评分 |
| [`t2_source_adaptation_v2.json`](t2_source_adaptation_v2.json) | 旧版 T2 来源适配和受控回放 |

模型通过 `providers/model_routes.py` 和 `providers/factory.py` 注入。Anthropic、OpenAI-compatible 与 Responses 传输各有 owner；领域代码不应绕过 provider 直接发 HTTP。凭据从环境或私有文件读取，不写入报告、题目或清理备份。

## 历史配置的保留

2026-10-21 核对：共 126 个 JSON 配置，规范化 JSON 内容没有完全相同的副本；
其中 56 个引用已退役 prompt。此次重构没有删除配置或替换 prompt ID。
这不表示其余 70 个均可直接运行，具体入口仍需通过各自来源、Gate 和运行前检查。
逐文件格式、SHA 和退役引用见[配置审计清单](../build/code_cleanup_20261021/config_inventory.json)，
代码退役与保留依据见[代码审计](../docs/architecture/CODE_AUDIT.md)。

2026-10-10 已按确认链路撤下 39 份中间 prompt。56 份历史配置中的旧 ID 继续
作为来源记录保留，引用已撤下模板时会明确报错；不能直接用于新调用或把 ID
批量改成新版。当前支持入口与恢复方式见 [Prompt 目录](../docs/prompts/RUNTIME_PROMPT_CATALOG.md)
和 [审计记录](../docs/prompts/PROMPT_AUDIT.md)。

`rollout.state_*`、`model_routes.*` 和旧 benchmark 配置中有不少仍被脚本、批次 manifest 或实验报告引用。它们支撑失败对照、断点恢复和复现，不能仅凭文件名删除。`scripts/` 中带旧批次名称的入口也可能仍被活跃脚本导入，应先检查调用链。

新配置需声明用途、输入根与输出根；替换默认路径时同步更新调用方、测试和文档。目录整理不重写已冻结 manifest 的哈希，也不把旧结果升级为当前结果。
