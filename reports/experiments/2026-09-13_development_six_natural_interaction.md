# SocialFlux 自然互动小批量验收（2026-09-13）

## 结论

本轮没有启动 20×3 正式生成。两轮集中修复后，最终固定版本 `development_six_v2_ownership_bound` 在 3 个场景×2 个 seed 上完成 6 次单次候选生成：6 条均生成到自然结束，无预算截断；机器主候选 2/6，但模型语义复核仅认可 IA009 的 2/6，跨场景覆盖为 1/3。IA003 与 IA019 均无合格完整候选，因此当前方案不值得直接扩量。

这里的“模型语义复核”是 Codex 阅读完整轨迹，不是人工验收。

## 1. 保留、停用与修改

保留：

- Emotion、Motivation/Behavioral Disposition、Relationship 与派生 Risk；每轮都有状态更新流程，允许零变化。
- 两个独立环境调用：Structured Appraisal → Python 确定性 calibration/state/dynamics → Response Generation。实际重试单独计数。
- T1、T2、T3、T4 定义、T3 隐藏 latent state、公开事件证据和自然结束的最大 20 轮合同。
- 数值更新、公开事件、版本/hash 绑定与日志链路。

停用：

- hard-only 路径中的词面重复、话题轮数、固定节奏、必须直接回答、固定末轮措辞等自然度硬拒绝。
- 最终片段因达到片段 `max_turns` 自动伪装成自然完成。
- `live_questions` 作为逐项完成清单；现仅是可选讨论空间。
- “非零 event feature 必须产生状态 impact”的要求。

修改：

- Ledger 保留 proposal resolution（接受、拒绝、反提议或不确定处理）及原文证据；conditional commitment 带条件与条件状态，未验证条件不能触发履约事件。
- Ownership validator 只放行 appraisal 明确分配给当前角色的 request 动作；同一句里对方自述的动作不能因另有一个 request 而被接管。
- Response 的 turn brief 明示“分配给你执行的请求”和“对方自有动作”，未新增第三个 LLM 阶段。
- 三个隔离开发场景不再统一五片段：IA003/IA019 各保留有时间依据的三段，IA009 为单段连续互动；没有新增情节事件。

历史证据保存在 `build/development_six_20260913_snapshot/`；第一批冻结在 `build/development_six_v1_batch1/freeze.json`，第二批冻结在 `build/development_six_v2_batch2/freeze.json`。

## 2. 验证与六条候选

短路径：第一轮真实两回合请求为 appraisal 5、response 3；第二轮修复后为 appraisal 2、response 2。第二轮中 tentative proposal、proposal acceptance、未验证条件和未完成状态均按证据记录。主测试第一轮 432/432，第二轮 434/434。网站测试 10/13；三个失败绑定旧工作台 hash/旧 60 条预期，本轮没有伪造 60 条来满足它们。

| 场景/seed | 轮数 | 结束 | 实际请求 P/A/R（总数） | 机器预检 | 模型语义复核 |
|---|---:|---|---:|---|---|
| IA003 / 9301 | 7 | 自然结束 | 7/7/8（22） | 短轨迹；`broken_dialogue_logic` | 拒绝：t6 环境角色逐字接管对方措辞，t5–t7 混淆接受与关系边界 |
| IA003 / 9302 | 11 | 自然结束 | 11/11/12（34） | 拒绝；`broken_dialogue_logic` | 拒绝：t4–t11 持续无信息复述，t5 还把借款人的履约责任反问给出借人 |
| IA009 / 9301 | 3 | 自然结束 | 3/3/3（9） | 短轨迹；无 hard reject | 认可但任务受限：部分数据与接口风险形成合理暂定安排 |
| IA009 / 9302 | 3 | 自然结束 | 3/4/3（10） | 短轨迹；无 hard reject | 本批最好：角色、分工、承诺与完成区分正确 |
| IA019 / 9301 | 11 | 自然结束 | 11/11/11（33） | 主候选通过 | 拒绝：t1–t9 虚构 15%/11%、超募 30%、条款及董事会权力，改变责任/权利/答案；t11 重复 t8 |
| IA019 / 9302 | 14 | 自然结束 | 15/14/14（43） | 主候选通过 | 拒绝：t5 无事件来源却声称已查文件，t9 把方案写成董事会已同意，t14 跨角色逐字复制 |

