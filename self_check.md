# SocialFlux Self Check

> 维护规则：每次任务结束都必须重新读取并自查本文件。完整完成的条目标记 [x]，未完成或仅部分完成的保留 [ ]；不得删除既有条目。

> 勾选标准：必须有可复核的代码、产物或测试证据。标明需要真人审核、标注员、真实模型 API 或视频资产的条目，在没有对应记录前不勾选。

> 最后自查：2026-09-23。

> 当前主链：先完成 GPT 小规模端到端设计审计，再扩大 Claude 主批次；每个通过 Gate 1 的场景只生成 1 条自然 rollout，不做 3 seed 或 best-of-N。唯一入口为 `python -m pipeline`。Gate 1–4 的正式人工证据和正式 tasks 尚未完成。以下既有条目与历史记录按维护规则保留，不因主链升级而删除或伪造完成状态。

> 历史快照（2026-09-18，不代表当前 pipeline）：20个scenario、全部rollout配置、Gate 3与T4已统一为连续`t1..t20`；被测模型使用明确身份、角色和explicit goal，网站同时展示研究者私有persona/hidden intention与被测模型实际公开输入。旧184条轨迹均只有6轮，当前Protocol重筛结果为REJECT=184、provisional winner=0；旧180个Task只作历史审计。新的20×3质量候选池已由可断点脚本启动，实时完成数见`build/rollout_20turn_3candidate/progress.json`；模型族只记录provenance，不设配额。旧 Talking Head 的60条低质量资产及本地引擎已永久删除，仅保留等待外部 API 的框架；本轮工程验证为core 168/168、web 8/8、Prompt 30/30、scenario文档20/20。真人Gate、全量20轮池、重筛选、新Task和正式研究验收仍未完成。

## Revision v2 工程自查

| 条目 | 完成标准 | 自查 |
| --- | --- | --- |
| R1 自由 action | 生产环境拒绝 action_id，不存在固定 action taxonomy/effect table | [x] |
| R2 单一环境 | offline rollout 与 T4 共用 StatefulEnvironment/ModelEnvironmentFactory | [x] |
| R3 Hybrid source | narrative-derived 与 synthetic-script 进入同一 blueprint/scenario schema | [x] |
| R4 Scenario review gates | quality 人工批准后 normalization，initial state 单独 candidate→freeze；runtime dynamics seed 机器校验 | [x] |
| R5 Rollout-derived tasks | T1 natural checkpoint、T2 natural histories+O*、T3 real checkpoint local branch | [x] |
| R6 九项验收 scaffold | 报告固定九项且无证据不标 pass | [x] |
| R7 Prompt/schema audit | 30个固定prompt、hash manifest、职责/边界/schema linkage；rollout Judge v2强制逐维turn-ID证据 | [x] |
| R8 真实自然 trajectory pool | 旧六轮开发池已真实生成但已按20轮合同全部淘汰；新版20×3池单列于R18/G11 | [x] |
| R9 正式研究验收 | 九项真人/模型实验与 adjudication 全部完成 | [ ] |
| R10 影视结构原创化 | 影视来源只抽象高层社会机制；新增 10 个原创 scenario 且不复制角色、台词或情节序列 | [x] |
| R11 Instance target/quality | T1/T2/T3 指向 environment character；结构审计与盲化语义质量协议可运行 | [x] |
| R12 GPT–Qwen rollout 对照 | 同 environment/construction、匹配 scenario/seed 后比较任务质量；Qwen 已跑，GPT 匹配运行与盲审结果尚未落盘 | [ ] |
| R13 历史Qwen六轮pilot | IA_PIPE_011两个seeds、6 turns及旧Task可复核，但只作迁移前审计，不再是有效长程数据 | [x] |
| R14 20-scenario新版抽查包 | 每个scenario完成10–20轮候选筛选后重建T1/T2/T3、dialogues.md、tasks.md与逐场景bundle audit | [ ] |
| R15 人工标注网站 | 可视化20个情节、完整persona/hidden intention、被测prompt与信息边界、184条旧失败rollout、180个历史Task、60视频和所有人工Gate；本地草稿、进度和JSON导出 | [x] |
| R16 Screening Protocol v1 | 精确三态阈值、10项hard reject、严格20轮、全REJECT不强选winner、184条旧库存与协议五问均有代码/报告/网站证据 | [x] |
| R17 文档与论文证据整理 | `docs/` 分类索引、Prompt catalog、paper evidence index、当前/归档实验分层、内部链接检查；无审计价值垃圾已清除 | [x] |
| R18 统一 20 轮合同 | 20 个 scenario、全部 rollout 配置、Gate 3 和 T4 runner 均强制 20 轮；新轨迹实际落盘并重筛选 | [ ] |
| R19 被测角色与 Prompt 可审计 | 每个角色有明确身份/目标；网站展示prompt实参和作者私有字段且验证不泄漏 | [x] |
| R20 20轮断点生成 | 60个固定槽位、逐条原子落盘、失败/替代seed留痕、resume复验与多worker执行脚本 | [x] |

