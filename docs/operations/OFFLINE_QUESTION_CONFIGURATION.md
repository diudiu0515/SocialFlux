# Offline 题库与人工审核 Demo 配置说明

> 2026-10-22 更新：新领取任务已改为分阶段标注。T1–3 先完成整组盲答，再开放私有 state / environment 与机器答案供人确认 GT；T4 为 50 条轨迹的五维评分。本文有关“视频审核必填、题目选填、52 段视频”的配置只适用于第 2 版历史审核会话。当前流程见 [人工标注与 GT](ANNOTATION_DEMO.md)。


更新日期：2026-10-21。适用题库版本：`socialflux_offline_choice_v2`；适用线上 Demo：Sites 第 2 版。

当前完整题库有 **50 个场景、300 道题**，每场景 T1、T2、T3 各 2 题。人工答题与视频审核 Demo 收录其中有现成视频的 **45 个场景、270 道题、52 段视频**。参与者按场景连续看视频，视频审核必填，题目作答选填。

本配置覆盖 Offline T1–T3。任务语义和生成约束见 [v2 协议](../protocols/OFFLINE_T1_T3_CHOICE_V2.md)，网站访问、发布和运维见 [Demo 操作说明](ANNOTATION_DEMO.md)。

## 题库与发布范围

| 数据范围 | 场景数 | 题目或条件记录数 | T1 / T2 / T3 | 用途 |
|---|---:|---:|---|---|
| 完整 v2 题库 `items.jsonl` | 50 | 300 道逻辑题目 | 100 / 100 / 100 | 当前完整题目定义，场景为 GPT50_001–050 |
| 当前人工审核包 `multimodal.json` | 45 | 270 道逻辑题目 | 90 / 90 / 90 | 与 52 段视频一起查看、答题和审核 |
| 已有非语言视频评测配对 `paired.items.jsonl` | 45 | 540 条条件记录，对应 270 道逻辑题目 | 每个任务 90 题，各有 text 与 text+video 两个条件 | 保留相同题目的模态配对；此配对清单尚未纳入 7 段英文共同回应 |
| 旧六题 Demo `questions.json` | 1 | 6 道逻辑题目 | 2 / 2 / 2 | 仅供原会话恢复，场景为 GPT50_001 |

完整题库保留全部 300 题。未进入当前视频审核包的 30 题来自 GPT50_005、GPT50_020、GPT50_034、GPT50_036、GPT50_039，这 5 个场景没有本次选定的视频资产。

完整题库与当前审核包内的公开题目均保留原始 `modality: "text"`。审核页面额外关联视频，记录导出使用 `modality: "text+video_review"`；它表示同屏素材审核，不能直接并入随机分配的文字／视频条件成绩。

## 每个场景的题目组成

| 任务 | 判断内容 | 每场景题数 | 参与者看到的材料 | 本批时间定位 |
|---|---|---:|---|---|
| T1 社会状态理解 | 根据已发生的对话，判断当前状态、变化或支持证据 | 2 | 背景、角色、目标人物、2 轮 `history`、题干、4 个选项 | `checkpoint=t2`，公开历史截至 t2 |
| T2 历史敏感解释 | 比较不同历史下，相同表达的含义与人物状态 | 2 | 共同背景与角色、各 2 轮 `history_a` / `history_b`、一份 `shared_ending`、题干、4 个选项 | `checkpoint=ending`，A/B 共用结尾台词及可见表达 |
| T3 行动后果预测 | 在明确目标与约束下，预测候选行动的后果 | 2 | 背景、角色、目标人物、2 轮 `history`、2 个 `candidate_actions`、题干、4 个选项 | 起点为 `checkpoint=t2`，后果按题目指定窗口判断 |

T3 的 **2 个候选行动**是待比较的行为；**4 个答案选项**是对行动或后果的不同判断。候选行动数与答案选项数分别配置。未来分支、未来私有状态和作者参考答案不进入公开题面。