第二批共 151 次实际请求。机器主候选通过率 2/6（33.3%），模型语义认可率 2/6（33.3%），合格场景覆盖率 1/3。没有 budget truncation。机器通过与语义认可发生错位，说明现有机器预检不能作为扩量替代品。

所有六条的已保存轮次均满足：appraisal/calibration/response 三阶段齐全、calibration 标记为 `deterministic_python`、state/dynamics 数值加法正确、跨轮状态连续。

## 3. 最好样例完整对话

场景：IA009 团队项目分工，seed 9302，共 3 轮，自然暂停。

1. 被评估角色：我觉得我们需要先确认每个人目前实际负责的部分，再讨论接下来怎么协调时间，这样可能比继续争论分工更有效。
   环境角色：我同意，我们可以先整理一下各自负责的部分，然后再讨论后续的安排。
2. 被评估角色：那我先把数据清理和方法说明的部分列出来，你可以同步整理原型和展示方向的分工吗？
   环境角色：我接受你的安排，我会先确认原型部分的分工，再处理展示方向的具体内容。
3. 被评估角色：我先把数据清理的部分整理成共享文档，你同步确认原型分工时，能不能也标出展示稿需要我补充的部分？
   环境角色：好的，我会在整理原型分工的同时，注意标记展示稿需要你补充的部分。

关键状态变化：

| 类别 | 初始 → t1 → t2 → t3 | 依据与判断 |
|---|---|---|
| Emotion | anger 5、anxiety 4、hope 5，全程不变 | 只是形成分工，没有完成交付或新冲突，保持不变合理 |
| Motivation | repair_intent 5→6；resolve 6→6→8→10 | 合作框架与具体分工支持上升；连续两次 +2 偏快，是残余 calibration 风险 |
| Relationship | trust 5、hostility 2，全程不变 | 只有承诺、尚无履约，未提前奖励信任，合理 |
| Risk/dynamics | escalation_risk 4→4→2→0；goal_failure_risk 3、negotiation_open 5 不变 | 明确分工可降冲突，但两轮降至 0 偏乐观；没有错误降低 goal failure risk |

Ledger：t1 的集体提议被接受并保留 resolution 证据；t2 明确区分被评估角色的数据任务与环境角色的原型/展示任务；t2/t3 环境角色的行动保持 pending commitment，`completed_actions` 为空，没有把承诺写成完成。

可构造任务：

- T1：可在 t1–t3 形成公开历史 checkpoint；但场景当前 target IDs（anger、anxiety、trust、hostility）均不变，辨别力较弱。
- T2：可与 IA009/9301 的不同公开历史组成候选 pair，但两条都只有 3 轮，需要人工确认 shared observation 与差异是否足够有意义。
- T3：不可构造；任一 checkpoint 都没有至少 5 个后续回合，按设定不强行补窗口。
- T4：可作为 3 轮自然结束的在线互动样例，评价动作归属、协调和合理暂停。

## 4. 尚未解决的问题与停止决定

- IA003：时间片段与公开支付事件能工作，但模型进入“接受—确认—再确认”循环；现有 hard check 有时能发现，仍不能稳定产生完整自然样例。
- IA019：主要失败是模型把提案、询问或低依据补全写成正式股权/董事会事实。该问题直接改变责任、权利、行动可行性和任务答案，不能按“允许适度虚构”放行。
- 机器预检错位：两条 IA019 均机器通过但语义拒绝；IA009 两条语义认可却仅因长度被归入 short。扩量前必须修正筛选解释，而不是把 short 当失败或把 main pass 当人工质量。
- 状态灵敏度：数学与接线正确，但最好样例的 resolve 与 escalation risk 在两轮计划性承诺后变化偏快，需在独立样本上验证 calibration，而不是针对本例调数值。
- 当前没有三种场景各一条合格候选，因此停止生成；不启动 20×3 或 60 条。

最有信息量的下一项对照不是再跑整条轨迹，而是用保存的 IA003/IA019 失败 checkpoint 做小规模 turn-local component swap：固定公开历史与 ledger，分别替换 policy model 和 environment-response model，比较“无依据 consequential fact”“动作归属”“重复”三项。这样可区分是 agent policy、环境 response 还是共同模型能力限制；appraisal、确定性更新和场景保持不变。
