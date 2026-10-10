# SocialFlux

SocialFlux 使用同一套社会状态环境生成 rollout、构建 T1–T3 离线题目，并执行 T4 在线评测。四类 state 为 Emotion、Behavioral Disposition、Relationship、Interaction Risk；内部风险路径沿用 `consequence_risk`。

当前开发入口包括 GPT50 场景与轨迹、多模态资产，以及基于其中 5 个场景的 60 道 T1–T3 选择题。开发题已有 56 道完成所需回放，4 道 T3 待补；全部答案仍待人工审核。数量与状态以对应批次 manifest 为准，详见 [项目进度](PROJECT_PROGRESS.md) 和 [开发题报告](reports/experiments/2026-10-10_offline_t1_t3_dev60.md)。

另已接入固定 50 场景的 [T1/T3 扩展批次](docs/operations/OFFLINE_GPT50_T1_T3.md)，
T2 暂停新增。目标为每场景 4 道 T1、4 道 T3，共 400 题；
已获授权继续使用现有 provider，实际产出和缺项见批次 manifest。网页新入口为
`/offline-review?bank=gpt50-t1-t3`，旧 60 题继续独立保留。

## 从哪里开始

| 目标 | 入口 |
|---|---|
| 理解模块职责、依赖与数据流 | [项目架构](docs/architecture/ARCHITECTURE.md) |
| 理解 Gate 与运行顺序 | [Pipeline](docs/architecture/PIPELINE.md) |
| 查找当前批次、配置和恢复方式 | [活跃批次手册](docs/operations/ACTIVE_BATCH_PIPELINE.md)、[配置索引](configs/README.md) |
| 开发 T1–T3 题目与评分 | [选择题协议](docs/protocols/OFFLINE_T1_T3_CHOICE_V1.md)、[任务说明](tasks/README.md) |
| 查看场景、对话、视频或标注题目 | [网站说明](web/README.md) |
| 查阅设计约束与历史实验 | [DESIGN_CONTRACT](DESIGN_CONTRACT.md)、[文档索引](docs/README.md)、[报告索引](reports/README.md) |

## 当前可用入口

公共命令统一从 `python -m pipeline` 进入；`scripts/` 保存具体编排与专项实验入口。查看帮助不会发起模型调用：

```bash
python -m pipeline --help
python -m pipeline offline-build --help
python -m pipeline offline-eval --help
```

对已有开发题进行零模型调用检查：

```bash
python -m pipeline offline-eval --items data/offline_t1_t3_dev60/replay_ready.items.jsonl --output build/offline-check --check-only
```

新协议作答只需 `{"answer":"B"}`。`tasks --protocol choice` 与 `offline-build` 走同一构建路径；不带协议参数的 `tasks` 保留旧概率题流程。重新生成、回放或试答可能调用 provider，参数见协议。CLI 的通用正式默认配置仍为 Fable；当前 GPT/offline 批次显式选择自己的配置，不要把默认值视为当前实验的模型配置。

网站日常由 [Supervisor 配置](configs/web.supervisord.conf) 管理。临时启动前先确认没有实例占用 8000 端口：

```bash
python -m web.server --host 127.0.0.1 --port 8000
```

| 页面 | 用途 |
|---|---|
| `/gpt50` | 场景与 Gate 人工审核 |
| `/gpt50-live` | 当前轨迹、逐轮 state、Gate 结果与视频 |
| `/offline-review` | T1–T3 题目标注、参考材料与草稿导入导出 |
| `/multimodal` | 多模态素材审核 |
| `/state-annotation` | 固定历史样本的 state 标注 |

远程服务器沿用 SSH 隧道：`ssh -p 22 -L 8000:127.0.0.1:8000 root@SERVER_IP`，然后打开 `http://127.0.0.1:8000/offline-review`。标注草稿保存在当前浏览器，换浏览器或清缓存前应导出 JSON。

## 模块与产物

| 目录 | 职责 |
|---|---|
| `pipeline/` | 公开 CLI、配置编排、运行时装配与翻译 |
| `environment/`、`policies/`、`providers/` | 环境状态推进、行动策略、模型调用适配 |
| `rollout/` | 自然轨迹与从真实 checkpoint 开始的反事实分支 |
| `offline/`、`tasks/`、`evaluation/` | 出题、输入/回答协议、评分与质量门 |
| `scenario_design/`、`annotation/` | 场景修订与人工审核合同 |
| `configs/`、`prompts/`、`schemas/`、`shared/` | 配置、版本化提示词、结构与语义约定 |
| `web/` | 只读材料接口与浏览器标注工作台 |
| `scripts/`、`tests/` | 批次/实验命令和验证 |
| `data/` | 场景、轨迹、题库、视频及其 manifest；本地数据，不进入 Git |
| `build/` | 实验产物、验证结果和网站服务环境；并非都可重新生成的缓存 |
| `reports/`、`docs/`、`reviews/` | 结论与证据索引、说明、审核模板 |
| `archives/` | 不作为活跃入口的本地恢复副本 |

已按[确认的 prompt 链](docs/prompts/RUNTIME_PROMPT_CATALOG.md)删除 39 份中间实验模板，并从注册表撤下。历史配置与结果保留来源信息；旧模板复现需使用匹配的归档，不能直接启动已撤下版本。`prompts/manifest.json.orig` 仅保留为冻结记录输入。`.secrets/`、服务环境和浏览器草稿不属于普通清理对象。范围与恢复说明见[架构文档](docs/architecture/ARCHITECTURE.md#维护与清理)。

## 验证与正式发布

```bash
python scripts/check_markdown_links.py
python -m unittest discover -s web/tests -v
python -m unittest tests.test_offline_choice tests.test_t2_source_adaptation -v
```

全量回归另用 `python -m unittest discover -s tests -v`；部分历史集成测试需要各自冻结的数据资产，不应为通过测试而补造旧场景。

正式流程为 Gate 1 → 一场景一条自然 rollout → Gate 2/3 → T1–T3/T4 → Gate 4。开发产物、模型审核和浏览器草稿均不代表正式 human GT。正式命令与证据要求见 [Formal Rollout Runbook](docs/operations/FORMAL_ROLLOUT_RUNBOOK.md)。不可变约束及提交规则见 [DESIGN_CONTRACT](DESIGN_CONTRACT.md)。