## gate.md 正式数据约束自查

| 条目 | 完成标准 | 自查 |
| --- | --- | --- |
| G1 自由轨迹来源 | 同一 stateful environment、无预定义策略、T1/T2/T3 只从完整轨迹派生 | [x] |
| G2 模型池合同 | 每场景至少3条20轮质量候选；模型族只记录provenance，不设配额；environment/policy分离 | [ ] |
| G3 开发/正式隔离 | formal_raw 独立目录、旧 Qwen3.5 开发轨迹不能进入 final | [x] |
| G4 六维与 hard reject | 六维独立评分、缺证据 pending、Protocol v1 十类 hard reject 与确定性三态阈值 | [x] |
| G5 Post-hoc selection | rollout 后 outcome 标注、近重复过滤、全局多样性报告、每场景人工确认 1 条 | [ ] |
| G6 History dependence | 同 checkpoint 的 Full / Recent-k / Critical-event-removed 同时比较 evaluated action 与 environment interpretation，正式轨迹必须有证据 | [x] |
| G7 Judge + audit | 全量机器主审 + 跨模型族确定性分层/边缘二审，缺必需audit不能合并完成 | [x] |
| G8 Backbone sensitivity | 同 checkpoint/action 在两个 environment backbone 重放并设方向阈值 | [ ] |
| G9 真人签名边界 | scenario/initial state 与精确 JSON hash 绑定；runtime dynamics seed 不单独人签；Gate 2 要求实名/时间戳；自动化不能签名 | [x] |
| G10 Gate 4 + audited machine GT | T1/T2/T3机器答案绑定实例hash；两人审同一抽样，分歧由第三人adjudicate | [x] |
| G11 正式质量候选池 | 20 × 3 本地真实rollout产物通过配置/来源审计 | [ ] |
| G12 正式发布证据 | 每场景1条human-confirmed selected、Judge/audit、history/backbone、Gate 4抽查全部通过 `verify_gate_md.py --strict` | [ ] |

## 当前剩余 TODO（按阻塞顺序）

以下是长表的执行视图，不替代也不删除后面的历史条目。自动推荐不等于人工通过；浏览器草稿导出后仍需进入签名 registry/正式证据文件。