场景与题目编号保持固定。例如 GPT50_001 包含：

```text
SFV2-001-T1-01    SFV2-001-T1-02
SFV2-001-T2-01    SFV2-001-T2-02
SFV2-001-T3-01    SFV2-001-T3-02
```

`001` 对应场景序号，`T1/T2/T3` 对应任务，末尾 `01/02` 表示该场景该任务的第几道题。场景内的两个位置不固定对应同一 subtype；具体题型以原始条目的 `subtype` 为准。

### 子题型数量

| 任务 | `subtype` | 问题形式 | 完整题库 | 当前 Demo |
|---|---|---|---:|---:|
| T1 | `current_state` | 判断当前状态 | 26 | 23 |
| T1 | `interval_change` | 比较明确区间内的状态变化 | 26 | 23 |
| T1 | `evidence_support` | 选择最支持或限制状态判断的已发生证据 | 25 | 23 |
| T1 | `state_combination` | 判断一组状态组合 | 23 | 21 |
| T2 | `history_comparison` | 比较 A/B 历史对状态判断的支持 | 34 | 32 |
| T2 | `expression_meaning` | 解释相同表达在不同历史下的含义 | 27 | 25 |
| T2 | `joint_comparison` | 比较状态组合或合作原因 | 20 | 16 |
| T2 | `history_evidence` | 判断早期事件与近期修复的持续影响 | 19 | 17 |
| T3 | `action_selection` | 根据目标、约束及窗口选择行动判断 | 50 | 45 |
| T3 | `consequence_explanation` | 解释相对行动前或另一行动的后果 | 50 | 45 |
| 合计 | — | — | **300** | **270** |

### T3 后果窗口

| `target_spec.horizon` | 含义 | 完整题库 | 当前 Demo |
|---|---|---:|---:|
| `immediate` | 行动及紧接的下一次环境回应之后 | 88 | 80 |
| `delayed` | 题目指定的延迟窗口 | 10 | 9 |
| `immediate_delayed` | 同时比较即时与延迟后果 | 2 | 1 |

本批所有 T3 的 `delayed_horizon` 均配置为 5，计数包含紧接行动的第一次环境回应；它不表示每道 T3 都考延迟后果。具体比较基准由 `comparison` 指定，风险事件和风险窗口另存 `risk_event`、`risk_window`，不能仅从通用轮数推断。

## 能力维度与难度配置

每题只有一个主要能力，辅助能力允许交叉归属。以下主要能力题数可以相加得到总题数。

| 主要能力 | `analysis.primary_capability` | 完整题库 | 当前 Demo |
|---|---|---:|---:|
| 情境证据整合 | `situational_evidence_integration` | 167 | 151 |
| 跨时动态推理 | `temporal_dynamics_reasoning` | 84 | 75 |
| 多维状态区分 | `multidimensional_state_distinction` | 49 | 44 |

状态维度是题目判断的对象，与主要能力分别统计。下表按每题涉及的 `target_spec.target_state_ids` family 去重计数；同一题可以覆盖多个维度，不能把各行相加当作总题数。

| 状态维度 | 字段前缀 | 完整题库覆盖题数 | 当前 Demo 覆盖题数 |
|---|---|---:|---:|
| 行动倾向 | `behavioral_disposition` | 127 | 117 |
| 关系判断 | `relationship` | 124 | 109 |
| 互动风险 | `consequence_risk` | 56 | 50 |
| 情绪 | `emotion` | 11 | 11 |

完整题库有 282 道单 family 题、18 道双 family 题；当前 Demo 分别为 253 道与 17 道。题目按材料选择判断对象，当前四维覆盖并不均衡，也未要求每个场景四维各出一题。

| 设计难度 | `analysis.design_difficulty` | 完整题库 | 当前 Demo |
|---|---|---:|---:|
| 普通 | `ordinary` | 230 | 209 |
| Hard | `hard` | 70 | 61 |

