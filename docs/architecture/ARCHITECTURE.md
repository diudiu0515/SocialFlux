# SocialFlux Architecture

## 总体数据流

```text
Versioned scenario authoring batch (GPT design audit or Claude primary)
        ↓
N complete canonical scenario JSON candidates
        ↓
schema/catalog validation (no model approval)
        ↓
Gate 1 source/quality review + S0/D0 real reviewer freeze
        ↓
one canonical StatefulEnvironment
        ├── one natural baseline-model rollout per scenario
        ├── T1 natural checkpoints
        ├── T2 naturally divergent histories + exact shared O*
        ├── T3 local branches from one real checkpoint
        └── T4 online free interaction
        ↓
nine-criterion acceptance + human annotation
```

## 唯一环境

`ModelEnvironmentFactory` 同时服务离线 rollout 与 T4，每轮严格按以下顺序执行：

1. 向 evaluated model 暴露 observable observation。
2. 接收任意自由文本 action。
3. 从可观察历史检索 memory；完整原始历史始终是权威记录。
4. `ModelAppraiser` 私下结合 persona、目标、hidden intention、S_t/D_t 与历史解释 action。
5. 配置指定的 appraisal prompt 输出 event features 与稀疏、带证据的 variable impacts；DeterministicStateCalibrator 统一完成 inertia、persona sensitivity、magnitude、稀疏性和 0–10 边界更新，期间不调用 LLM；随后配置指定的 response prompt 作为独立 LLM call 读取更新后状态与 ledger 生成回应。
6. `ModelResponseGenerator` 在更新后的状态上生成自然回应。
7. trigger engine 检测 threshold/crossing/state-change，并只公开安全 expression/media。
8. logger 保存 private master trajectory；公开 task builder 必须通过 leakage audit。

环境没有 action interpreter、action effects 表、response template 或固定策略 runner。

### 运行时模块边界

- environment/env.py 只编排单轮生命周期：准备输入 → Structured Appraisal → 确定性更新 → Response Generation → 提交状态 → 终止判断 → 写日志。step() 不承载 prompt 或语义规则。
- environment/dialogue_support.py 保存 policy 与 environment 共用、且与说话人无关的生成配置、horizon 提示和 prompt 压缩逻辑。
- environment/ledger_events.py 只校验带原文证据的语义事件；environment/interaction_ledger.py 负责把已校验事件归约为可持续记忆。两者均不调用模型。
- environment/response_generator.py 负责 response prompt 和 provider 调用；environment/response_validation.py 独立保存输出 schema、事实边界和动作归属检查。
- policies/model_policy.py 负责 agent prompt 和 provider 调用；policies/action_validation.py 独立保存 agent action 的验证契约。
- tasks/T2/runtime.py 是 T2 文件 I/O、环境创建、公开历史投影和状态比较的唯一 owner；`scripts/t2_common.py` 仅保留历史导入兼容，新代码不得从其增加逻辑。
- batch validator 只校验模型直接创建的 canonical JSON，并刷新 Markdown、manifest 与 coverage；它不调用模型、不批准 Gate 1，也不修改场景语义。
- providers/anthropic.py 是 active baseline 的唯一网关 owner，负责 Anthropic Messages、有界 transport retry 与实际 HTTP 请求计数；领域层只负责 schema/语义 retry。

## 信息边界

| 层 | 可见 | 禁止进入 |
|---|---|---|
| Evaluated policy / T4 | 角色、背景、显式目标、可观察历史、回应、expression、media | hidden intention、S/D、appraisal、delta、阈值、未来 |
| T1/T2/T3 输入 | 任务所需可观察历史/checkpoint/候选自由文本 | private trajectory fields、作者假设、模型生成答案 |
| Author-side environment | persona、hidden intention、S/D、相关 observable memory、action | 未来轨迹或预设 action 结果 |
| Human annotation | 冻结的公开实例、rubric、独立证据要求 | simulator delta 作为 ground truth |
| Annotation website | scenario、rollout、task 公开题面与研究者诊断视图 | 写入正式文件、伪造签名或维护第二套状态机 |