- [x] 按 Screening Protocol v1 建立184条旧库存、三态判定、六维分数、10项hard reject和确定性人工队列；新20轮规则下结果为184条REJECT、0条winner。
- [x] 禁止从全REJECT场景物化winner；旧原始与淘汰轨迹保留在audit archive，不进入新版canonical pool。
- [x] 网站展示全部184条旧rollout、180个历史任务、60个视频、完整persona/hidden intention、被测prompt/排除字段和全部人工Gate。
- [x] 新rollout Judge prompt/schema固定逐维1–3个有效turn ID；caller验证引用，旧证据统一显示warning。
- [x] 被测模型使用配置指定的 T4 prompt（在线 T4 为 `task_t4_action_v21`；离线 10–20 轮 rollout 为共享的 `task_rollout_action_v1`），固定角色身份、explicit goal、反复述 ledger 和公开信息边界；T4 在自然结束或预算结束后评分。
- [x] 20×3质量候选配置与断点生成器已实现；Qwen3.5 environment-only，policy按pilot通过率优先使用Qwen3-32B。
- [x] Markdown已按架构、协议、操作、Prompt、设计输入和论文证据归档；本轮T4失败与20轮smoke已留痕。
- [ ] **P0 自动长任务：**完成`build/rollout_20turn_3candidate/progress.json`中的60/60槽位；重试耗尽项不得伪装完成。
- [ ] **P0 自动+人工筛选：**对新20轮池运行双Judge/history/backbone/Protocol，并在网站逐场景比较后确认20个唯一winner。
- [ ] **P0 Task重建：**仅从新20轮筛选来源重建每场景T1/T2/T3及自然语言抽查Markdown。
- [ ] **P0 人工：**审核20个scenario的来源、原创性、六维质量和initial state，并生成真实reviewer签名与精确hash绑定的freeze registry；runtime dynamics seed 仅做机器校验。
- [ ] **P0 人工：**逐条检查60个视频的expression–state consistency、temporal continuity、speech naturalness与multimodal utility。
- [ ] **P0 Gate 2：**由1名审核员完成 E1–E9 环境证据抽查；自动脚本不能代签，失败项必须修复后复验。
- [ ] **P1 模型 pilot：**部署并记录 GLM-4-32B 量化服务的显存、吞吐和失败证据；在相同 scenario/seed/budget 下与 Qwen3-32B、DeepSeek 做盲审比较。
- [ ] **P1 正式 raw：**Gate 1/2 通过后生成或确认 20×3=60 条 environment/policy 分离的自然 rollout；模型只按质量选择并完整记录provenance。
- [ ] **P1 正式筛选：**对60条使用Judge v2、确定性二审audit、history intervention、backbone sensitivity和Protocol v1；1人主审、第二人少量audit后每场景仅留1条。
- [ ] **P1 Gate 4：**从正式 selected pool 构建 T1/T2/T3；T2 的第二历史只能作为通过 Gate 3 与人工审核的 task-local auxiliary history。
- [ ] **P1 正式 GT：**LLM生成T1/T2/T3机器建议答案；Gate 4两人独立抽查同一确定性样本，分歧由第三人adjudicate，并通过 `verify_gate_md.py --strict`。
- [ ] **P2 发布：**完成 filter-dev/holdout、重复与泄漏、template artifact、影视来源/模型污染人工审核和 benchmark freeze。

