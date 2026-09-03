# SocialFlux Framework Definition — Revision-Integrated Canonical Version

> 文件名为历史兼容入口；本文内容已按 2026-09-02 的 `revision.md` 与 `prompt_check.md` 重写，是当前 pipeline 的权威定义。若旧文档冲突，以本文和 schema/code 为准。

## 1. 研究目标

SocialFlux 评估模型能否在长期社会互动中追踪人物的主观状态、理解历史依赖、预测自由行动的即时/延迟影响，并在同一动态环境中在线适应。研究对象是 interaction-conditioned latent social state，不是固定剧情分支或“选最佳话术”游戏。

## 2. 核心对象

每个 scenario 固定：

- 稳定 persona、社会背景、关系与权力结构；
- environment agent 的 explicit goal 与 author-only hidden intention；
- evaluated-agent role 与可见目标；
- 候选并经真人 freeze 的初始 latent state S0；
- 独立 interaction dynamics D0；
- 终止条件、时长、可观察表达与稀疏 media trigger；
- 来源、quality gate、normalization 和初始化 review provenance。

Persona 不是 mutable state。S_t/D_t 使用 0–10 数值，但模型 state updater 只输出七级 semantic delta；确定性映射负责数值更新和边界裁剪。

## 3. 禁止的正常生成机制

正常 offline/T4 轨迹不得使用：

- repair、neutral、escalation 或类似固定 policy classes；
- action ID、keyword classifier、scenario-authored action effects；
- scripted action trajectory；
- response templates；
- 为得到“预期方向”而重复同一策略的多轮 rollout。

自由模型每轮可输出任何自然语言行动。多样性来自不同模型、temperature、seed 与自然形成的历史。

## 4. Hybrid Scenario Sources

来源至少包含 narrative-derived 与 synthetic-script 两类。

Narrative-derived 只提取抽象社会结构：关系、权力、冲突目标、信息不对称、关键历史与选择空间。未经许可不得发布原作台词、人物、场景表面细节。

Synthetic-script 的模型先写连贯社会叙事，不同时考虑 JSON、S0/D0、阈值、T1/T2/T3 或答案。两类来源执行相同流程：

```text
source material
→ 11-item source quality report
→ real reviewer approval
→ canonical blueprint
→ candidate S0/D0 + trigger specification
→ real reviewer freeze
→ canonical scenario
```

质量项为 social plausibility、real tradeoff、longitudinal necessity、nontrivial strategy space、motivation coherence、information asymmetry、T1/T2/T3 suitability、T4 adaptation opportunity、no universal script。LLM 报告始终是 pending human review，不能自我批准。

## 5. Canonical Stateful Environment

offline rollout 与 T4 必须通过同一个 `StatefulEnvironment` 和 `ModelEnvironmentFactory`。

每轮：

```text
public O_t
→ free-form action A_t
→ observable-history memory retrieval
→ private persona/history-conditioned appraisal
→ semantic ΔS_t and ΔD_t
→ deterministic numeric update
→ response conditioned on S_{t+1}, D_{t+1}
→ sparse expression/media trigger
→ private log + next public observation
```

Appraisal 与 state update 是两个不同 prompt/call。Response 只能在更新后生成。Memory 只检索 observable history，不能把 hidden state 当事实。Environment 可见 persona、hidden intention 和 private state；evaluated model 永远不可见这些私有字段。

## 6. Prompt Contracts

所有固定 prompt 位于 `prompts/` 并登记 SHA-256。基本写法是 task-first、constraints/quality checks 居中、schema-last。职责边界：

- scenario script：只负责社会叙事；
- source quality：只做归一化前质量判断；
- normalization：只产 blueprint，不产 S0/D0；
- initialization：只产候选 S0/D0、threshold 与 expression；
- appraisal：只解释当前 action；
- state update：只产 semantic delta；
- response：读取 updated state 后只产可观察回应；
- memory：只读取可观察历史；
- expression/talking head：只把已选中的安全 observable specification 变成媒体；
- T1/T2/T3/T4：各自只接收允许信息；
- human annotation 与 LLM judge 明确分离。

