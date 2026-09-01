# SocialFlux 项目进度

更新时间：2026-09-01

## 当前状态

项目已收敛为 scenario 驱动的可复现 pipeline 和 Scenario Observatory 网站，后续主要扩展 scenario 及其配套产物。

| 模块 | 状态 | 当前结果 |
|---|---|---|
| 框架定义与状态本体 | 已完成 | 0–10 连续状态、离散语义 delta、状态边界与终止契约已实现 |
| Stateful Environment | 已完成 | 初始化、记忆、appraisal/state update、响应、终止和轨迹日志已连通 |
| Provider / Policy 接口 | 已完成 | OpenAI-compatible、Anthropic、Gemini、local/vLLM 适配器已统一 |
| Controlled validation rollout | 已完成 | 10 个场景、每场景 3 条策略 rollout |
| Offline benchmark 构建 | 已完成 | T1=50、T2=30、T3=40，共 120 条候选实例 |
| Counterfactual 验证 | 已完成 | T3 私有分支和即时/延迟 horizon 已生成 |
| Interactive benchmark | 旧 world 已清理 | IA001/IA002 创作源文件按当前项目整理要求移除；转换器、schema 和标注工具保留 |
| Scenario 配对文档 | 已完成 | 10/10 JSON 均有同名自然语言 Markdown；source hash、自动 manifest、pipeline/acceptance gate 和网站展示已接通 |
| Prompt catalog | 已完成 | 13 个版本化 prompt，manifest SHA-256 校验，运行时代码统一 loader |
| 信息隔离与泄漏审计 | 已完成 | participant 只暴露 observable view；候选实例不暴露 private effects |
| Scenario Observatory | 已完成 | 只读展示当前 scenario、策略轨迹、状态转移和 Talking Head trigger；不维护第二套状态机 |
| GitHub 发布 | 本地已提交 | commit `0f76297` 已完成；推送需先将项目 deploy key 添加到仓库 |
| Pipeline acceptance | 工程验收通过 | State 210/210、Persona 通过、Paraphrase 30/30、Policy 10/10；Trajectory 10/10 结构+专家预审通过，正式人工签字待补 |
| 正式 ground truth | 待人工标注 | 需要独立标注与 adjudication，代码不会伪造正式标签 |
| Talking-head 视频 | 结构层已完成 | 10 个 scenario 已注册 state-triggered expression/media 规则；真实视频资产仍为 spec-only |
| RL policy 训练 | 待后续 | 当前提供 policy/provider 接口，不包含训练过程 |

## 已验证指标

- 核心测试：21 项通过
- Web 测试：3 项通过
- Interactive benchmark 工具测试：12 项通过，旧 IA001/IA002 world 测试按整理要求跳过
- Python compileall：通过
- Pipeline manifest：10 个 scenario，120 条候选实例
- Interactive benchmark manifest：48 条实例
- Talking Head trigger tests：2 项通过
- Acceptance gate：automated engineering checks passed；formal human trajectory review pending

## 下一步优先级

1. 为 5–10+ 轮轨迹组织正式人工 plausibility review，并记录 reviewer、版本和 adjudication。
2. 接入真实模型 provider，记录 provider/model/prompt version/seed 等可复现实验元数据。
3. 根据 talkinghead_generation.md 接入真实 Talking Head 生成与 media manifest，并完成 trigger validity、expression-state consistency、temporal continuity 和 non-leakage 人工验收。
4. 如需恢复交互 benchmark，再新增 Story World，并沿用同一 schema、prompt 和采样约束。
5. 再考虑 RL policy，不在正式标注前改变任务定义。

## 维护规则

- 每完成一项可验证工作，更新本文件的更新时间、状态表和测试结果。
- 新增或修改 scenario JSON 后必须运行 `python scripts/scenario_docs.py`；缺失或过期的同名 Markdown 会阻断 pipeline 和 acceptance。
- 修改任务语义先更新 tasks/，修改固定 prompt 先新增 prompts/ 版本并更新 prompts/manifest.json。
- 任何正式数据变更都要重新运行核心 tests、web/tests 和对应构建脚本；interactive_benchmark/tests 仅在保留旧 world 源文件时运行。
- build/ 是可再生产物；interactive benchmark 可提交，含 private master trajectory 的 build/pipeline_v1 只在本地生成并被 .gitignore 排除；web/ 只读读取 configs/scenarios 和 build/pipeline_v1；不生成独立 session。