所有题目的 `empirical_difficulty` 目前均为 `null`。Hard 表示设计难度，不表示已经测得模型或人工的低正确率。能力、难度、判断目标和私有状态字段不进入 `public_instance()` 的公开输入。

## 视频和语言配置

| 场景组 | 场景编号 | 场景数 | Demo 题数 | 非语言前史视频 | 英文共同回应视频 |
|---|---|---:|---:|---:|---:|
| 两类视频均有 | GPT50_001、002、003、004、006、008、009 | 7 | 42 | 7 | 7 |
| 只有非语言前史视频 | GPT50_001–050 中除上行及缺视频组之外的场景 | 38 | 228 | 38 | 0 |
| 缺少本次选定视频 | GPT50_005、020、034、036、039 | 5 | 0；原题库保留 30 题 | 0 | 0 |
| 本次 Demo 合计 | 45 个场景 | **45** | **270** | **45** | **7** |

以下语言配置指当前 `scenarios-v2` 题库和新导出的英文包；已分配的历史标注会话按冻结材料恢复。语言按内容分别配置：

| 内容 | 当前配置 |
|---|---|
| 公开题干、选项与对话材料 | 统一英文；人物、题目 ID、答案和难度标记保持不变 |
| 审核界面 | 中文 |
| 7 段 talking-head 的语音与 `spoken_text` | 英文；当前 `source_text` 使用与音频一致的英文台词 |
| 45 段非语言前史视频 | 用于表情与动作线索，不承担题面对白配音 |

英文台词映射在 [offline_talking_preview_en_v1.json](../../configs/offline_talking_preview_en_v1.json)。GPT50_006 复用对应英文轨迹的原句，其余为受控共同回应的英文映射。7 段样片使用独立虚构人物，完整前史的人物连续性尚未覆盖。

### 视频对应的证据位置

| 视频类型 | 对应题目 | `evidence_ids` | 视频与题目绑定数 |
|---|---|---|---:|
| 非语言前史 | 45 场景的全部 T1 与 T3 | `t1` | 180 |
| 同一非语言前史 | 45 场景的全部 T2，A/B 复用同一文件 | `A:t1`、`B:t1` | 90 |
| 英文共同回应 | 7 场景的两道 T2 | `ending` | 14 |
| 合计 | — | — | **284** |

**52 是去重后的视频文件数，284 是视频与题目的关联数，270 是独立题目数。** 每个非语言视频关联同场景 6 道题，每个英文共同回应关联同场景 2 道 T2。重复引用不重复要求人工审核。

例如 GPT50_001 的 `video-5b7aa98738b14bb4` 对应该场景全部 6 道题的 t1 线索；`video-21d0c33a6d14d135` 只对应 `SFV2-001-T2-01` 和 `SFV2-001-T2-02` 的 `ending`。在这两道 T2 中可以分别查看前史表情和英文共同回应。

当前非语言视频只覆盖 t1，英文样片只覆盖所选 7 场景的共同结尾。完整前史逐字对白、其他场景共同结尾的英文配音尚未齐全；进入 Demo 不代表整道题已有完整对白视频。当前评测用 `media.json` / `paired.items.jsonl` 仍是非语言前史条件，不能把 Demo 新增的英文视频视作已经进入该评测条件。

## 配置字段与公开边界

原始题目见 [items.jsonl](../../tasks/examples/offline_scenarios_v2/items.jsonl)，公开审核包见 [multimodal.json](../../web/participant_demo/data/multimodal.json)。

| 原始题目字段 | 含义 | 是否属于公开题目投影 |
|---|---|---|
| `instance_id` | 固定题号 | 是 |
| `modality` | 原题输入模态，本批为 `text` | 是 |
| `input` | 背景、角色、目标人物及对应任务材料 | 是，经白名单处理 |
| `question`、`options` | 题干及 A/B/C/D 四个选项 | 是 |
| `task`、`subtype`、`story_id` | 任务、子题型与来源场景 | 否；发布包另保留任务／场景索引用于组织页面 |
| `target_spec` | 目标状态、主体、对象、checkpoint、比较基准、风险和时间窗口 | 否 |
| `analysis` | 主要／辅助能力、状态绑定、设计／实测难度 | 否 |
| `authoring` | 作者参考、证据、来源、回放和机器核验信息 | 否 |
| `ground_truth`、`label_status` | 正式标签及审核状态 | 否 |