## 7. Natural Rollout Pool

每个已批准 scenario 从相同 frozen S0/D0 启动多个 model/sampling 配置。每条 trajectory 必须记录 policy model、sampling、seed、prompt ID、environment model/config（去密钥）、完整 private transitions 与 observable projections。异常、过早终止和格式错误可过滤，但不得按“是否符合预设策略方向”筛选。

## 8. T1

T1 从自然 trajectory checkpoint 提取完整可观察历史与当前 observation，让被测模型估计目标人物当前状态及变化。Ground truth 由独立人类标注；simulator state 仅可作为诊断参考，不自动成为答案。不得预先在 scenario 中编写 T1 checkpoint。

## 9. T2

T2 从自然轨迹池检索同 scenario、同深度且历史与 private state 已分化的 A/B。随后构造一个对两段历史都自然的完全相同 O*。实例必须保留 O* 一致性证明、来源 trajectory IDs 和 compatibility pending 状态。若 O* 自身泄漏历史差异或对任一历史不自然，实例删除。

## 10. T3

T3 从真实自然轨迹 checkpoint 提供 2–4 个自由文本候选行动。构建端 restore 同一 private snapshot，逐个执行一次局部 action intervention，再由与源轨迹一致的自由模型策略继续 5 轮，必要时至 10 轮。所有 option 共享起点与 continuation protocol。主任务输入不含 oracle state；oracle 只能用于单独 ablation。

## 11. T4

T4 让被测模型直接进入 canonical environment，自由输出行动。评分维度包括 Goal Achievement、State Adaptation、Risk Management、Recovery 与 Relationship Outcome。低冲突不是自动高分；应依据 scenario 的真实目标和 trade-off。LLM judge 需要与人类评分校准。

## 12. Multimodal / Talking Head

普通轮次为 text。私有 state/dynamics 满足 threshold、crossing 或 state-change 条件时，trigger engine 选择一个 observable expression event。公开端只能看到自然表情、视线、停顿、语速、语调、姿态与安全 media asset metadata，不能看到 trigger ID、阈值、state 名称/数值、hidden intention 或 appraisal。视频建议 3–8 秒并保持人物和时间连续；真实资产仍需人工检查。

## 13. Environment Validation

固定九项：

1. State-Update Human Agreement：抽 30–50 transitions，三人判断方向与合理性。
2. Persona Sensitivity：同 H/S/A，只改变 persona。
3. Paraphrase Robustness：人审语义等价 action pair。
4. History Intervention：同 checkpoint 删除一个因果相关历史事件。
5. Local Action Intervention：同真实 checkpoint 比较自由候选行动。
6. Neutral-State Stability：人审 no-op/neutral 行动不应导致无故漂移。
7. Response-State Consistency：固定公开 context，局部改变 hidden state。
8. Full-Trajectory Plausibility：15–20 条 5–10+ 轮自然轨迹，三人评审。
9. Seed Robustness：同 model/config 不同 seed 的定性方向与方差。

报告状态只能是 pending、evidence_ready、provisionally_ready 或在真实证据齐全后的 passed。旧的三种固定 policy sensitivity 不属于本 gate。

## 14. Coverage 与发布

10 个 scenario 应覆盖不同关系、权力、目标冲突、信息不对称、state 子集、trigger 类型与两类 source。Coverage matrix 不能用自动推断冒充真人结论。

正式发布前必须完成：scenario source/quality/S0 freeze、自然 rollout pool、九项验收、人类 ground truth、泄漏与 contamination audit、T4 judge validation、multimodal validity。代码能运行不等于 research acceptance。

## 15. 文件与可复现性

Canonical scenario 位于 `configs/scenarios/scenario_NNN/scenario_NNN.json`；同名 Markdown 是确定性可读投影。Rollout JSON、manifest 和 `dialogues.md` 与 scenario 同目录。跨场景构建位于 `build/pipeline_v2`，验收位于 `build/acceptance_v2`。所有本地产物可再生且默认 gitignored；secrets 只来自环境变量。
