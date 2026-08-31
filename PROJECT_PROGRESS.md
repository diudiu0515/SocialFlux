# SocialFlux 项目进度

更新时间：2026-08-31

## 当前状态

项目已完成第一版可复现 pipeline 和 on-policy demo，具备上传 GitHub、继续扩展和人工标注的基础。

| 模块 | 状态 | 当前结果 |
|---|---|---|
| 框架定义与状态本体 | 已完成 | 0–10 连续状态、离散语义 delta、状态边界与终止契约已实现 |
| Stateful Environment | 已完成 | 初始化、记忆、appraisal/state update、响应、终止和轨迹日志已连通 |
| Provider / Policy 接口 | 已完成 | OpenAI-compatible、Anthropic、Gemini、local/vLLM 适配器已统一 |
| Controlled validation rollout | 已完成 | 10 个场景、每场景 3 条策略 rollout |
| Offline benchmark 构建 | 已完成 | T1=50、T2=30、T3=40，共 120 条候选实例 |
| Counterfactual 验证 | 已完成 | T3 私有分支和即时/延迟 horizon 已生成 |
| Interactive benchmark | 已完成 | IA001/IA002 共 48 条 text/text_video 实例 |
| Prompt catalog | 已完成 | 12 个版本化 prompt，manifest SHA-256 校验，运行时代码统一 loader |
| 信息隔离与泄漏审计 | 已完成 | participant 只暴露 observable view；候选实例不暴露 private effects |
| Demo | 已完成 | Participant / Researcher / Replay 三端和 20-turn 上限 |
| 正式 ground truth | 待人工标注 | 需要独立标注与 adjudication，代码不会伪造正式标签 |
| Talking-head 视频 | 待后续 | 当前保留视频控制结构和 spec-only 资产 |
| RL policy 训练 | 待后续 | 当前提供 policy/provider 接口，不包含训练过程 |

## 已验证指标

- 核心测试：12 项通过
- Demo 测试：9 项通过
- Interactive benchmark 测试：20 项通过
- Python compileall：通过
- Pipeline manifest：10 个 scenario，120 条候选实例
- Interactive benchmark manifest：48 条实例

## 下一步优先级

1. 为 IA001/IA002 完成人工标注、双人一致性检查和 adjudication。
2. 增加更多独立 Story World，并沿用同一 schema、prompt 和采样约束。
3. 接入真实模型 provider，记录 provider/model/prompt version/seed 等可复现实验元数据。
4. 根据环境 validity scorecard 进行状态转移和反事实一致性审计。
5. 再考虑 Talking-head 资产和 RL policy，不在正式标注前改变任务定义。

## 维护规则

- 每完成一项可验证工作，更新本文件的更新时间、状态表和测试结果。
- 修改任务语义先更新 tasks/，修改固定 prompt 先新增 prompts/ 版本并更新 prompts/manifest.json。
- 任何正式数据变更都要重新运行三套测试和对应构建脚本。
- build/ 是可再生产物；demo/data/trajectories/ 只保存本地运行时 session，不提交真实 session。
