# SocialFlux-Eval 离线 T1–T3 · 动态社会理解与适应

2026-10-20 的设计版本为 `socialflux_offline_choice_v2`。评测模型能否结合互动历史与语言、表情、语气等可观察证据理解人物状态，并预测不同选择的后果。沿用现有四维 ontology、状态更新、环境分支与人工审核机制。本版新增能力标签、任务问题形式、受控编辑记录和时间比较合同。旧 v1 题库、生成配方和成绩保持原版本，不重新解释为 v2。

当前默认 Demo 已扩展为 [50 场景题库](../../tasks/examples/offline_scenarios_v2/examples.md)：每场景 T1/T2/T3 各 2 题，按材料挑选目标状态，四维在题库层面覆盖。旧 460 题退出默认批次，替换关系记录在 [replacement_ledger.json](../../tasks/examples/offline_scenarios_v2/replacement_ledger.json)。配置、真实 API 筛查与待核验部分见 [逐场景报告](../../reports/experiments/2026-10-20_scenarios_v2.md)；下述 24 题保留为题型示例，入口 `?bank=design-v2`。

[首批完整题面](../../tasks/examples/offline_design_v2/examples.md) · [三组字段记录](../../tasks/examples/offline_design_v2/records.jsonl) · [兼容运行器的题库](../../tasks/examples/offline_design_v2/items.jsonl) · [仅被测输入](../../tasks/examples/offline_design_v2/public.jsonl) · [旧题逐题审计](../../tasks/examples/offline_design_v2/legacy_reuse_audit.json)。网站入口为 `/offline-demo`，亦可 `/offline-review?bank=design-v2`。

## 能力与判断对象

| 被测能力 | 数据值 | 典型要求 |
|---|---|---|
| 情境证据整合 | situational_evidence_integration | 整合历史、当前语言和可观察表达，比较证据解释力，处理张力 |
| 多维状态区分 | multidimensional_state_distinction | 区分情绪、行动倾向、关系判断、互动风险及其不同步变化 |
| 跨时动态推理 | temporal_dynamics_reasoning | 理解积累、保持、反证、修复和行动的即时／延迟影响 |

每题一个主要能力，必要时辅助能力；两者不重复。四维是判断对象：Emotion=`emotion`，Behavioral Disposition=`behavioral_disposition`，Relationship=`relationship`，Interaction Risk=`consequence_risk`，不改底层变量名或数值机制。每个目标变量分别绑定主体、关系对象；风险必须另记事件和事件窗口。首批沿用一个题目共同的状态持有者与互动对方，逐变量绑定与其一致。

四维在题库层面覆盖，按材料选题，不强迫每个 checkpoint 四维齐全。统计主能力时每题只计一次；多维状态、辅助能力允许交叉归属，分组样本量不能相加当题数。

## 任务边界与生成模板

可执行模板及请求构造见 [offline_design.py](../../tasks/offline_design.py)，完整作者指令见 [offline_choice_author_v2.md](../../prompts/offline_choice_author_v2.md)。模板中的槽位来自公开事实和明确判断目标；不是把所有槽位直接显示给被测模型。

| 任务 | 问题形式 / subtype | 核心模板 |
|---|---|---|
| T1 社会状态理解 | current_state | 截至指定时间，某人的当前状态哪项最符合材料？ |
| T1 | interval_change | 相较明确起点，某人的指定状态如何变化？ |
| T1 | evidence_support | 哪项已发生的证据最支持或限制该状态判断？ |
| T1 | state_combination | 哪组状态判断最符合当前材料或明确区间？ |
| T2 历史敏感解释 | history_comparison | 共同表达时，A/B 哪段历史更支持某状态判断？ |
| T2 | expression_meaning | 相同微笑、沉默、接受或语气在两段历史中各有什么含义？ |
| T2 | joint_comparison | 哪组状态组合／合作原因比较符合各自历史？ |
| T2 | history_evidence | 综合早期事件与近期修复，哪些影响改变、哪些仍持续？ |
| T3 行动后果预测 | action_selection | 给定目标、约束和窗口，哪个行动更可能产生该结果？ |
| T3 | consequence_explanation | 相对行动前或另一个行动，哪组后果判断最有依据？ |

