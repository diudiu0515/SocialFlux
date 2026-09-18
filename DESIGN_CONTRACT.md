# SocialFlux 设计约束与核心机制

> 本文件是当前项目的单一设计入口。它把最初的设计约定、后来确认的自然互动规则、运行时合同和正式数据发布条件合并在一起。
>
> 代码和 schema 必须实现本文件；运行配置必须显式记录 prompt、模型、seed 和阶段。若旧实验报告、旧 prompt、旧 rollout 或其他说明与本文件冲突，以本文件和当前代码/schema 为准，并把旧材料视为历史证据，不得当作当前正式数据。

## 1. 研究对象

SocialFlux 是一个用于长期社会互动推理的 stateful benchmark。它研究模型能否在同一动态环境中：

- 根据公开历史理解人物的主观状态和互动动态；
- 区分当前事实、承诺、提案、意向、已完成行为和未决事项；
- 预测自由行动的即时与延迟影响；
- 在信息不完全、关系变化和风险变化中持续适应；
- 在 T4 中直接进入环境并完成或合理结束互动。

研究对象是 interaction-conditioned latent social state，不是固定剧情分支，也不是从有限话术类别中选择“最佳回应”。

## 2. 权威层级

当前权威顺序如下：

1. 本文件 `DESIGN_CONTRACT.md`：设计语义、核心不变量、数据和发布条件。
2. `schemas/` 与运行时代码：机器可执行合同；代码不得静默放宽本文件规则。
3. `configs/`：一次实验的具体模型、prompt、seed 和阶段声明。
4. `docs/`：操作手册、协议映射、prompt 审计和论文证据索引。
5. `PROJECT_PROGRESS.md`、`self_check.md`、`reports/`：当前状态、证据和历史记录，不改变设计合同。
6. `docs/source-notes/`：设计决策的历史输入，只用于追溯，不是运行时规范。

旧的设计入口、备份副本和旧 rollout 可以保留为审计材料，但不得被新代码默认读取，也不得冒充当前 canonical 数据。

### 2.1 每次运行前必读：代码结构与修改纪律

本节适用于 rollout、T1–T4 构造、质量筛选、媒体生成和正式评测。开始运行前必须确认当前代码与配置符合本节；不能把“先跑起来”作为继续累积临时补丁的理由。

#### 单一职责与唯一执行路径

- 每项能力只能有一个明确 owner。CLI 只解析参数和调用，orchestrator 只负责编排；选择、生成、状态更新、验证和产物写入由各自领域模块负责。
- 同一任务只保留一条 active execution path。替代实现验证后，更新调用方并删除无调用者的旧路径；历史结果留在 artifact/archive，不保留为可误调用的代码分支。
- 不建立 `_new`、`_v2`、`_final` 或 wrapper-over-wrapper 的长期链条。版本属于配置、manifest 和产物 provenance，不靠复制整套实现表达。
- 同一校验、归属判断或状态转换如果在两个位置出现，先集中到一个有测试的 owner 接口，再继续运行。

#### 禁止补丁式修复

- 不因一条失败台词就在通用代码中增加场景 ID 特判、同义词枚举、词面黑名单、固定回复模板或额外后处理器。
- 不用新的 prompt 条款、正则、normalizer 或 retry wrapper 掩盖上游职责错误。先根据完整失败轨迹判断根因属于 policy、environment response、appraisal/ledger、确定性更新、场景设计还是 validator，再在拥有该职责的层修复。
- 同一根因最多进行两轮有证据的集中修复与验证。仍失败时停止该路径，保留失败正文与请求记录，改做组件/模型对照或替换不合格场景；不得通过改名版本继续同一种补丁循环。
- 机器 validator 只硬拦角色混淆、事实矛盾、私有信息泄漏、无证据把提案/承诺升级为完成等可定位错误。自然度、表达相似和讨论充分度不得靠不断追加词面规则解决。

#### 修改与清理标准

