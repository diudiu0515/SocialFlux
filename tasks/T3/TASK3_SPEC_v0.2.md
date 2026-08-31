# EmoTree Task3 v0.2 任务定义

## 1. 任务目标

Task3（Counterfactual Choice Effect Prediction）检验模型能否在给定完整互动历史和当前选择情景后，同时推断多个候选行动对目标角色状态的即时与延迟影响。它不是选择“最好行动”的游戏任务，而是对所有候选行动进行反事实社会—情绪后果预测。

每个 Story World 固定 4 个 T3 semantic instances；每个实例生成 `text` 和 `text_video` 两个配对 variant，因此每 world 共 8 条物理记录。

## 2. 输入

模型可见：目标角色、完整历史、当前 decision scene、2–4 个候选行动，以及当前模态允许的媒体。作者 `effects`、`flags_set`、后续节点和结局不进入输入。

同一 semantic instance 的两个 variant 必须共享相同历史、decision、候选行动、目标状态与答案，只允许 `text_video` 增加对应媒体。

## 3. 预测单位

最小预测单位为：

```text
candidate option × target state × time horizon
```

每题包含 6–10 个状态。允许主观情绪、应对/动机、关系状态和任务相关风险，因为 T3 评估的是行动后果而非仅当前主观状态。

两个时间窗固定为：

- `immediate`：行动发生后至对方首个直接回应结束；
- `delayed`：直接回应之后，直到下一选择情景或当前故事路径结局。

时间窗描述的是人类需要预测的反事实范围，不向模型展示真实后续分支。

## 4. 方向标签与概率

每个时间窗输出：

```text
increase, similar, decrease, cannot_determine
```

四类概率必须位于 `[0,1]` 且总和为 1。`similar` 表示有足够证据判断变化接近零；`cannot_determine` 表示证据不足，二者不能互换。

模型不得另填自由 confidence。主 confidence 为最大概率；辅助诊断为 top-1/top-2 margin 与：

```text
entropy_confidence = 1 - H(P) / log(4)
```

## 5. 人类标注与 Ground Truth

每个 option/state/horizon 独立标注方向、四级 annotator confidence 与历史证据节点。正式 ground truth 是通过质检的人类标签未加权频数分布：

```text
P_human(k) = n_k / N
```

confidence 不给标签加权。作者 effects 仅用于创作和目标状态词汇筛选，不是 ground truth；因此未标注实例的 `ground_truth` 固定为 `null`。

## 6. 排序计算

不让模型额外填写含义模糊的“总体最好选项”。对具体 state/horizon，从方向分布计算可判断条件下的期望变化：

```text
increase=+1, similar=0, decrease=-1
expected_change = Σ P(k)value(k) / (1-P(cannot_determine))
```

再按 expected change 对选项排序。若 `cannot_determine=1`，该预测不参与排序。不同状态的正负价值可能不同，因此不得把所有状态压成未经定义的总福利排名。

## 7. 固定采样规则

```json
{
  "semantic_instances_per_world": 4,
  "required_variants": ["text", "text_video"],
  "physical_instances_per_world": 8,
  "selection_strategy": "round_robin_decision_then_history",
  "seed": 42,
  "require_distinct_decisions_when_available": true,
  "minimum_target_state_count": 6,
  "maximum_target_state_count": 10
}
```

先轮询不同 decision，再选择同一 decision 的不同历史，直到取得 4 个语义实例。不得复制完全相同的 decision/history 充数。数据划分必须以 `semantic_instance_id` 为单位，双模态 variant 不得跨 split。

## 8. 输出与标注 Schema

- 模型输出：`tasks/T3/model_output_schema_v0.2.json`；
- 人类标注：`tasks/T3/human_annotation_schema_v0.2.json`；
- 概率工具：`tasks/T3/t3_probability_utils.py`。

## 9. 指标

主要指标：方向分布交叉熵或 Brier score、方向 macro-F1、按状态与时间窗分层的准确率。排序指标：pairwise ranking accuracy 与 Kendall tau。校准指标：NLL、Brier、ECE。必须分别报告 immediate/delayed、text/text_video、状态类别和历史长度分层结果。

## 10. 质量门禁

- 每 world 恰好 4 个 semantic instances、8 条物理记录；
- 每个 semantic instance 恰好含两个 variant；
- 每题 2–4 个候选行动和 6–10 个状态；
- 两个时间窗、四类方向概率和证据字段完整；
- 模型输入无作者 effects、flags 或真实后续；
- `ground_truth=null` 直到独立人类标注完成。
