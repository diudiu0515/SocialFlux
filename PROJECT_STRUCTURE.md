# SocialFlux 项目结构

当前仓库只保留 scenario 驱动的 pipeline、固定 prompt、任务产物和只读可视化网站。后续新增场景时，主要新增 `configs/scenarios/scenario_*.json` 及其测试/配套配置。

```text
emotree/
├── configs/scenarios/              # 唯一场景输入；每个 scenario_*.json 配对同名 .md
├── environment/                   # action normalization、状态、记忆、更新、响应、终止、表达层
├── policies/                      # ControlledPolicy 与 ModelPolicy
├── providers/                     # OpenAI-compatible、Anthropic、Gemini、local/vLLM
├── rollout/                       # rollout runner、日志、manifest、counterfactual
├── offline/                       # 从私有 rollout 提取 T1/T2/T3 公开候选
├── tasks/                         # T1/T2/T3 任务定义、模型输出和人工标注 schema
├── evaluation/                    # 五项验收、环境 validity、泄漏审计、指标
├── annotation/                    # 人工标注 overlay、聚合和导出
├── prompts/                       # 所有固定 prompt、版本和 SHA-256 manifest
├── schemas/                       # scenario/trajectory schema 校验
├── scripts/                      # run_pipeline、run_acceptance 等唯一构建入口
├── web/                          # Scenario Observatory 只读可视化网站
├── interactive_benchmark/         # 可选 legacy world converter/schema 工具
├── shared/                        # scenario 创作规范和状态本体参考
├── talkinghead_generation.md      # state-triggered Talking Head 设计
├── self_check.md                  # 永久 TODO/验收清单；每次任务更新，禁止删除既有项
├── build/                         # 可再生构建；pipeline_v1 私有轨迹只本地生成
├── ARCHITECTURE.md
├── PIPELINE.md
└── PROJECT_PROGRESS.md
```

## Scenario 是唯一扩展点

新增场景：

1. 在 `configs/scenarios/` 新增 `scenario_*.json`，遵守 `schemas/scenario.schema.json`；
2. 配置 persona、initial state/dynamics、action effects、response、observable expression 和 video triggers；
3. 运行 `python scripts/scenario_docs.py configs/scenarios/scenario_*.json` 生成同名 Markdown；
4. 生成器会自动重建 manifest；运行 `python scripts/scenario_docs.py --check` 检查全部 JSON/Markdown/source hash/manifest；
5. 运行 `python -m scripts.run_pipeline --scenarios configs/scenarios --output build/pipeline_v1`；
6. 运行 acceptance、核心测试与 web/tests；
7. 打开 `python web/server.py`，网站会自动发现新场景并展示配对文档。

## 数据边界

`configs/scenarios` 是作者侧定义；`build/pipeline_v1` 的 master rollout 含 private state 和 appraisal，默认不提交；`offline` 候选必须通过 `evaluation/leakage.py`。网站是研究/开发可视化层，可展示完整 scenario 与私有 rollout，但不对外模拟 participant 视图。