- 修改前先找到 canonical entry point、数据 owner 和现有测试；不得在不了解调用图时新增平行入口。
- 如果一个模块同时承担选择、模型调用、状态变换、质量判断和汇总，先按职责拆分；能扩展现有清晰接口时，不再包一层兼容 facade。
- 替换路径后删除确认无调用者的废弃代码、无效配置和临时 `.orig`/`.rej` 文件，同时保留原始 rollout、失败证据和研究审计记录。不得删除或覆盖用户数据及与当前任务无关的工作区修改。
- 重构必须保持 Structured Appraisal → Python 确定性更新 → Response Generation 的两个独立 LLM stage，以及公开/私有信息边界。重构不是改变研究设定或降低质量门槛的理由。

#### 批次冻结与运行记录

- 生成批次开始后冻结代码、prompt、schema 和配置；批内不得边生成边修改。修复后使用新的 run ID，并在 manifest 中记录版本/hash、模型、seed、实际请求数和修改原因。
- 运行前至少确认：active entry point 唯一；配置引用当前 schema/prompt；相关测试通过；旧产物不会被汇总为本次成功；请求预算与 retry 上限已设置；程序检查、模型复核和人工验收标签彼此分开。
- 运行后如实保留 skipped、rejected、short natural、budget truncated 和 retry 记录。不能用 wrapper 过滤、静默回退或汇总口径隐藏失败。

若确需违反本节，必须在本次 run manifest 中写明理由、影响范围和移除计划；没有记录的临时兼容层不得进入下一次正式运行。

### 2.2 Git 提交与推送纪律

代码、配置、schema、prompt 和文档的修改必须及时形成可审计的 Git
历史，不能长期堆积在未提交工作区。

#### 提交时机与粒度

- 一个职责完整、相关测试通过的工作单元完成后立即提交；开始长时间
  rollout、切换任务、交接工作或结束会话前，必须先处理当前可提交变更。
- 一个 commit 只表达一个连贯目的。功能、无关格式化、实验数据和历史清理
  不应混在同一提交；不得用一个超大提交长期吞并多个无关阶段。
- 不提交已知破坏 active pipeline、缺少必要文件或未通过相关测试的状态。
  需要保存失败实验时，提交的是可复核的报告/fixture，而不是把生产分支留在
  不可运行状态。
- 提交前必须检查 `git status`、`git diff --check`、相关测试和文档链接；
  同时确认没有 secret、private trajectory、`build/`、`data/formal/`、
  模型权重、日志或其他被 `.gitignore` 排除的本地产物。

#### Commit message

- 使用 `<type>: <imperative summary>`，必要时使用
  `<type>(<scope>): <imperative summary>`。
- 常用 type 为 `feat`、`fix`、`refactor`、`docs`、`test` 和
  `chore`；summary 应准确描述结果，避免 `update`、`changes`、
  `misc` 等无信息内容。
- 提交说明和交接记录必须如实写明测试结果、尚未完成的 Gate 与人工边界，
  不得把机器通过写成研究通过。

#### Push 与远端一致性

- 除非任务明确要求只保留本地，commit 成功并通过检查后应及时 push 当前
  工作分支，不把唯一副本长期留在本机。
- push 前先获取远端状态并确认不存在意外分叉；push 后核对本地 HEAD 与
  对应 remote-tracking branch 的 commit hash，并确认工作区干净。
- 禁止向远端推送密钥、签名真人证据、private trajectory 或未授权的大型
  artifact。远端、分支或提交范围不明确时，先取得明确确认。
- 已共享的历史不得擅自 force-push、rebase 或 amend。需要修正时追加新
  commit；只有得到明确授权后才能改写远端历史。

## 3. 不可违反的研究原则

### 3.1 自由互动

- evaluated policy 每轮输出任意非空自然语言文本。
- 不接受 `action_id`、repair/neutral/escalation 类固定策略标签或 action transition table。
- 正常 rollout 不使用 scripted action trajectory，不重复同一策略来制造预期方向。
- diversity 来自模型、采样、seed 和自然形成的历史；结果标签只能在 rollout 后描述，不能在生成前作为策略。
- 场景不得包含 `action_effects`、`response_templates` 或按 action 直接指定 observable cue 的字段。

内部 appraisal 可以把 action 解释成 question、proposal、commitment 等语义事件，但这些是环境的解释结果，不是 evaluated policy 的可选 action taxonomy，也不能直接决定状态变化。

### 3.2 单一 canonical environment