`public_instance()` 顶层只输出 `instance_id`、`modality`、`input`、`question`、`options` 五个字段。协议允许的模型主回答格式为 `{"answer":"B"}`；这里的 B 只是格式示例。

公开审核包的组织结构如下：

| 包内字段 | 配置作用 |
|---|---|
| `release`、`source_bank_sha256`、`dataset_sha256` | 标识审核版本及来源题库 |
| `items[]` | 保存单题 SHA、`scene_id`、`task` 和 `public` 题面 |
| `scenes[]` | 用 `scene_id` 关联 `question_ids` 与 `video_ids` |
| `videos[]` | 保存 `asset_id`、文件 SHA、URL、场景、类型、说话人、台词、公开表达及题目绑定 |
| `videos[].bindings[]` | 每项为 `instance_id` 与 `evidence_ids`，明确视频覆盖到哪道题的哪个片段 |

视频 URL 使用 `/media/<完整视频SHA>.mp4`，`asset_id` 使用 `video-<SHA前16位>`。前端按场景组织，场景内先列前史视频，再列英文共同回应。

## 人工答题和视频审核配置

研究端 `/offline-annotation` 自 2026-10-22 起新任务默认使用文字＋视频；只分配已通过题目绑定和文件 SHA 核验的 45 个场景。题面、视频及证据位置在领取时冻结，旧文字会话继续使用原条件。它使用当前 `media.json` 注册的非语言前史视频，不混入下述 Demo 独立的英文共同回应样片。`/offline-demo` / `/offline-review` 也默认展开配对视频。50 场景逐项覆盖见 [视频清单 CSV](../../reports/experiments/2026-10-22_offline_video_coverage.csv)。

独立参与者 Demo 的新任务为 `dataset.kind=multimodal_review`。每份新会话包含同一批 45 个场景和 52 段视频，目前没有随机抽题或分组分配；默认按场景连续审核，也可切换场景或筛选未审完、需修改或待判断的内容。

### 题目作答

记录位于 `answers[instance_id]`，整个题目作答部分选填。

| 字段 | 允许值 | 提交要求 |
|---|---|---|
| `answer` | `A` / `B` / `C` / `D`，或未选择 `null` | 可跳过题目 |
| `confidence` | `high` 很有把握、`medium` 比较有把握、`low` 不太确定 | 选了答案后必填 |
| `rationale` | 自由文本，最多 2000 字符 | 选填 |
| `issue` | `none`、`unclear`、`multiple`、`insufficient` | 分别表示无问题、表述不清、多个选项合理、材料不足；默认 `none` |

### 视频审核

记录位于 `media_reviews[asset_id]`；保存接口中的同一字段名为 `mediaReviews`。

| 字段 | 允许值或内容 | 提交要求 |
|---|---|---|
| `verdict` | `usable` 可用、`revise` 需修改、`unusable` 不可用、`uncertain` 无法判断 | 52 段逐段必填 |
| `issues` | 问题类型数组，可多选 | 需修改或不可用时，至少选一项或填写非空说明 |
| `note` | 修改建议或判断依据，最多 2000 字符 | 可与问题类型配合使用 |
| `watched` | 布尔值 | 需为 true，或在问题类型中记录 `playback` |

问题类型对应关系：

| 值 | 界面含义 |
|---|---|
| `dialogue` | 台词不匹配、多读或漏读 |
| `lip_sync` | 口型不同步 |
| `expression` | 表情与公开线索不符 |
| `unnatural` | 说话或动作不自然 |
| `picture` | 画面或人物异常 |
| `audio` | 音质或语音问题 |
| `context` | 与场景不匹配或引入额外信息 |
| `playback` | 无法播放 |
| `other` | 其他问题 |

