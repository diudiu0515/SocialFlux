# EmoTree Benchmark 任务定义 v0.2

## 1. 总体目标

EmoTree 评测模型能否在带选择、后果与分支汇合的双人多轮互动中追踪潜在状态，并预测候选行动的反事实影响。Story World 是题库原材料，模型实际评测单位是独立 Benchmark Instance。

作者 `effects` 只用于剧情设计，不是 ground truth。正式标签必须来自独立人类标注并保存分布。

## 2. 三个任务

- T1：Longitudinal Subjective State Tracking；
- T2：History-sensitive Merge Test；
- T3：Counterfactual Choice Effect Prediction。

第一篇以 T2 为中心，T1 提供状态追踪基础，T3 检验追踪错误是否传播到行动效果预测。

# 3. T1：Longitudinal Subjective State Tracking v0.2

## 3.1 T1 测什么

给定目标角色、至少 8 轮完整历史和当前 checkpoint，模型预测角色当前潜在主观状态，以及这些状态相对指定历史锚点的变化。

T1 判断潜在体验，不等同于当前台词的表面情绪分类。

## 3.2 T1 当前包含的状态

T1-A 主任务包含：

- `emotion`：难过、愤怒、焦虑、内疚等；
- `motivation/coping`：决心、坚定表达、忍耐、策略耐心等；
- `relationship`：信任、敌意感知、关系安全等。

第一版 T1 不标注毕业风险、职业风险、用户安全风险等客观风险。风险后续作为 T1-B Situational Risk Appraisal 或 T3 后果维度单独处理。

## 3.3 历史要求

正式 T1 Instance 必须满足：

- `history_view = full_history`；
- 当前 checkpoint 之前至少 8 个不同轮次；
- 推荐历史长度 8–20 轮；
- 至少包含一个影响当前状态的早期选择；
- 明确 `change_anchor_node_id`；
- 记录关键证据节点和最远因果距离。

## 3.3.1 每个 World 的固定实例数

每个 Story World 固定抽取 5 个 T1 语义实例。每个语义实例必须生成两个配对 variant：

```text
text
text_video
```

因此：

```text
每个 world = 5 个 semantic instances = 10 条物理 JSONL records
```

两种模态共享同一个 `semantic_instance_id`，分别使用不同 `instance_id` 和 `variant_id`。数据划分、抽样和显著性分析以 semantic instance 为配对单位，不能把 10 条记录当成 10 道独立题。

五个语义实例采用 `round_robin_checkpoint_then_path`：先尽量覆盖不同 checkpoint，再从已有 checkpoint 选择不同历史路径。若一个 world 无法提供 5 条满足至少 8 轮历史的候选路径，则构建失败，不允许用重复实例补足。

每条实例保存：

```json
{
  "history_start_round": 1,
  "history_end_round": 17,
  "history_length_rounds": 17,
  "checkpoint_round": 18,
  "change_anchor_node_id": "D02",
  "key_evidence_node_ids": ["D01", "D02"],
  "causal_distance_rounds": 12,
  "decision_count_in_history": 2,
  "merge_count_in_history": 1
}
```

后续诊断版本可以生成 `recent_only`、`key_evidence_ablated` 和 `irrelevant_ablated`，但每种可见历史必须分别接受人类标注，不能复制 full-history 标签。

## 3.4 Intensity 定义

人类不直接标 0–100，而使用五级序数量表和一个信息不足选项：

| 标签 | 定义 |
|---|---|
| `absent` | 几乎没有证据表明该状态存在 |
| `mild` | 状态存在但主要处于背景，不明显影响当前判断 |
| `moderate` | 状态清楚存在并对当前反应产生可见影响 |
| `strong` | 状态是当前体验的重要组成部分，明显影响判断或行为 |
| `very_strong` | 状态占主导地位，很可能决定下一步反应 |
| `cannot_determine` | 历史证据不足、冲突或无法合理判断 |

`absent` 与 `cannot_determine` 必须分开：没有该状态不等于无法判断。

标注者判断的是角色潜在体验，不是音量、表情夸张程度、客观风险或标注者自己的反应。

## 3.5 Change Direction 定义

相对 `change_anchor_node_id` 判断：

- `increase`：当前程度明显高于锚点；
- `similar`：没有足够证据表明显著变化；
- `decrease`：当前程度明显低于锚点；
- `cannot_determine`：锚点或当前证据不足。

## 3.6 人类 Confidence 定义

Confidence 表示证据对刚才判断的支持程度，不表示状态强度。