offline rollout、T1/T2/T3 构建所依赖的 checkpoint 和 T4 必须使用同一个 `StatefulEnvironment` 与 `ModelEnvironmentFactory`。不得为 T4 另写一套状态机或 response 逻辑。

每轮唯一顺序为：

```text
public observation O_t
→ free-form action A_t
→ observable-history memory retrieval
→ private appraisal
→ semantic state/dynamics delta
→ deterministic numeric calibration and update
→ response conditioned on updated state
→ sparse expression/media trigger
→ private log + next public observation
```

### 3.3 角色与信息边界

环境角色可以访问 persona、explicit goal、author-only hidden intention、私有 S/D、可观察历史和当前 action。被测 evaluated model 只能看到：

- 自己的公开身份、角色和 explicit goal；
- 公开背景与当前 public situation；
- 对方公开身份；
- 已观察的 action、response、公开时间和事件记录；
- 可观察的 expression、media 和公开 conversation ledger；
- 自己先前的发言以及反重复 ledger。

被测模型、T1/T2/T3 公开题面、公开 judge packet 不得包含：

- hidden intention；
- persona 数值 trait；
- initial/current S 或 D；
- appraisal、semantic delta、numeric delta；
- trigger ID、threshold、未来分支或作者预设结果；
- 只存在于 simulator private log 的证据。

网站可以向研究者展示完整私有诊断，但不能把研究者视图当作模型输入，也不能由浏览器草稿直接签署正式证据。

## 4. 状态、动力学与更新

### 4.1 状态定义

所有 mutable state 和 interaction dynamics 数值范围均为 0–10，表示场景相对强度，不是临床量表或群体规范。

Persona、role、explicit goal 和 hidden intention 是稳定上下文，不是 mutable state。

可用状态族包括：

- emotion：anger、anxiety、hope、sadness、fear、guilt、shame、disappointment、relief 等短期主观体验；
- motivation：resolve、avoidance_urge、repair_intent、resistance_intent 等当前行动准备度；
- coping：assertiveness、strategic_patience、evidence_seeking、endurance 等情境化应对取向；
- relationship：trust、hostility、respect、perceived_safety、affiliation 等关系信念或立场。

每个 scenario 只选择与其社会机制相关的变量。相反方向的变量不强制互补，也不要求每轮同时变化。

### 4.2 Interaction dynamics

D_t 与人物主观状态分开。常见 dynamics 包括：

- `goal_failure_risk`：互动正在偏离 evaluated role 的合法目标的风险；
- `escalation_risk`：互动继续下去的成本或困难正在增加；
- `negotiation_open`：有意义的交换和适应是否仍然可能。

客观风险不能伪装成 emotion。新增变量必须有 operational definition、邻近概念区分、可观察/可推断依据和 schema 记录。

### 4.3 Semantic delta 和确定性更新

模型每个选定变量只输出一个 semantic delta：

| semantic delta | numeric update |
|---|---:|
| `strong_decrease` | -3 |
| `moderate_decrease` | -2 |
| `mild_decrease` | -1 |
| `similar` | 0 |
| `mild_increase` | +1 |
| `moderate_increase` | +2 |
| `strong_increase` | +3 |

代码负责 persona sensitivity、inertia、稀疏性、边界裁剪和 numeric log；模型不能直接写数值结果。所有结果裁剪到 0–10。

同一事件可以降低 risk、缓解 emotion，却不恢复 trust 或 motivation。重复确认不自动等于零变化，也不自动持续加分；是否变化必须由当前语义、历史和证据决定。

## 5. 每轮调用合同

每轮有两个逻辑 LLM stage：

1. Structured Appraisal：解释当前 action、引用相关历史、产生 event features、候选 impacts、dialogue diagnostics 和 ledger events。
2. Response Generation：读取更新后的 S/D、当前公开情境和 ledger，生成环境角色的一次可观察回应。

两阶段之间不得调用 LLM；numeric state/dynamics 更新必须由确定性 Python 完成。正常 response 不得看到未来轨迹。

结构化输出必须通过 schema/validator。格式或语义失败可以进行有界 retry；因此“每轮两个 LLM stage”不等于物理 HTTP 请求永远只有两次，实际请求数必须在 provenance 中记录，不能把 retry 隐瞒成两次调用。

## 6. Memory、事实与 interaction ledger