## 轨迹和局部干预

每个场景只生成一条自然轨迹。每条 run 保存 base seed；Anthropic Messages provider 按 base seed + call index 推进随机流，既可复现又避免每回合重置同一采样。Gate 3 只判断这条轨迹是否合格，不做 best-of-N、跨 seed 排名或失败后补抽。轨迹间的总体多样性来自场景设计和自然历史；模型与 seed 仅作 provenance。T2 先选一条人物与历史连贯的真实轨迹 A，在有意义的 checkpoint 后改写并重新计算 B；A/B 共享分叉前历史，并使用在两边都自然可信、字节级相同的受控 ending O*。固定 ending 只属于 T2 构造，不扩展为在线对话脚本。T3 从真实 checkpoint restore 同一 private snapshot，为 2–4 个自由文本行动各执行一次局部 intervention，随后继续使用与源轨迹匹配的同一模型配置。snapshot 同时冻结 scenario-authored 外生 event plan 与片段边界；每个分支记录实际经过时间和跨越事件，由 action 自身导致的后果可以不同，外部条件不得随机分叉。受控 intervention 是实验工具，不是多轮 rollout policy。

## Scenario bundle

每个 `scenario_NNN/` 的 JSON 是机器事实源，同名 Markdown 是确定性生成的人类说明，含故事初始化、S0/D0、作者化多片段时间线/事件池、视频阈值与质量状态。批次目录和运行产物分离：场景目录不内嵌历史模型 rollout。JSON 改动后必须刷新确定性文档并重新进行 hash-bound Gate 1；旧签名自动失效。

S0/D0 的候选值与真人冻结协议见 [`S0_D0_REVIEW.md`](../protocols/S0_D0_REVIEW.md)。Talking Head 是可选的批次级扩展：当前旧素材与 manifest 已归档，没有活跃媒体资产。生成和审核脚本继续保留；未来新批次必须创建自己的 manifest，请求只含公开表演指令，并通过视频流、音轨、时长、分辨率和帧率检查。网站的受限 `/media/<asset_id>` 路由在没有 manifest 时返回空集，不接受任意文件路径。

影视来源只允许贡献高层社会机制。`extract-structure` 的结构合同强制记录必须丢弃的表层元素以及原创化要求；后续 source 必须使用新人物、新场域、新事件、新 stakes 和原创语言，不复制台词、角色或标志性情节序列。

## Prompt 和 schema

所有固定模型指令只放在 `prompts/`，文件名以 `_vN.md` 结尾。运行时代码通过 `prompts.loader` 加载并校验 manifest hash；`scripts/update_prompt_manifest.py` 是唯一登记命令。模型结构化输出分别由 `schemas/` 合同和 Python validator 约束。完整职责映射见 [`PROMPT_AUDIT.md`](../prompts/PROMPT_AUDIT.md)。

## Instance 质量

T1/T2/T3 均绑定持有 latent state 的环境角色，而不是输出 action 的 evaluated model。结构审计检查无泄漏、目标 state、历史形状、精确重复、T2 双方角色与 private-state 分化、T3 checkpoint/branch 完整性，并按 source model 与 scenario 双重汇总；轨迹审计另按 scenario 报 action/response 唯一率、简洁性和 latent 边界占比。语义质量采用移除 model/provider/trajectory provenance 的盲化 packet。九项验收自动读取该质量报告；轨迹质量未过时不得标 Full-Trajectory provisionally ready。自动或 LLM 分数均不能替代 human answerability 与标签有效性评审。

开发池修复采用事务式 replacement：只有四 Gate 报告中明确 `rejected` 的
trajectory ID 才进入自动重采样；新候选先过结构门，再由两个独立 seeded
Claude review 请求预筛。它们提供请求级复核，不构成跨模型族独立证据。候选通过后先写新文件与新 manifest，再把旧文件移动到
bundle 内的 `rollouts/rejected/` 并记录 old/new ID、原因、尝试次数和 judge
证据。失败候选逐条写 JSONL，包含人工可见的完整对话，不会静默丢弃。
历史上的 `t2_pairing_rebalance` 只作为旧开发实验留痕；当前生产构建不再为模型均衡替换轨迹，也不得把来源不均衡伪装成 Gate reject。