| Phase | 模块 | 具体要做什么 | 产物 | 是否人工 | 优先级 | 自查 |
| --- | --- | --- | --- | --- | --- | --- |
| **0** | 核心定义 | 最终确定项目名、construct、T1–T4 定义 | Framework vFinal | 否 | 🔴 | [x] |
| 0 | Global Ontology | freeze Emotion / Behavioral Disposition / Relationship / Dynamics 全局变量池 | `ontology.yaml` | 人工设计 | 🔴 | [ ] |
| 0 | 数值体系 | freeze state range、7-level delta → numeric mapping | state spec | 否 | 🔴 | [x] |
| 0 | T3 Horizon | 默认 delayed = 5 turns，最长 10；确定 continuation protocol | T3 spec | 否 | 🔴 | [x] |
| 0 | Episode | 定义 max turns、提前结束、关系破裂、goal achieved 等 termination | termination spec | 人工设计 | 🔴 | [ ] |
| **1** | Scenario Schema | Persona / Background / Goal / Hidden Intention / state subset / triggers schema | `scenario.schema.json` | 否 | 🔴 | [x] |
| 1 | Scenario 01 | 完整制作第一个 scenario（可继续用 authorship conflict） | `scenario_01.yaml` | 人工审核 | 🔴 | [ ] |
| 1 | Initial State | 根据 scenario 生成 candidate initial state 与 runtime dynamics seed | candidate state/config | 是 |  | [x] |
| 1 | Initial State | 人工 review → freeze initial state；机器校验 runtime dynamics seed | frozen initial state | 是 | 🔴 | [ ] |
| **2** | Provider | OpenAI-compatible / Anthropic / Gemini / vLLM 等统一接口 | `providers/` | 否 | 🔴 | [x] |
| 2 | Policy | `policy.generate(observation)` | policy abstraction | 否 | 🔴 | [x] |
| 2 | Memory | full history / retrieval / summary 第一版实现 | memory module | 否 | 🔴 | [x] |
| 2 | Appraisal | 实现当前确定的 appraisal prompt | appraisal JSON | 否 | 🔴 | [x] |
| 2 | State Update | semantic delta → deterministic numeric update | transition module | 否 | 🔴 | [x] |
| 2 | Dynamics | escalation / breakdown / viability 更新 | dynamics module | 否 | 🔴 | [x] |
| 2 | Response | updated state → environment response | response module | 否 | 🔴 | [x] |
| 2 | Logging | 保存完整 hidden + observable trajectory | trajectory JSONL | 否 | 🔴 | [x] |
| **3** | Video Trigger | 实现 state threshold / crossing trigger | trigger engine | 否 | 🟠 | [x] |
| 3 | Expression Layer | state → facial/prosody/behavioral cue specification | expression JSON | 人工抽查 | 🟠 | [ ] |
| 3 | Sparse Media | 普通节点 text；达到条件触发 multimodal event | multimodal event schema | 否 | 🟠 | [x] |
| 3 | Video | 接 Talking Head / video generator | media assets | 是/自动 | 🟡 | [x] |
| **4** | Smoke Test | 手工输入若干 actions 看 state 是否更新 | debug logs | 人工 | 🔴 | [ ] |
| 4 | Long Rollout | 跑 5 / 10 / 20 turns 检查有没有 state 爆炸、锁死、循环 | debug trajectories | 人工抽查 | 🔴 | [ ] |
| 4 | API Rollout | 多个模型从相同 initial state 与 runtime dynamics seed 正常跑通 | trajectories | 否 | 🔴 | [ ] |
| **5A** | **Deprecated Controlled Sensitivity** | revision 已废弃固定三策略多轮 rollout；仅保留局部 checkpoint intervention | 不再执行 | — | — | [ ] |
| 5A | Deprecated Controlled Sensitivity | 不用 authored expected direction 验证 environment | 不再执行 | — | — | [ ] |
| **5B** | **Paraphrase Robustness** | 同 history/state，输入语义等价 action pairs | paired transitions | 是 | 🔴 | [ ] |
| 5B | Paraphrase Robustness | 比较 \(\Delta S_A\approx\Delta S_B\) | similarity metric | 自动 | 🔴 | [ ] |
| **5C** | **Persona Sensitivity** | 固定 H/S/A，只改变 persona trait | paired transitions | 是 | 🔴 | [ ] |
| 5C | Persona Sensitivity | 验证 persona → appraisal → transition 真有作用 | sensitivity result | 是+自动 | 🔴 | [ ] |
| **5D** | **State Update Human Validation** | 抽 30–50 transitions | annotation set | 1 reviewer | 🔴 | [ ] |
| 5D | State Update Human Validation | 人标 decrease / similar / increase + plausibility | agreement | 是 | 🔴 | [ ] |
| **5E** | **Trajectory Plausibility** | 抽 15–20 条完整 trajectory | validation set | 1 reviewer | 🔴 | [ ] |
| 5E | Trajectory Plausibility | State continuity / history sensitivity / persona consistency / response-state consistency / overall plausibility | human scores | 是 | 🔴 | [ ] |
| **5F** | **Response-State Consistency** | 相同 context、不同 hidden state，检查 response 是否合理变化 | paired responses | 是 | 🔴 | [ ] |
| **5G** | **History Sensitivity** | Full history vs remove relevant event | paired transitions | 人工+自动 | 🔴 | [ ] |
| **5H** | **State Stability** | neutral/no-op actions 不应导致 state 大幅漂移 | stability trajectories | 自动+抽查 | 🟠 | [ ] |
| **5I** | **Order Sensitivity** | 相同 events 改变合理的时间顺序 | paired trajectories | 自动+人工 | 🟠 | [ ] |
| **5J** | **Reproducibility** | 同配置不同 seed 重跑 | variance statistics | 否 | 🟠 | [ ] |
| **6** | Gate A | Scenario 01 是否通过 Environment Engineering Gate | acceptance report | 是 | 🔴 | [ ] |
| **7** | Scenario Design | 设计 20 个**主题真正不同**的 social scenarios | 20 scenario specs | 人工 | 🔴 | [ ] |
| 7 | Coverage | 检查 relationship / conflict / goal / ontology coverage | coverage matrix | 人工 | 🔴 | [ ] |
| 7 | Initial State | 每个 scenario candidate → review → freeze initial state；机器校验 runtime dynamics seed | 20 initial states | 是 | 🔴 | [ ] |
| 7 | Trigger Rules | 每 scenario 定义 relevant multimodal triggers | trigger configs | 人工 | 🟠 | [ ] |
| **8** | Rollout Generation | 每个 scenario × 多个 model policies × seeds | master trajectory pool | 否 | 🔴 | [ ] |
| 8 | Quality Filter | malformed / incoherent / terminated-too-early trajectories 清洗 | clean pool | 自动+抽查 | 🔴 | [x] |
| **9** | 20-Scenario Validation | 每个 scenario 都做 local checkpoint intervention | validation results | 是+自动 | 🔴 | [ ] |
| 9 | 20-Scenario Validation | 每个 scenario 抽 state updates 人工验 | validation set | 是 | 🔴 | [ ] |
| 9 | 20-Scenario Validation | 每个 scenario 抽完整 trajectories 人工验 | validation set | 是 | 🔴 | [ ] |
| **10** | T1 Builder | 从普通 rollout checkpoints 抽 T1 | candidate T1 | 否 | 🔴 | [x] |
| 10 | T1 Balance | 控制 state / intensity / change / scenario 分布 | balanced T1 | 自动 | 🔴 | [ ] |
| **11** | T2 Retrieval | 从 rollout pool 找 divergent-history candidate pairs | candidate pairs | 否 | 🔴 | [x] |
| 11 | T2 Construction | B retrieval + C identical \(O^*\) injection | candidate T2 | 自动 | 🔴 | [x] |
| 11 | T2 Compatibility | 判断 \(O^*\) 对 A/B history 都自然 | filtered T2 | LLM+人工抽查 | 🔴 | [ ] |
| 11 | T2 Leakage | 确保 current observation 单独不能泄漏 A/B difference | leakage test | 自动+模型 | 🔴 | [ ] |
| **12** | T3 Branching | checkpoint 上生成 2–4 candidate actions | branches | 自动 | 🔴 | [x] |
| 12 | T3 Immediate | rollout candidate → \(S_{t+1}\) | immediate effects | 自动 | 🔴 | [x] |
| 12 | T3 Delayed | 相同 continuation protocol rollout 默认 5 turns | delayed effects | 自动 | 🔴 | [x] |
| 12 | T3 Long Horizon | 部分需要时延长到 ≤10 turns | delayed effects | 自动 | 🟠 | [x] |
| 12 | T3 Stability | 多 seed 检查 delayed direction 是否稳定 | confidence/filter | 自动 | 🔴 | [ ] |
| **13** | **Audited Machine GT** | LLM生成T1答案；Gate 4抽取同样本复核 | T1 audited-machine GT | 2 auditors；分歧时第3人 | 🔴 | [ ] |
| 13 | Audited Machine GT | LLM生成T2 pairwise state + evidence + causal action；Gate 4抽查 | T2 audited-machine GT | 2 auditors；分歧时第3人 | 🔴 | [ ] |
| 13 | Audited Machine GT | LLM生成T3 immediate/delayed effect；Gate 4抽查 | T3 audited-machine GT | 2 auditors；分歧时第3人 | 🔴 | [ ] |
| 13 | Adjudication | disagreement / ambiguous cases 复审或删除 | final GT | expert/human | 🔴 | [ ] |
| 13 | Agreement | Fleiss κ / Krippendorff α / weighted κ 等 | annotation statistics | 自动 | 🔴 | [ ] |
| **14** | T1 Baselines | 主流模型跑 T1 | results | 否 | 🔴 | [ ] |
| 14 | T2 Baselines | 主流模型跑 T2 | results | 否 | 🔴 | [ ] |
| 14 | T3 Baselines | 主流模型跑 T3 | results | 否 | 🔴 | [ ] |
| 14 | T4 Baselines | 主流模型进入 environment 自由互动 | trajectories + scores | judge+人工抽查 | 🔴 | [ ] |
| **15A** | **Full History Ablation** | Full History | score | 否 | 🔴 | [ ] |
| 15A | History Ablation | Recent-k | score | 否 | 🔴 | [ ] |
| 15A | History Ablation | Current Observation Only | score | 否 | 🔴 | [ ] |
| 15A | History Ablation | Shuffled History | score | 否 | 🔴 | [ ] |
| **15B** | **Persona Ablation** | With Persona vs No Persona | score | 否 | 🔴 | [ ] |
| **15C** | **Oracle-State Ablation** | T3 hidden-state vs Oracle Current State | score | 否 | 🔴 | [ ] |
| **15D** | **Memory Ablation** | Full history vs recent-k vs retrieval/summary | score | 否 | 🟠 | [ ] |
| **15E** | **Multimodal Ablation** | Text vs Text+Video | score | 否 | 🟠/🔴* | [ ] |
| **15F** | **Video Trigger Ablation** | state-triggered cues vs no-video / controlled modality condition | score | 否 | 🟠 | [ ] |
| **16** | T4 Judge | freeze Goal / Adaptation / Risk / Recovery / Relationship rubric | judge spec | 人工设计 | 🔴 | [ ] |
| 16 | T4 Judge Validation | LLM judge vs human ratings correlation/agreement | judge validity | 是 | 🔴 | [ ] |
| 16 | T4 Analysis | per-model multidimensional profiles | result tables | 否 | 🔴 | [ ] |
| **17** | Difficulty | Chance / weak / medium / strong model performance | benchmark difficulty | 否 | 🔴 | [ ] |
| 17 | Ceiling | human performance / agreement | human ceiling | 是 | 🔴 | [ ] |
| 17 | Scenario Breakdown | 每个 scenario 单独报告 | breakdown | 否 | 🔴 | [ ] |
| 17 | State Breakdown | Emotion / Behavior / Relationship 分开报告 | breakdown | 否 | 🔴 | [ ] |
| 17 | Horizon Breakdown | T3 immediate vs 5-turn vs optional longer horizon | breakdown | 否 | 🔴 | [ ] |
| **18** | Dataset Audit | duplicate / leakage / label imbalance / template artifacts | audit report | 自动+人工 | 🔴 | [ ] |
| 18 | Prompt Leakage | benchmark input 是否暴露 hidden intention/state/trigger | audit | 人工+自动 | 🔴 | [ ] |
| 18 | Model Contamination | scenario 是否过于接近公开 benchmark/template | audit | 人工 | 🟠 | [ ] |
| **19** | Final Benchmark | freeze 20 scenarios + splits + T1/T2/T3 + T4 | v1 dataset | — | 🔴 | [ ] |
| 19 | Documentation | README / task specs / schemas / evaluation scripts | release package | — | 🔴 | [ ] |
| 19 | Paper | Environment validation + benchmark + ablations + analysis | paper | — | 🔴 | [ ] |