Memory 只能检索 observable history。完整原始历史是权威记录，summary/retrieval 不能制造隐藏状态事实。

Ledger 服务于记忆和一致性，不能把人物强迫成流程机器人。至少区分：

- 谁说话；
- 谁负责执行；
- proposal / attempt / intention 与 firm commitment；
- 接受原提案与新增自身行动；
- 声称完成与公开证据支持的完成；
- 当前 obligation、open proposal、pending question 和 public event。

不确定语义保留不确定性。不得把 promise 自动写成 completed，不得把对方的行动归为当前说话人的承诺，不得凭空新增改变责任、权利、履约、可行性或任务答案的关键事实。

## 7. 自然互动、轮数与结束

一轮统一指 evaluated action 加 environment response；公开时间和事件记录单独计数。

### 7.1 Offline rollout

- `max_turns` 固定为 20，是上限而不是必须填满的剧情清单。
- 10–20 轮内自然结束的轨迹才可进入主数据候选池。
- 少于 10 轮的自然结束如实保留为 `short_natural_trajectory`，不补写、不进入 10–20 主候选池。
- 20 轮仍未结束的轨迹以 `budget_truncated` 记录，保留未决事项，不冒充自然结局；是否进入候选须经过质量门。
- ending 的 reason、turn_id 和实际对话必须一致；提前写 `max_turns`、越界或错误结束为 hard reject。
- 不因“尚未覆盖作者话题清单”禁止自然结束，也不因出现“好的/谢谢”自动结束。

自然结束可以是达成安排、明确拒绝、接受分歧、合理暂停、退出或当前没有继续理由；不要求和解、目标成功、关系改善或所有问题都解决。

### 7.2 跨时间互动

场景可以有多个 interaction segment，但不是每个场景都必须分段。再次互动必须有公开的 elapsed time、recontact reason 和 event record。经过时间不等于履约，承诺不等于完成，后续关系变化必须承接历史，不能直接预设恢复信任。

反事实分支共享 scenario-authored 外部条件；候选 action 引起的后果可以不同，不能把 action 后果也固定。

### 7.3 T4

T4 使用同一环境，最大 20 轮。自然结束允许在 20 轮前发生；只有实际 ending 后才评分。必须区分 `natural_completion` 与 `budget_truncated`/`max_turns`，不得把预算截断写成自然结局。

T4 评分维度为：Goal Achievement、State Adaptation、Risk Management、Recovery、Relationship Outcome。低冲突不自动高分，必须依据 scenario 的真实目标、风险和 trade-off。自动 judge 只能作为机器评分，必须经过人工校准后才能作为正式结论。

当前 T4 默认 policy prompt 为 `task_t4_action_v21`，环境使用
`environment_appraisal_v11` 与 `environment_response_v25`；prompt ID 必须在
config 中显式声明并存在于 `prompts/manifest.json`。诊断实验可使用其他版本，
但必须作为诊断 provenance，不能混入正式 baseline。

## 8. Scenario 创建与冻结

每个 scenario 固定：稳定 persona、社会背景、关系/权力结构、environment explicit goal、author-only hidden intention、evaluated-agent role/goal、候选 S0/D0、终止条件、可观察表达和稀疏 media trigger。

当前 Scale300 由 Claude 直接创建 300 个完整 canonical JSON，不继承、复制或扩展
Scale20/100/150/200 catalog。`scripts/build_scale300_v1.py` 只验证完整性和 schema
并生成确定性投影，不调用模型、不改写语义，也不能设置人工通过状态。

来源至少包括 synthetic-script 和 narrative-derived 两类。

### 8.1 Synthetic-script

模型先写连贯原创社会叙事，再分别进行 normalization 和 initialization。写故事阶段不能同时为 JSON、S0/D0、threshold、T1/T2/T3 答案或预期 delta 服务。

### 8.2 Narrative-derived

只抽取高层社会机制：关系、权力、目标冲突、信息不对称、关键历史和选择空间。必须丢弃原作角色、台词、标志性物件/机构和情节序列，并原创化人物、场域、事件、stakes 与语言。

### 8.3 Gate 1 与 S0/D0

在进入正式环境前，scenario 必须经过真人审核：social plausibility、real trade-off、longitudinal necessity、nontrivial strategy space、motivation coherence、information asymmetry、T1/T2/T3 suitability、T4 adaptation opportunity、no universal script 等。