T1 的可见历史必须在 checkpoint 结束。变化题的比较起点和终点均可定位，关系题写清“谁对谁”。当前风险以已经存在的安排为条件；若比较新候选行动则属于 T3。持续求证、同样的授权阻断等正面证据可支持“基本不变”；没有变化证据本身不支持“不变”，需区分“证据不足”。

T2 的共同背景、角色、当前外部条件共用一份记录；两段历史差异集中在指定因素。共同焦点台词、表情和语气只存一个 `shared_ending`。原有“只能改最后一轮”的 v1 实现限制不适用于 v2，v2 可以编辑较早事件，但每项差异都必须保存 A 原文、B 编辑与定位。代码逐字段核对编辑日志。共同表达的自然性、因素是否真正受控仍需人工核验。正确项与干扰项要结合具体历史，而不是泛泛声称“历史重要”。允许部分状态有差异、其余相近。

T3 同起点提供 2–4 个合理且可执行的回应，行动在信息、承诺、责任、协商或风险处理上有实质差异。展示 `行动 1、行动 2……`，内部定位 `action_1`；答案仅用 A/B/C/D。即时窗口为动作及紧接的环境回应后；延迟默认含该即时回应的五次环境回应，最多十次，沿用原分支计数。`comparison` 必须区分相对行动前与行动间比较，`horizon` 与风险事件窗口分别保存。共同外部事件保持一致，行动引起的内生后果可不同。

优先用已有受控分支；作者侧的未来和隐藏状态不进入被测材料。只有一轮分支证据也能支持即时题，不能视为完整延迟窗口。证据不足单列 `needs_branch_evidence`；单次偶然结果不能写成必然因果规律。选择行动不等于无条件选择“最好”的行为：必须给出目标，例如提高进度可见性、降低特定失约风险或保留授权边界。

## 选项与难度

主回答只有：

```json
{"answer":"B"}
```

默认四选一；纯方向或历史比较可用增加／相近／降低三项，必要时单独加证据不足。v2 首批不使用原六档强度题；历史 v1 仍保持原格式。v2 的一个最佳答案必须可区分，存在相邻答案歧义则重写，不据私有数字强行定档。独立证据诊断入口沿用 v1，可选运行，不增加主回答字段。

每题围绕明确目标，多维题通过一个组合选项作答。错项优先反映忽略历史、表达替代状态、维度混淆、承诺当履约、即时／延迟混淆、主体对象反转、忽略约束、过度推断。各项长度、语气和具体程度接近，都有局部合理性；题干不先提示正确理论。答案位置在批次中均衡安排。

`design_difficulty=ordinary`：证据直接一致或后果关系明确。`hard`：分散证据、冲突线索、状态不同步、累积、反证、修复或跨时取舍，必须记录一句具体 `difficulty_reason`。单维也可 Hard，多维也可普通，例如 SFD2-016 的三个状态均由直接表达支持。`empirical_difficulty` 初始为 null，未来按具体模型运行另存 run_id、sample_size、accuracy；不可把设计 Hard 当成实测困难。

## 三组数据字段

`records.jsonl` 是三组物理字段导出；`items.jsonl` 保留现有运行器兼容布局，由 `grouped_record()` 映射，不要求模型输出任何数据侧标签。

| 分组 | 字段 | 含义／兼容位置 |
|---|---|---|
| evaluated_input | instance_id、modality、input、question、options | 材料、角色、时间定位、题干和选项；`input.history` / `history_a` / `history_b` / `shared_ending` / `candidate_actions` |
| annotation | answer、rationale、evidence_ids、counterevidence_ids | 作者答案、简短理由、支持及必要反证的公开定位；原布局 `authoring.*` |
| annotation | review_status、review_protocol、ground_truth | T1/T2 人工核验，T3 人工标注；未审 GT 为 null |
| annotation | generation_source、construction_source、history_control、branch_evidence | 生成来源／SHA、原始来源、历史差异与状态核验、分支窗口完整性 |
| annotation | option_errors、option_variable_map | 错项主要失误与组合的逐变量判断，仅供分析 |
| analysis | task、question_form、primary_capability、auxiliary_capabilities | 任务与能力，不是判断对象 |
| analysis | state_bindings、target_spec | 每个变量的主体／对象、checkpoint、区间、风险事件／窗口和行动比较 |
| analysis | design_difficulty、difficulty_reason、empirical_difficulty | 设计与实测难度分开 |
| analysis | modality、story_id、history_pair_id、modality_pair_id、branch_ids、source | 模态、来源场景、配对／分支与旧题关联 |