| # | 实验 | 操纵什么 | 理想结果 | 证明什么 | 自查 |
| --- | --- | --- | --- | --- | --- |
| V1 | **Deprecated Controlled Policy Sensitivity** | revision 已废弃三策略多轮 rollout | 不纳入当前 gate | 保留历史条目 | [ ] |
| V2 | **Paraphrase Robustness** | 语义相同、表述不同 | \(\Delta S\) 高度相似 | 不是关键词触发器 | [ ] |
| V3 | **Persona Sensitivity** | Persona 改，H/S/A 不变 | appraisal/state 按 persona 合理变化 | Persona 真正在工作 | [ ] |
| V4 | **Human State-Update Agreement** | 人 vs simulator | transition direction 高 agreement | state transition 有人类合理性 | [ ] |
| V5 | **Trajectory Plausibility** | 人看完整 rollout | continuity/coherence 高 | 长期 dynamics 合理 | [ ] |
| V6 | **Response-State Consistency** | context 固定、state 改变 | response 随 state 合理变化 | state 不是 decorative logging | [ ] |
| V7 | **History Intervention** | 删除关键历史事件 | 后续 appraisal/state 明显改变 | Environment 真有 longitudinal memory | [ ] |
| V8 | **Neutral-State Stability** | neutral/no-op action | state 不应无故大幅漂移 | 防止 state random walk | [ ] |
| V9 | **Timescale Validity** | 按状态族抽样变化轨迹 | fast/medium/slow/context-dependent 变化速率与证据一致 | E9 机器统计 + 人工复核 | [ ] |
| V10 | **T2 Leakage Test** | 只给 current \(O^*\) | 应接近 chance/明显下降 | T2 真测 history | [ ] |
| V11 | **History Ablation** | Full / Recent / Current / Shuffle | Full History 最好 | benchmark 真测 longitudinal reasoning | [ ] |
| V12 | **T4 Judge Validation** | Human vs automatic judge | 高相关/高 agreement | online score 值得相信 | [ ] |


| # | 视频验证 | 核心问题 | 自查 |
| --- | --- | --- | --- |
| MV1 | **Trigger Validity** | state 到阈值时是否正确触发 | [x] |
| MV2 | **Expression-State Consistency** | 视频表情/语气是否与 latent state 相符 | [ ] |
| MV3 | **Temporal Continuity** | t5→t6 的人物表现是否自然连续 | [ ] |
| MV4 | **Text vs Text+Video** | 视频是否真的给模型提供额外 social information | [ ] |