S0/D0 是候选初始化，不是自动 ground truth。只有真人 reviewer 对精确 JSON hash、来源质量和初始化结果签名后才算 human-frozen。LLM report、机器 gate 和网站草稿不能替代真人签名。

## 9. Offline 数据与任务构建

### 9.1 Raw pool

- 每个已批准 scenario 生成 3 条质量候选；模型族只记录 provenance，不设最终配额。
- 当前 active baseline 的 policy、Structured Appraisal、Response、T1–T4 构造/答案和自动质量复核统一使用 `claude-fable-5`，模型映射只能来自 `configs/model_routes.frontier_api.json`。这是明确的 single-model baseline，不得误称为跨模型独立性证据。
- “统一模型”不改变逻辑和物理调用边界：Structured Appraisal 与 Response 必须是两次独立请求，中间仍只允许 Python 确定性更新；policy、任务答案和 judge 也分别请求并记录各自 prompt、sampling、seed、重试和实际请求数。
- backbone sensitivity 与不同模型族 judge 作为后续单独实验保留，不得把历史多模型配置混入当前 baseline，也不得用旧 benchmark 输出冒充本轮 Claude 产物。
- 只从同一 frozen S0/D0 启动自然 rollout。
- 每条 trajectory 记录完整 private transitions、observable projections、prompt IDs、sampling、seed、environment config 和 ending。
- 所有候选、拒绝原因、替代 seed、Judge evidence 和 manifest 变化必须留痕。

### 9.2 Rollout Quality Gate

六个独立维度：Dialogue Coherence、History Dependence、Character Consistency、State–Response Consistency、Interaction Progression、Naturalness。

hard reject 包括：hidden-state leakage、malformed output、repetitive loop、severe character contradiction、broken dialogue logic、meaningless premature ending、nonsensical state oscillation、implementation-induced state saturation、future-information leakage、unusable trajectory。

机器结构检查、LLM judge 和真人判断必须分开记录。缺分数、缺 history evidence 或缺 required secondary audit 只能是 pending，不能被写成 passed。

### 9.3 Canonical selection

先过质量门，再做 near-duplicate 过滤、post-hoc outcome 描述、多样性检查和人工比较。每个 scenario 最终只保留一条 human-confirmed canonical trajectory；不能按单一总分机械选，也不能为了模型族均衡强留低质量样本。

T1、T2、T3 在合格池上独立选源，一个模型可以零入选，也可以赢得全部任务。任务分数不包含 model identity。

## 10. T1/T2/T3 合同

### T1

从自然 trajectory checkpoint 提取完整公开历史和当前 observation，让模型估计持有 latent state 的 environment character 的当前状态、变化方向和证据。target 必须是环境角色，不能误设成输出 action 的 evaluated model。simulator state 只能作为诊断参考，正式 GT 必须经过人工审核。

### T2

从一条通过来源质量筛选的真实 rollout A 中选择有共享前史的 checkpoint，定位 A 分叉段内可引用的公开证据，再一次性编写连贯的对应 History B。B 保留角色、背景、分叉前历史和已成立事实，只改写锚定区间内有研究意义的互动；不得新增分叉前往事或区间外事件来制造差异。

A/B 分别从分叉 checkpoint 经过正式 Structured Appraisal → 确定性更新 → Response 路径重放，B 不能沿用 A 的后续状态。ending 的台词和可观察行为必须字节级一致，并在两侧都自然；有媒体时两侧引用同一资产。题面显式携带 target environment character 和少量有证据的 target state IDs，模型答案包含差异判断、双侧证据、关键历史事件和表达解释。

若 shared ending 暴露历史差异、发生角色互换、含重复历史、把承诺写成完成、时间/事件顺序错误或对任一历史不自然，则拒绝该 pair。自动 pair review 与 answer review 是模型语义复核，不是人工验收；通过后仍保持 pending human review。

### T3

从有公开历史的真实 checkpoint 提供 2–4 个自由文本候选 action。所有分支 restore 同一个 private snapshot，并共享同一 continuation protocol 和外生 event-plan；随后用与源轨迹一致的自由 policy 继续 5 轮，必要时不超过 10 轮。分支不足、无法完整运行或外生条件不一致时留痕并回退，不能硬凑。