`public_instance()` 用白名单导出被测输入。`answer_prompt()` 不加入任务、能力、难度、作者标注或未来。`evidence_ids` 和 `counterevidence_ids` 只能引用公开片段；私有分支证据另存在作者来源中。

[JSON Schema](../../schemas/offline_choice_item_v2.schema.json) 检查字段形状；`validate_item()` 同时检查跨字段的主体、可见证据、T2 编辑、T3 比较与窗口。Schema 不能替代证据含义和历史因素控制的人工核验。

## 首批示例与旧题复用

首批 24 题，T1/T2/T3 各 8；每个任务四维覆盖。答案位置 A/B/C/D 各 6。其中 12 题改写自 11 道旧题（SFO-001 同时提供状态判断与证据支持题），另 12 题为老师／小陈的受控写作示例。9 普通、15 Hard；只是设计标签，全部尚未人工审核。

SFD2-001—012 保留旧 scenario、trajectory、T2 编辑／回放和 T3 分支引用，当前工作区均能验证来源 SHA。改题后重新待审，不搬用旧 human GT。SFD2-013—024 不是实际环境 rollout；T2 状态核验与 T3 分支均显式 pending。`replay_ready.items.jsonl` 仅收录前 12 题，仍是开发数据，不是正式真值。T1 写作示例也没有冒充通过来源 Gate。

460 道旧题的设计审计结果：

| 处置 | 题数 | 含义 |
|---|---:|---|
| 已用于新版改写 | 11 | 产生 12 道新版示例，仍待人工审核 |
| 补充标签、复核后可作复用候选 | 378 | 仅通过本次结构性筛查，未逐题完成语义批准 |
| 需重写 | 67 | 强度档位／相邻答案／解释干扰项问题 |
| 需补充分支证据 | 4 | 原轨道场景 T3，不得冒充完整延迟验证 |

这些处置是早期助手结构筛查，`formal_usable=false`；不是“378 道已经可正式用”。后续按新版设计进行的实际 API 逐题适配核验见 [旧题迁移报告](../../reports/experiments/2026-10-20_legacy_task_migration.md)，机器建议、尚未完成和助手发现的争议分别保留。旧 60 题中证据不足占比偏高，继续保留用于检验过度推断的价值，但不应主导新版。新增初批包含“不变”和“证据不足”的不同选项，保留同向或相近组合，不把状态不同步设为总是正确。

## 多模态与统计

### 逐字台词 talking-head 制作

新版 300 题的环境角色台词去重为 150 个节点：50 个 t1、50 个 t2、50 个 T2 共同结尾。`offline.talking_head` 按原语言保留完整台词，长句无损拆成 241 段，分段连接必须逐字还原原文。T2 的相同前史和共同结尾分别复用同一文件，候选行动的未来台词不进入题面视频。生成请求只发送公开台词、公开表情和虚构人物参考，不发送答案、私有状态或未来分支。

此队列使用独立的 `offline_talking_head_exact_v1` 提示；旧英文压缩渲染流程保持原版本。49 个场景有现成人物参考，GPT50_036 先生成首段作为新参考，再用于同场景后续片段。全部产物、provider state、原文台词表和题目版本绑定保存在 `data/offline_talking_head_v1/<题库SHA前16位>/`，提交失败和已提交 task ID 均保留，可续查下载。

