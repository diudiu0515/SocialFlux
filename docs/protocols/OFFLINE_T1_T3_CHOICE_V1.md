# Offline T1–T3 选择题协议 v1

本协议定义本轮开发题和后续主评测。环境、state、自然 rollout 与人工审核制度保持现有合同；旧概率分布接口保留用于复现。生成入口为 `python -m pipeline tasks --protocol choice`（别名 `python -m pipeline offline-build`），评测入口为 `python -m pipeline offline-eval`。T1/T2/T3 的既有 `answering.generate_answer` 按 `benchmark_version` 分发新协议。

## 判断对象与题型

题面使用自然语言，作者侧 `target_spec.target_state_ids` 绑定现有 ontology。`emotion` 对应 Emotion（人物情绪体验），`behavioral_disposition` 对应 Behavioral Disposition（此时采取某种行为的意愿），`relationship` 对应 Relationship（持有者对另一人的关系判断），`consequence_risk` 对应 Interaction Risk（指定不良事件在指定窗口内的风险）。不迁移或改名底层 state。

| Task | subtype | 主要判断 | 选项 |
|---|---|---|---|
| T1 | current_intensity | checkpoint 当前强度 | 既有五档 + 证据不足，共六项 |
| T1 | interval_change | 两个明确时刻间的方向 | 上升、基本不变、下降；确有必要时另列证据不足 |
| T1 | joint_change | 两变量的区间变化 | 四项，每项保存两变量判断 |
| T2 | history_comparison | 相同 ending 时 A/B 的指定状态 | A 较高、接近、B 较高；必要时另列证据不足 |
| T2 | expression_meaning | 相同表达在两种历史下的含义 | 四项，解释共同 ending 和各自历史 |
| T2 | joint_comparison | 两变量的 A/B 比较 | 四项，包含同步或基本不变的可能 |
| T3 | immediate_effect | 指定动作后的下一次环境回应 | 方向三分类，可另列证据不足 |
| T3 | delayed_effect | 指定动作后的延迟影响 | 同上 |
| T3 | action_comparison | 两候选行动在指定状态上的比较 | 三分类，可另列证据不足 |
| T3 | immediate_delayed | 即时—延迟组合 | 四项，分坐标保存判断 |

强度沿用 `tasks/T1/t1_probability_utils.py` 的 absent / mild / moderate / strong / very_strong / cannot_determine，不重新定义数值阈值。当前强度与变化幅度分别出题；本批不新增七档幅度题，未来可作为附加指标。`similar` 表示证据支持基本不变或接近，`cannot_determine` 表示无法判断，两者不能互相替换。安静、微笑或接受一个安排不自动等于内心情绪弱、信任恢复或风险下降。

T2 从同一背景与共享前史出发，保留原有事实，只改写记录在 `authoring.construction_source.edits` 的区间。共同 ending 仅存一份，避免两侧副本漂移。A/B 独立 restore 同一分叉 snapshot，经现有 state appraisal、确定性更新与 response 路径重放。受控 ending 的兼容性仍须语义审核，机器重放不等于人类认可其自然性。

T3 提供 2–4 个有真实取舍的候选行动。本批复用默认五轮窗口，定义为候选动作产生的即时回应加四轮自由续演；必要时配置不超过十轮。这个计数与现有 `branch_counterfactuals` 一致。记录实际观测轮数，不以自然提前结束补足窗口。候选分支可以并行执行。中断后仅从真实记录中的完整 before-snapshot 重放最后一步，再续演剩余轮次；不推算缺失 state，旧运行日志保留在独立目录。所有分支使用同一 snapshot、外生 event plan、continuation policy 和时间控制，回应与内生结果可以不同。基线为执行候选动作之前的 checkpoint。预测题不会把未来分支、数字 state 或作者答案送给被测模型。若以后问“更合适”，必须显式给出目标、约束、时间范围。

## 作答与评分

主协议：

```json
{"answer":"B"}
```

兼容去除首尾空白后的单个选项字母，或只有 answer 字段的 JSON；字母大小写归一。自由文本解释、代码围栏、多答案、重复 JSON 键、越界选项均记录格式失败，不通过正则从段落中猜选项，不为答题格式重试。调用失败与格式失败不混记，格式失败与可解析的语义错误不混记。所有计划评测题都留在主分母，包括失败题。JSON 仅多出解释等字段时，记录格式问题但仍对明确唯一的 answer 计分；不把格式不合规等同于语义答错。证据字段能独立解析时，即便 answer 缺失或越界，也可单独计算证据成绩。

独立证据诊断：

```json
{"answer":"B","evidence_ids":["A:t1","B:t2","ending"]}
```

证据用公开材料定位 ID；T2 同名轮次必须带 A:/B: 前缀。解释共同表达引用 ending，历史差异引用两侧历史。T3 的可见证据只能是行动前历史与候选行动，未来只属于作者依据。证据集合 precision/recall/F1 和答案准确率分别计算；答案正确但证据缺失、证据正确但答案错误都能单独记录。