最终提交要求全部视频审核有效、已选答案都有把握程度，并勾选独立完成确认。标记 `usable` 的视频不能同时保留问题勾选。正常播放结束会自动勾选已查看，也允许手动确认；这项记录是参与者确认或浏览器事件，不是独立验证的观看证明。

修改约 1.4 秒后自动保存，切换场景前也会保存。云端使用 `revision` 防止不同页面相互覆盖，本机备份未保存输入；提交后锁定。导出格式为 `socialflux_multimodal_review_v1`，将 `answers`、`media_reviews`、`item_hashes` 和 `media_hashes` 分开保存。

当前 300 道原题均为 `pending_human_annotation`，`ground_truth=null`。视频可用性审核、题目作答和正式 GT 是不同记录；本 Demo 导出固定 `formal_ground_truth=false`，提交审核不会自动写入正式题库标签。

## 冻结版本与维护位置

| 配置对象 | 文件或版本 |
|---|---|
| 当前完整题库 | `tasks/examples/offline_scenarios_v2/items.jsonl` |
| 非语言评测配对 | `tasks/examples/offline_scenarios_v2/paired.items.jsonl`、`media.json`、`pairing_report.json` |
| 英文台词映射 | `configs/offline_talking_preview_en_v1.json` |
| 选定英文样片 | `data/offline_talking_head_en_v1/fa64c939b7653fc1/preview_selection.json`、`manifest.json`、`completed_nodes.json` |
| 历史冻结审核公开包 | `web/participant_demo/data/multimodal.json` |
| 新版英文公开包 | `web/participant_demo/data/multimodal-en.json`，`offline-multimodal-review-20261022-en-v1`；尚未替换已发布站点 |
| 当前审核 release | `offline-multimodal-review-20261021-v1` |
| 旧六题 release | `demo-2026-10-21`，文件为 `web/participant_demo/data/questions.json` |
| 公开包导出与绑定核验 | [export_participant_multimodal.py](../../scripts/export_participant_multimodal.py) |
| 答题与审核校验规则 | [protocol.ts](../../web/participant_demo/lib/protocol.ts) |
| 版本选择、保存、提交与导出 | [store.ts](../../web/participant_demo/lib/store.ts) |

本次源题库文件 SHA-256：

```text
c1d1f3fd60e94e0c09e1b6ecae4187cd3ae98a7b32e836204749d7de559deee8
```

本次 Demo 的 `dataset_sha256`：

```text
5912f0b36db69f2a3d6f12fd602d604333f318f41c79dc9cbe9ebaf85a873e27
```

修改题干、选项、台词或视频绑定后，应重新导出并核验源题库、逐题及视频 SHA；发布新审核版本时保留旧会话所需的冻结包和版本选择规则。恢复码始终恢复原版本：旧六题记录继续要求六题全答，重新领取的任务进入综合审核。

复现本次公开包的命令如下，只读取和导出现有材料，不调用视频生成接口：

```sh
python -m scripts.export_participant_multimodal \
  --site-dir web/participant_demo \
  --report build/participant_multimodal_export.json
```

该导出器当前校验固定的 270 题、45 个非语言视频及 7 个英文样片。扩大范围时需同步调整选择配置、绑定核验、发布包和旧会话兼容逻辑；不能仅修改页面上显示的题数。

2026-10-22 英文迁移已完成：当前 300 题及其来源、回放和参考说明均为英文。Hard 为 T1 10/100、T2 36/100、T3 24/100；这仍是设计难度，实测难度尚未填写。数值、答案、证据 ID 和难度标记保持不变，翻译语义等价性仍待人工复核。核验记录见 [英文迁移报告](../../data/english_migration_20261022/release_report.json)。