```bash
# 准备和状态检查不调用视频 API
python -m offline.talking_head --phase prepare
python -m offline.talking_head --phase status --manifest data/offline_talking_head_v1/c1d1f3fd60e94e0c/manifest.json
# 经授权后，显式提交；可用 --request-id 先选一段样片
python -m offline.talking_head --phase run --manifest data/offline_talking_head_v1/c1d1f3fd60e94e0c/manifest.json --submit-new --workers 4
# 全部节点完成后发布到开发审核页；未完成时保留既有配对
python -m offline.talking_head --phase publish --manifest data/offline_talking_head_v1/c1d1f3fd60e94e0c/manifest.json
```

生成完成只代表视频文件和音轨存在。原文发音、逐字完整性、口型、人物一致性及表情仍需审核；网站保留待审标记，不转为正式人工通过。帧图传输仍只包含视觉信息。当前只完成请求准备，实际提交须以 provider state 为准，不能把清单数量当作生成数量。

### 已有非语言素材配对

当前 50 场景、300 题的已有非语言视频配对由 `scripts.match_offline_multimodal` 独立刷新，不重新出题或覆盖 oracle 参考。逐项核对冻结轨迹 SHA、公开台词、表情、公开事件与历史轮次，再按原 `media_asset_id` 和视频 SHA 绑定。2026-10-21 核对为 270 对（T1/T2/T3 各 90 对）、45 段视频；GPT50_005、020、034、036、039 的对应素材尚未生成，涉及 30 题。所有已匹配视频仅覆盖 t1；T2 对应 A:t1/B:t1，共同结尾未匹配视频。此条件是文字加前史非语言 cue，不是朗读当前台词的 talking head。

`pairing_report.json` 保存逐题覆盖、缺口、当前题库及媒体清单 SHA。`media.json` 包含原视频及每段 0.25/1.25/2.25/3.25 秒的四张帧图，帧图缓存位于 `data/offline_multimodal_frames/`。帧图传输只评测视觉信息，不包含音轨与语音韵律；所有素材仍待人工审核。

```bash
python -m scripts.match_offline_multimodal
python -m pipeline offline-eval --items tasks/examples/offline_scenarios_v2/paired.items.jsonl --media-manifest tasks/examples/offline_scenarios_v2/media.json --transport video_frames --output /tmp/offline-media-check --check-only
```

第一条命令先暂存配对结果并备份旧配对文件，保留当前题目、答案和审核状态；第二条在零 provider 调用下校验 540 个条件、270 个视频条件的绑定及视频/帧图 SHA。新版题库发布后可重新运行这两条命令。

早期 24 题型示例另为其中 12 道旧材料改写题保留文字／文字+视频配对，共 24 个条件，沿用已有素材、相同题干与相同答案并校验资产 SHA。T2 视频只覆盖未改写的共同前史；共同焦点台词／表情／语气文字保持一致，但本批没有匹配的焦点音视频，不宣称已验证相同结尾视频或语音韵律。老师／小陈示例没有视频，明确记录素材缺口，不拿无关视频充数。生成脚本在没有原工作媒体清单的 checkout 中仍可构建文本集，配对报告如实记录缺口。

评分沿用整题准确率、格式失败、调用失败、错项类型、组合诊断及配对一致性，新增主要能力、辅助能力、设计难度、总体状态维度和任务×主要能力分组。仍只统计实际作答；本次结构测试不算模型成绩。

## 运行与复现

```bash
# 生成确定性、可审阅的初批示例与旧题审计；不调用模型
python -m scripts.build_offline_design_v2
# 原评测入口可直接验证和运行 v2
python -m pipeline offline-eval --items tasks/examples/offline_design_v2/items.jsonl --output /tmp/socialflux-v2-check --check-only
# 合同、旧版兼容、模型输入边界与网页数据检查
python -m unittest tests.test_offline_design tests.test_offline_choice web.tests.test_offline_review -v
```

需要模型辅助出题时，先冻结允许的公开材料和作者来源，再调用：

```python
from tasks.offline_design import generation_request, author_item
request = generation_request(
    'T1', 'evidence_support', public_input,
    primary_capability='situational_evidence_integration',
    difficulty='hard', author_context=frozen_author_sources,
)
proposal = author_item(provider, request)
```

