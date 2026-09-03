# SocialFlux Self Check

> 维护规则：每次任务结束都必须重新读取并自查本文件。完整完成的条目标记 [x]，未完成或仅部分完成的保留 [ ]；不得删除既有条目。

> 勾选标准：必须有可复核的代码、产物或测试证据。标明需要真人审核、标注员、真实模型 API 或视频资产的条目，在没有对应记录前不勾选。

> 最后自查：2026-09-03。

> 本轮记录：已按 revision.md 与 prompt_check.md 完成 v2 架构迁移、legacy 清理、prompt/schema 审计和 42+4 项测试；真实模型 rollout 与九项人工研究验收仍保持未完成。

## Revision v2 工程自查

| 条目 | 完成标准 | 自查 |
| --- | --- | --- |
| R1 自由 action | 生产环境拒绝 action_id，不存在固定 action taxonomy/effect table | [x] |
| R2 单一环境 | offline rollout 与 T4 共用 StatefulEnvironment/ModelEnvironmentFactory | [x] |
| R3 Hybrid source | narrative-derived 与 synthetic-script 进入同一 blueprint/scenario schema | [x] |
| R4 Scenario review gates | quality 人工批准后 normalization，S0/D0 单独 candidate→freeze | [x] |
| R5 Rollout-derived tasks | T1 natural checkpoint、T2 natural histories+O*、T3 real checkpoint local branch | [x] |
| R6 九项验收 scaffold | 报告固定九项且无证据不标 pass | [x] |
| R7 Prompt/schema audit | 19 个固定 prompt、hash manifest、职责/边界/schema linkage | [x] |
| R8 真实自然 trajectory pool | 多模型、多 temperature/seed API rollout | [ ] |
| R9 正式研究验收 | 九项真人/模型实验与 adjudication 全部完成 | [ ] |