评分报告包含 Task、Task/subtype、Task × 四类 state、单维／组合、模态、错误选项类型、证据诊断、格式失败、调用失败。组合的整题只计一分；变量坐标的准确率另列诊断，并标注其分母为可解析的组合题答案。一个组合题在 Task × state 中可进入两个维度，不能把这些行的样本量相加当总题数。

若公开证据无法可靠区分相邻强度／变化判断，`authoring.acceptable_answers` 保存全部可接受选项，并与组合题的相同变量保持一致；仍只要求模型选一个答案。

八类错项标签：主体／对象反转、外在表达替代状态、维度混淆、忽略历史、承诺当履约、即时／延迟混淆、忽略目标约束、无依据推断。它们是选项设计时的主要失误归因，不证明模型内部实际发生了该推理过程。

## 内部数据和边界

| 信息 | 复用／新增位置 |
|---|---|
| 唯一题号、Task、subtype | instance_id、task、subtype |
| 根场景、轨迹、T2 对 | story_id、metadata.source_trajectory_id、pair_id |
| 人物方向、变量、checkpoint、时间／风险事件 | target_spec |
| 完整公开输入、题干、选项 | input、question、options |
| 开发参考答案、证据、解释 | authoring.answer / evidence_ids / rationale |
| 错项、分维映射 | authoring.option_errors / option_variable_map |
| 来源路径／SHA、改写、重放记录 | authoring.construction_source |
| 历史依赖、非语言与历史的关系、审核状态 | authoring |
| 已冻结正式真值 | ground_truth；未审一律 null |

T3 的 `target_spec.checkpoint` 统一指行动前 t2，`prediction_window` 保存即时和延迟定义；行动比较另存 `comparison_horizon`，避免把整个风险事件窗口误当作风险判断时点。

跨时变量坐标写作 `emotion.anxiety@immediate`、`emotion.anxiety@delayed`，不会让后一个值覆盖前一个值。主调用采用公开投影的白名单；不传 task、state 路径、错误类型、作者依据或 private Persona。

开发评分明确标为 provisional_author_answers。正式 `--formal` 必须有人工批准、ground_truth、source admission；T2/T3 还需验证重放。视频还需通过媒体人工审核。已有人工标注只在轨迹版本、人物、变量、目标动作和窗口匹配时引用；同场景的旧标注不自动成为新题 GT。

## 多模态配对

按原轨迹公开 media_asset_id 查找现有资产，校验本地文件 SHA-256。T2 只复用未改写的共同前史视频，两侧引用同一文件；不把原 t2 视频挪给改写后的 t2。文本与视频条件的题干、选项、参考答案完全相同，保存 modality_pair_id 和每段视频对应的公开 evidence IDs。

正式评测需要审核视频线索是否支持题目。开发试答可显式使用 `video_frames`（四帧视觉采样），须记录不含音频和连续动态的限制；也支持 provider 已验证的 `native_video`，不做静默文本回退。原资产的触发类型和带状态含义的文件名不进入被测消息。

## 可复现命令

```bash
# 生成／断点续作（会调用现有 provider；未来只写作者侧 sources/）
python -m pipeline offline-build --config configs/offline_choice_dev60.json
# 从已完成产物导出完整题面和既有媒体配对，不重新调用模型
python -m pipeline offline-build --export-only --pair-media data/gpt50/experiment/multimodal_delivery_v1/online_multimodal/manifest.json
# 结构和公开边界检查
python -m pipeline offline-eval --items data/offline_t1_t3_dev60/items.jsonl --output /tmp/offline-check --check-only
# 小样本试答；结果目录必须是新的，避免混入上一次响应
python -m pipeline offline-eval --items data/offline_t1_t3_dev60/items.jsonl --output data/offline_t1_t3_dev60/smoke_text --per-task 2
# 证据模式单独试答
python -m pipeline offline-eval --items data/offline_t1_t3_dev60/items.jsonl --output data/offline_t1_t3_dev60/smoke_evidence --per-task 1 --diagnostic
# 仅计分，不调用模型
python -m pipeline offline-eval --items data/offline_t1_t3_dev60/items.jsonl --responses path/to/responses.jsonl --output path/to/scores
```

`--timeout` 可调整单次试答超时；另开目录重试会保留初次失败成绩，不覆盖或从分母中删除失败。

`replay_ready.items.jsonl` 单列具备所需回放的开发题；它仍不是人工批准的正式真值。`items.jsonl` 可以保留待回放候选，供题型与题面审核。

完整可读样例在 `data/offline_t1_t3_dev60/examples.md`；机器题库 `items.jsonl` 含作者信息，给被测端的独立文件是 `public.jsonl`。`sources/` 中保留源文件 SHA、原始出题、改写位置和私有分支，不应分发给被测端。`--author-only` 是显式设计草稿模式，不能冒充已完成分支验证。