该入口使用注册且校验 SHA 的 v2 prompt，强制输入、题型、主要能力和设计难度不漂移，并保持未审状态。`frozen_author_sources` 必须包含 `construction_source`、`replay_status`，T2 另含 `history_control`，T3 另含 `branch_evidence`；生成器拒绝改动这些来源记录，输出仍需核验。旧 `offline-build` 的批量生成配方固定为 v1，用于旧实验复现，不会静默替换。

历史公开材料初稿入口为 `python -m offline.scenario_v2`，使用 [场景生成模板](../../prompts/offline_scenario_author_v2.md)。它只生成公开材料下的参考答案，不构成上帝视角答案。原稿、失败调用与旧人工标签均不能替代新版审核。

上帝视角制作入口为 `python -m offline.oracle --run <冻结目录> --phase author`，随后运行 `--phase review`、`--phase blind`。当前批次使用 `python -m offline.oracle_release` 发布：要求 300 题全部完成三项检查，并核验两处受控历史修订、解释中的选项字母和未改动前史的媒体绑定。旧 `--phase publish` 仅适用于公开材料完全不变的批次，不用于本次修订发布。失败题组由 `python -m offline.oracle_revision` 在新修订记录中处理；机器争议保留，不自动转为通过。

本次 300 题、50 组 T2 回放与两类独立检查均已完成；138 题有机器争议，162 题暂未被标记，全部仍待人工审核。完整指标及逐题问题见[上帝视角与标注报告](../../reports/experiments/2026-10-20_oracle_reference_and_annotation.md)。

- T1：完整公开历史截至题目 checkpoint，配套实际初始状态、各轮状态和判定依据；不使用 checkpoint 后的未来倒推当前答案。
- T2：从同一私有快照分别执行 A/B 行动，冻结同一结尾台词与可见表达。缺省的表情字段只补空值以符合环境接口，不新增线索。原事实轨迹的 t2 回应不冒充受控共同结尾。
- T3：读取同起点、同外部条件的候选行动分支和题目指定窗口。一个行动的一条实现轨迹只能提供该实现的证据，不能证明普遍概率或必然结果。
- 目标变量必须存在于实际私有记录。`authoring.oracle_reference` 保存机器候选、私有证据编号、解释、独立核验与证据包哈希；`ground_truth` 仍由人工审核产生。
- `public_instance` 是被测模型和人类盲答共享的唯一输入投影，不包含私有状态、机器答案、能力标签、设计难度或来源审核结论。

### 人类盲答与 GT 工作流

网站 `/offline-annotation` 为服务器持久化的采集入口；`/offline-demo` 保留题库浏览与制作侧检查用途，浏览者不能把看过答案后的作答计为首次盲答。

1. 以固定标注人 ID 分配完整场景组，当前采集固定文字条件。可以分配一个场景的 6 题，也可一次分配全部场景；模态不能在作答途中切换。
2. 本次分配全部盲答提交后才能解锁任意私有证据。盲答保存题目哈希、版本、模态、时间与原答案，之后不能覆盖。
3. 查看题目时点内的全部相关对话、私有状态、A/B 或分支证据，完成独立 GT 初判。全部初判提交后，才开放机器建议，防止同场景的机器答案影响未提交初判。
4. 对照机器建议完成最终人工审核，并明确本人审核声明。原盲答、独立初判、最终审核分别保存和导出；任何一步都不会自动改写正式题库。
5. 两名不同审核人的一致判断形成待准入 GT 候选；存在分歧或题目质量问题时留待裁决。给某位参与者计算人类基线时，排除该参与者自己的 GT，至少需要两名其他审核人的一致标签；无独立 GT 时准确率为 `null`。

当前是受控本地采集，标注人身份由本人声明，不提供外部身份核验。服务器保留跨会话、跨题库版本的同场景接触记录；重复测试或声明已经看过私有信息者可以参与 GT 审核，但不计入首次盲答基线。浏览器测试使用临时目录，不进入真实人工标注统计。