| Phase | 模块 | 具体要做什么 | 产物 | 是否人工 | 优先级 | 自查 |
| --- | --- | --- | --- | --- | --- | --- |
| **0** | 核心定义 | 最终确定项目名、construct、T1–T4 定义 | Framework vFinal | 否 | 🔴 | [x] |
| 0 | Global Ontology | freeze Emotion / Behavioral Disposition / Relationship / Dynamics 全局变量池 | `ontology.yaml` | 人工设计 | 🔴 | [ ] |
| 0 | 数值体系 | freeze state range、7-level delta → numeric mapping | state spec | 否 | 🔴 | [x] |
| 0 | T3 Horizon | 默认 delayed = 5 turns，最长 10；确定 continuation protocol | T3 spec | 否 | 🔴 | [x] |
| 0 | Episode | 定义 max turns、提前结束、关系破裂、goal achieved 等 termination | termination spec | 人工设计 | 🔴 | [ ] |
| **1** | Scenario Schema | Persona / Background / Goal / Hidden Intention / state subset / triggers schema | `scenario.schema.json` | 否 | 🔴 | [x] |
| 1 | Scenario 01 | 完整制作第一个 scenario（可继续用 authorship conflict） | `scenario_01.yaml` | 人工审核 | 🔴 | [ ] |
| 1 | Initial State | 根据 scenario 生成 candidate \(S_0,D_0\) | candidate state | 是 |  | [ ] |
| 1 | Initial State | 人工 review → freeze \(S_0,D_0\) | frozen initial state | 是 | 🔴 | [ ] |
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
| 3 | Video | 接 Talking Head / video generator | media assets | 是/自动 | 🟡 | [ ] |
| **4** | Smoke Test | 手工输入若干 actions 看 state 是否更新 | debug logs | 人工 | 🔴 | [ ] |
| 4 | Long Rollout | 跑 5 / 10 / 20 turns 检查有没有 state 爆炸、锁死、循环 | debug trajectories | 人工抽查 | 🔴 | [ ] |
| 4 | API Rollout | 多个模型从相同 \(S_0,D_0\) 正常跑通 | trajectories | 否 | 🔴 | [ ] |
| **5A** | **Deprecated Controlled Sensitivity** | revision 已废弃固定三策略多轮 rollout；仅保留局部 checkpoint intervention | 不再执行 | — | — | [ ] |
| 5A | Deprecated Controlled Sensitivity | 不用 authored expected direction 验证 environment | 不再执行 | — | — | [ ] |
| **5B** | **Paraphrase Robustness** | 同 history/state，输入语义等价 action pairs | paired transitions | 是 | 🔴 | [ ] |
| 5B | Paraphrase Robustness | 比较 \(\Delta S_A\approx\Delta S_B\) | similarity metric | 自动 | 🔴 | [ ] |
| **5C** | **Persona Sensitivity** | 固定 H/S/A，只改变 persona trait | paired transitions | 是 | 🔴 | [ ] |
| 5C | Persona Sensitivity | 验证 persona → appraisal → transition 真有作用 | sensitivity result | 是+自动 | 🔴 | [ ] |
| **5D** | **State Update Human Validation** | 抽 30–50 transitions | annotation set | 3 annotators | 🔴 | [ ] |
| 5D | State Update Human Validation | 人标 decrease / similar / increase + plausibility | agreement | 是 | 🔴 | [ ] |
| **5E** | **Trajectory Plausibility** | 抽 15–20 条完整 trajectory | validation set | 3 annotators | 🔴 | [ ] |
| 5E | Trajectory Plausibility | State continuity / history sensitivity / persona consistency / response-state consistency / overall plausibility | human scores | 是 | 🔴 | [ ] |
| **5F** | **Response-State Consistency** | 相同 context、不同 hidden state，检查 response 是否合理变化 | paired responses | 是 | 🔴 | [ ] |
| **5G** | **History Sensitivity** | Full history vs remove relevant event | paired transitions | 人工+自动 | 🔴 | [ ] |
| **5H** | **State Stability** | neutral/no-op actions 不应导致 state 大幅漂移 | stability trajectories | 自动+抽查 | 🟠 | [ ] |
| **5I** | **Order Sensitivity** | 相同 events 改变合理的时间顺序 | paired trajectories | 自动+人工 | 🟠 | [ ] |
| **5J** | **Reproducibility** | 同配置不同 seed 重跑 | variance statistics | 否 | 🟠 | [ ] |
| **6** | Gate A | Scenario 01 是否通过 Environment Engineering Gate | acceptance report | 是 | 🔴 | [ ] |
| **7** | Scenario Design | 设计剩余 9 个**主题真正不同**的 social scenarios | 10 scenario specs | 人工 | 🔴 | [ ] |
| 7 | Coverage | 检查 relationship / conflict / goal / ontology coverage | coverage matrix | 人工 | 🔴 | [ ] |
| 7 | Initial State | 每个 scenario candidate → review → freeze \(S_0,D_0\) | 10 initial states | 是 | 🔴 | [ ] |
| 7 | Trigger Rules | 每 scenario 定义 relevant multimodal triggers | trigger configs | 人工 | 🟠 | [ ] |
| **8** | Rollout Generation | 每个 scenario × 多个 model policies × seeds | master trajectory pool | 否 | 🔴 | [ ] |
| 8 | Quality Filter | malformed / incoherent / terminated-too-early trajectories 清洗 | clean pool | 自动+抽查 | 🔴 | [ ] |
| **9** | 10-Scenario Validation | 每个 scenario 都做 local checkpoint intervention | validation results | 是+自动 | 🔴 | [ ] |
| 9 | 10-Scenario Validation | 每个 scenario 抽 state updates 人工验 | validation set | 是 | 🔴 | [ ] |
| 9 | 10-Scenario Validation | 每个 scenario 抽完整 trajectories 人工验 | validation set | 是 | 🔴 | [ ] |
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
| **13** | **Formal Human GT** | 最终入 benchmark 的 T1 做 human annotation | T1 GT | 3 annotators | 🔴 | [ ] |
| 13 | Formal Human GT | T2 pairwise state + evidence + causal action | T2 GT | 3 annotators | 🔴 | [ ] |
| 13 | Formal Human GT | T3 immediate/delayed effect validation | T3 GT | 3 annotators | 🔴 | [ ] |
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
| **19** | Final Benchmark | freeze 10 scenarios + splits + T1/T2/T3 + T4 | v1 dataset | — | 🔴 | [ ] |
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
| V9 | **Seed Robustness** | 相同条件不同 seed | qualitative direction 相对稳定 | simulator 可复现 | [ ] |
| V10 | **T2 Leakage Test** | 只给 current \(O^*\) | 应接近 chance/明显下降 | T2 真测 history | [ ] |
| V11 | **History Ablation** | Full / Recent / Current / Shuffle | Full History 最好 | benchmark 真测 longitudinal reasoning | [ ] |
| V12 | **T4 Judge Validation** | Human vs automatic judge | 高相关/高 agreement | online score 值得相信 | [ ] |


| # | 视频验证 | 核心问题 | 自查 |
| --- | --- | --- | --- |
| MV1 | **Trigger Validity** | state 到阈值时是否正确触发 | [x] |
| MV2 | **Expression-State Consistency** | 视频表情/语气是否与 latent state 相符 | [ ] |
| MV3 | **Temporal Continuity** | t5→t6 的人物表现是否自然连续 | [ ] |
| MV4 | **Text vs Text+Video** | 视频是否真的给模型提供额外 social information | [ ] |