正式 rollout judge 的采样 seed 由基础 seed 与 trajectory ID 的 SHA-256
确定，因此同一轨迹在单条、批量或不同排序下得到相同判定。开发筛选的最终
证据采用 Claude 主审和独立 seed 的 Claude 二审；正常正式流程仍按
`gate.md` 使用全量主审加确定性分层/争议二审，且保留真人抽查。合并器对 hard reject 取并集、
对维度分数取均值，并要求证据 ID 与当前活跃 manifest 完全一致。

History dependence 的 Full / Recent-k / Critical-event-removed 三个 policy
条件使用同一模型配置与同一 seed 重新采样；原 rollout action 只作为审计字段，
不参与受控差异计算。环境侧在相同 S/D 与 action 上只执行 canonical appraisal
和 state update，因为后续 response 不影响已经得到的解释/delta，且不属于该
指标。脚本逐条落盘、支持断点续跑和按 trajectory ID 定向复验；证据合并器
拒绝任何缺失活跃 ID 的结果。

## 人工标注工作台

`web/` 保留为 Scenario、rollout、task 与 Talking Head 的人工审核工作台。当前默认入口读取 GPT 小规模设计实验的 exact scenario JSON；浏览器草稿不构成签名。历史四 Gate 页面保留框架，但旧 Qwen/Scale300 数据已从活跃路径归档。

模型通过版本化 route table 按语义角色注入。GPT 小规模批次用于设计审计，Claude 用于后续主批次；任何模型名都不得写死在业务模块，批次必须以 manifest 和 provenance 为入口。

## 验收

当前 gate 固定为九项：State-Update Human Agreement、Persona Sensitivity、Paraphrase Robustness、History Intervention、Local Action Intervention、Neutral-State Stability、Response-State Consistency、Full-Trajectory Plausibility、Seed Robustness。自动结构证据只能标为 pending/evidence_ready/provisionally_ready；需要真人的项目没有评审记录不得标 pass。

`gate.md` 在九项环境验收之外约束正式数据来源：每场景恰好 1 条自然结束在 10–20 轮的轨迹、模型只作为 provenance、各语义 role 保持独立请求、六维质量评分、十类 hard reject，以及 Gate 3 对唯一轨迹的合格/淘汰；

## 架构不变量

- 正常生成不得出现固定 action taxonomy 或 scripted trajectory。
- 同一 canonical environment 必须用于离线和 T4。
- canonical scenario 的 max_turns=20 是上限；offline 主候选须自然结束在10–20轮，T4最多20轮并允许自然结束。轨迹可由多个可变长度互动片段组成，只有 ending 与实际对话一致才可进入后续评分。
- 片段间必须公开经过时间和再次互动原因；期限到达不是履约，fulfilled/partial/unfulfilled 必须来自 scenario-authored event record。
- evaluated-agent prompt 必须显式提供其公开身份与 explicit goal，但禁止提供对方 hidden intention、persona 数值或任何 S/D/transition 私有量。
- T1/T2/T3 必须由自然轨迹派生。
- T3 干预必须 restore 同一真实 checkpoint。
- LLM judge 不是 human ground truth。
- 公开实例不得泄漏 private fields。
- 未批准 scenario 默认拒绝正式 rollout。
- 正式 rollout 必须写入隔离的 `data/formal/`，不得复用开发轨迹。
- 单 Judge、同模型族双 Judge 或缺失历史/骨干证据不能生成 formal_selected。
- selected manifest、文件或 quality-audit ID 不一致时不得构建任务。
- 开发池逐轨迹筛选通过不等于正式池合同通过；正式池必须证明每个 Gate-1-approved 场景恰有一个 rollout slot，且没有失败后补抽。
- secrets 只来自环境变量，公开 manifest 删除 secret 及环境变量名。