主任务输入不含 oracle state。oracle 只用于单独 ablation 或诊断。

## 11. Multimodal / Talking Head

普通轮次为 text。只有 private state/dynamics 满足 threshold、crossing 或 state-change 条件时才产生稀疏 expression/media event。

公开端只能看到自然表情、视线、停顿、语速、语调、姿态和安全 media metadata，不能看到 trigger ID、threshold、state 名称/数值、hidden intention 或 appraisal。视频建议 3–8 秒，人物身份、时间连续性、音画同步和表达—状态一致性必须分别审查。

## 12. Gate 1–4 与发布

四层不能互相代替：

1. Gate 1：scenario source、质量、原创性和真人 freeze。
2. Gate 2：environment validity，包括 state-update human agreement、persona sensitivity、paraphrase robustness、history intervention、local action intervention、neutral-state stability、response-state consistency、full-trajectory plausibility、seed robustness，以及必要的 backbone sensitivity。
3. Gate 3：raw trajectory 的六维质量、hard reject、history evidence、Judge/audit、去重和 canonical selection。
4. Gate 4：T1/T2/T3 instance 的泄漏、可回答性、证据和 machine proposal 人工抽查。

发布前必须同时满足：

- 300 个 Scale300 scenario 的 source/quality/S0/D0 evidence 完整；
- environment validity 的真人字段已签名，机器结果不能代签；
- 每个 scenario 有合格 raw candidates、Judge/history/backbone evidence 和一条 human-confirmed canonical trajectory；
- T1/T2/T3 仅从合格来源构建，manifest、trajectory、audit 和 instance hash 完全一致；
- Gate 4 对每种 task type 使用同一确定性 10% 样本给两名独立 reviewer；只有分歧才由第三人 adjudicate；
- machine proposal 只有在 Gate 4 通过后才能以明确的 audited-machine 来源发布；
- leakage、duplicate、contamination、holdout 和 multimodal validity 审核完成；
- `scripts/verify_gate_md.py --strict` 成功。

代码能运行、单元测试通过、LLM judge 通过或机器 gate 通过，都不等于正式 benchmark 已通过。

## 13. 文件合同

- `DESIGN_CONTRACT.md`：本文件，唯一设计入口。
- `README.md`：快速开始和常用命令，只引用本文件，不重复定义另一套轮数合同。
- `configs/scale300_v1/CLAUDE_AUTHORING.md`：Claude 直建 Scale300 的输入、输出和人工边界。
- `configs/scale300_v1/scenarios/scenario_NNN/scenario_NNN.json`：当前 Scale300 scenario 机器事实源；`configs/scenarios/` 仅保留 Web/历史诊断使用的 20 场景开发集，不是父 catalog。
- 同目录 `.md`：由 `scripts/scenario_docs.py` 生成的确定性可读投影；必须通过 `--check`。
- `environment/`：唯一状态环境及其 appraisal、update、response、memory、termination、ledger、multimodal。
- `prompts/`：固定运行时 prompt；`prompts/manifest.json` 记录 hash。
- `data/formal/`：正式 raw、judgment、selected 和 task 产物，与开发数据隔离。
- `build/`：可再生聚合产物，不能当作正式证据源。
- `PROJECT_PROGRESS.md`：当前完成/阻塞状态，不写成设计规范。
- `self_check.md`：持续任务清单，不能通过修改勾选框伪造证据。

任何 private trajectory、审计报告、失败候选或旧六轮库存都不得在没有明确 migration/audit 记录的情况下被“升级”为新正式数据。

## 14. 当前实现状态

当前代码已经实现自由文本 action、单一 environment、private/public boundary、两阶段 appraisal/response、确定性 state update、ledger、自然结束分类、T1/T2/T3 builder、T4 judge packet 和 Gate 结构。

当前仍不能宣称正式发布完成：旧 rollout 仅作审计，Scale300 的 900 条正式候选、真人 scenario/S0/D0 freeze、Gate 2/3/4、正式 Judge/history/backbone evidence 和 audited machine GT 仍需以实际产物证明。任何状态更新都必须反映真实文件和报告，不得只改本节文字。
