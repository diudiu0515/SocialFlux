# API model integrated probe（2026-09-17）

## 结论

在 IA003 与 IA019 上完成六条冻结条件的端到端对照。批内 prompt、Qwen3.8-Max
Structured Appraisal、确定性 calibration/state/dynamics 更新、自然结束协议和质量标准均未
改变，只替换 Policy 与 Response 模型。

生成层面一条进入 10–20 轮主候选、三条自然短轨迹、两条结构失败；Codex 完整阅读后，
只有两条 IA003 自然短轨迹语义可接受，主窗口内合格数为 0。该复核是模型语义复核，
不是人工验收。

| 场景与组合 | 轮数／结束 | 请求数 | 耗时 | 机器预检 | Codex 语义复核 |
| --- | --- | ---: | ---: | --- | --- |
| IA003 · MiniMax policy · Qwen response | 7，自然结束 | 23 | 176.9s | 短轨迹，结构通过 | 可接受短轨迹；不进入主候选 |
| IA003 · DeepSeek policy · Qwen response | 7，自然结束 | 29 | 337.3s | 短轨迹，结构通过 | 拒绝：t3 否认 t1–t2 已形成的约定；t4 把未到账三百从余额扣除 |
| IA003 · DeepSeek policy · DeepSeek response | 6，自然结束 | 21 | 622.8s | 短轨迹，结构通过 | 可接受短轨迹；承诺、到账和关系边界清楚 |
| IA019 · MiniMax policy · Qwen response | 4，生成失败 | 24 | 199.5s | Response 四次结构失败 | 拒绝：双方补造授权书、律师、交割和投资人事实 |
| IA019 · DeepSeek policy · Qwen response | 4，生成失败 | 20 | 228.0s | Response 四次结构失败 | 拒绝：t4 补造投资人改条款、法务扣版和助理发送 |
| IA019 · DeepSeek policy · DeepSeek response | 15，自然结束 | 52 | 1619.7s | 主候选，机器通过 | 拒绝：t13 无事件依据地宣布董事会票决结果；t10–t11 轻度空转 |

本批共 169 次实际请求，墙钟时间约 33 分 45 秒；并行运行，因此单条耗时之和不等于
批次墙钟时间。每轮仍保持两个独立环境阶段，额外 Policy 请求不属于环境阶段。

## 模型选择含义

- DeepSeek Response 在 IA003 产生了本批最干净的短轨迹，并在 IA019 完成 15 轮，结构
  稳定性优于本批 Qwen Response；因此当前 Response 路由暂保留 DeepSeek。
- 该选择不是“问题已解决”：15 轮 IA019 仍把未决提案和时间经过升级成票决结果，且耗时
  远高于 Qwen。正式扩量前必须把这类样本作为语义拒绝，而不能依赖机器结构通过。
- Policy 侧没有单一模型跨场景胜出。MiniMax 在 IA003 可用，但在 IA019 第一轮就虚构了
  具体授权书；DeepSeek 在 IA019 更克制，因此当前 Policy 路由仍保留 DeepSeek。
- Qwen3.8-Max Appraisal 的两阶段接线正常；六条轨迹都记录了逐轮 state/dynamics 更新与
  ledger。问题主要出现在自由文本行为和 Response 对外部结果的断言，而不是三阶段被合并。

## Judge 对照

MiniMax-M3 独立 Judge 对六条均给出无 hard reject，并给 15 轮 IA019 的连贯性与历史依赖
5 分。它没有识别 t13 的无依据票决结果，也没有识别两条四轮 IA019 的制度事实补造。
因此 MiniMax 只能保留为快速空转预检，不能单独承担事实边界 Gate。

原始 Judge 结果位于
`build/api_model_integrated_probe_v1/minimax_semantic_judgments.json`；哈希绑定的 Codex
复核位于 `build/api_model_integrated_probe_v1/codex_semantic_review.json`。

## 决策

当前 frontier 路由不回滚：Policy/Response/T2 构造与答案继续使用 DeepSeek-V4-Pro-0813，
Appraisal 继续使用 Qwen3.8-Max，MiniMax-M3 仅作机器语义预检。六条结果不支持直接启动
大规模 rollout：IA003 已证明能自然生成高质量短轨迹；IA019 仍需修正场景的外部结果来源
或替换该场景，不能靠换模型或增加重试解决。