| 标签 | 定义 |
|---|---|
| `low` | 主要依赖猜测，证据少或明显冲突 |
| `medium` | 有部分支持，但存在其他合理解释 |
| `high` | 有多处一致证据，替代解释较弱 |
| `very_high` | 历史、行为和当前反应形成直接一致的证据链 |

每位标注者对每个状态分别填写 intensity、change、confidence 和 `evidence_node_ids`。

## 3.7 模型 Confidence

模型不自由填写单个 0–1 confidence。它必须输出：

- 六类 intensity 概率分布；
- 四类 change 概率分布；
- 预测标签；
- 关键证据节点。

模型 confidence 由概率分布自动计算，例如最大概率或分布熵。概率和必须在数值容差内等于 1。

## 3.8 T1 模型输出

```json
{
  "instance_id": "IA001_T1_CP01_P01_text",
  "state_predictions": [
    {
      "state_id": "anger",
      "intensity_probabilities": {
        "absent": 0.02,
        "mild": 0.08,
        "moderate": 0.45,
        "strong": 0.38,
        "very_strong": 0.06,
        "cannot_determine": 0.01
      },
      "predicted_intensity": "moderate",
      "change_probabilities": {
        "increase": 0.72,
        "similar": 0.18,
        "decrease": 0.06,
        "cannot_determine": 0.04
      },
      "predicted_change": "increase",
      "evidence_node_ids": ["D01", "N11"]
    }
  ]
}
```

对应 Schema：`tasks/T1/model_output_schema_v0.2.json`。

## 3.9 T1 人类标注

```json
{
  "annotation_id": "ANN_001",
  "instance_id": "IA001_T1_CP01_P01_text",
  "annotator_id": "A001",
  "task_type": "T1_state_tracking",
  "state_annotations": [
    {
      "state_id": "anger",
      "intensity_label": "strong",
      "change_direction": "increase",
      "annotator_confidence": "high",
      "evidence_node_ids": ["D01", "N11"]
    }
  ],
  "created_at": "2026-01-01T00:00:00Z",
  "quality_status": "unreviewed"
}
```

对应 Schema：`tasks/T1/human_annotation_schema_v0.2.json`。

## 3.10 T1 Ground Truth

未标注 Instance 保持：

```json
{"ground_truth": null, "label_status": "pending_human_annotation"}
```

聚合后保存完整人类分布，而不是作者数值或单一多数标签：

```json
{
  "state_id": "anger",
  "annotator_count": 5,
  "intensity_distribution": {
    "absent": 0.0,
    "mild": 0.2,
    "moderate": 0.6,
    "strong": 0.2,
    "very_strong": 0.0,
    "cannot_determine": 0.0
  },
  "change_distribution": {
    "increase": 0.8,
    "similar": 0.2,
    "decrease": 0.0,
    "cannot_determine": 0.0
  }
}
```

核心集每条至少 3 人，开发/测试核心实例建议 5 人。

## 3.11 T1 指标

主指标：

1. Ordinal MAE：强度等级距离；
2. Distributional distance：模型与人类强度分布距离；
3. Change-direction macro-F1；
4. Evidence Recall@K。

辅助指标：Brier score、NLL、ECE、按历史长度和因果距离分层结果。

`cannot_determine` 不映射到序数 0–4，单独评价分类准确率与覆盖率。

# 4. T2：History-sensitive Merge Test

输入两段不同历史和完全相同的当前场景，预测状态差异维度、方向、关键选择和概率。T2 必须保证当前场景字节级一致或有稳定 checksum，并随机交换 A/B 顺序。

主指标：Pairwise Direction Accuracy、Difference-dimension macro-F1、Causal-choice Recall@K、Joint Accuracy 和校准误差。

# 5. T3：Counterfactual Choice Effect Prediction

输入共同历史、决策刺激和 2–4 个候选行动，预测每项行动造成的即时/延迟状态变化及选项排序。

主指标：变化方向 macro-F1、pairwise ranking accuracy、Kendall’s tau；有可靠连续人类标签后再计算 effect-size correlation。

# 6. 数据划分与标签原则

- 必须按 Story World 划分 train/validation/test；
- 同一 semantic instance 的 text/video variants 必须在同一 split；
- T2 的 History A/B 不得拆分；
- 作者 effects、flags 和 terminal effects 不进入模型输入；
- 正式 ground truth 只来自独立标注；
- 保存原始标注和聚合分布；
- 低一致性必须区分合理多解、文本歧义和标注失败。
