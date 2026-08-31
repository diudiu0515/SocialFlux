# EmoTree Task2 规范 v0.2

## 1. 实例规模

与 Task1 保持一致：每个 Story World 固定 3 个 T2 semantic instances，每个生成 `text` 和 `text_video` 两个配对 variant。

```text
每个 world：
3 个 T2 semantic instances
3 个 text records
3 个 text_video records
共 6 条物理 records
```

两个 variant 共享 `semantic_instance_id`，使用不同 `instance_id` 和 `variant_id`。统计、划分和显著性检验以 semantic instance 为配对单位。

若一个 world 无法形成 3 个合格的历史对照，生成或构建失败，不能复制 comparison 补足。

## 2. 输入与输出

输入：共享前史、两段不同历史和完全相同的当前场景。

输出：目标角色在 History A 与 History B 中的状态差异方向、支持判断的历史证据、关键原因选择及概率。

```text
T2-A：Pairwise State Difference
同一状态在 A 和 B 中，哪边更高，还是基本相同？

T2-B：Evidence Grounding
A/B 各有哪些历史节点支持该差异判断？

T2-C：Causal Choice Attribution
哪些不同选择造成了当前状态差异？
```

## 3. 合格 T2 对照

每条 T2 必须满足：

- A/B 具有共享前史；
- A/B 至少有一个实质不同的选择；
- A/B 最终进入完全相同的当前场景；
- 当前场景的文本和媒体条件相同；
- 共享当前场景有稳定 SHA-256；
- 差异选择发生在当前场景之前；
- 每段完整历史推荐 8–20 轮；
- 作者 effects、flags 和 causal hypothesis 对模型不可见；
- target states 只包含预注册主观状态，不混入未单独定义的客观风险。

T2 的核心控制是：

```text
History A != History B
Current Scene A == Current Scene B
```

## 4. 输入组织

不重复存储完全相同的前史，推荐结构：

```json
{
  "instance_id": "IA001_T2_MC01_TEXT",
  "semantic_instance_id": "IA001_T2_MC01",
  "variant_id": "text",
  "task_type": "T2_history_sensitive_merge",
  "input": {
    "instruction": "比较两段历史中林砚在相同当前场景下的潜在状态。",
    "target_character": {
      "character_id": "STUDENT",
      "name": "林砚"
    },
    "shared_history_prefix": [],
    "history_a_delta": [],
    "history_b_delta": [],
    "shared_current_scene": {},
    "media": []
  },
  "target_spec": {
    "prediction_format": "pairwise_state_difference_v0.2",
    "target_state_ids": ["sadness", "anger", "pain", "self_respect", "advisor_trust", "advisor_hostility"],
    "direction_labels": ["higher_in_a", "similar", "higher_in_b", "cannot_determine"],
    "require_direction_probability_distribution": true,
    "require_evidence_node_ids": true,
    "require_causal_choice_probabilities": true,
    "require_self_reported_confidence": false,
    "model_confidence_source": "predicted_probability_distribution"
  },
  "ground_truth": null,
  "label_status": "pending_human_annotation"
}
```

`shared_history_prefix` 保存分歧之前完全相同的节点；`history_a_delta` 和 `history_b_delta` 从首次分歧开始，到共享当前场景之前结束。

## 5. 状态差异方向

每个状态使用四类：

| 标签 | 定义 |
|---|---|
| `higher_in_a` | 目标角色在 A 中的该状态明显强于 B |
| `similar` | 没有充分证据认为 A/B 存在有意义差异 |
| `higher_in_b` | 目标角色在 B 中的该状态明显强于 A |
| `cannot_determine` | 历史证据不足、互相冲突或无法合理比较 |

`similar` 与 `cannot_determine` 必须分开：判断两边相近，不等于无法判断。

## 6. 模型输出

```json
{
  "instance_id": "IA001_T2_MC01_TEXT",
  "state_comparisons": [
    {
      "state_id": "sadness",
      "direction_probabilities": {
        "higher_in_a": 0.62,
        "similar": 0.20,
        "higher_in_b": 0.13,
        "cannot_determine": 0.05
      },
      "predicted_direction": "higher_in_a",
      "evidence_node_ids_a": ["D01_FIRST_RESPONSE", "N10_SLAM_RESULT"],
      "evidence_node_ids_b": ["D01_FIRST_RESPONSE", "N11_ARGUE_RESULT"]
    }
  ],
  "causal_choice_predictions": [
    {"choice_id": "D01_A", "relevance_probability": 0.88, "selected": true},
    {"choice_id": "D01_B", "relevance_probability": 0.84, "selected": true}
  ]
}
```

对应 Schema：`tasks/T2/model_output_schema_v0.2.json`。

每个 `direction_probabilities` 的四类概率之和必须为 1。不同 causal choices 的 relevance probability 是独立多标签概率，不要求总和为 1。

## 7. 人类标注

每位标注者针对每个状态填写：

```json
{
  "state_id": "sadness",
  "direction_label": "higher_in_a",
  "annotator_confidence": "high",
  "evidence_node_ids_a": ["D01_FIRST_RESPONSE", "N10_SLAM_RESULT"],
  "evidence_node_ids_b": ["D01_FIRST_RESPONSE", "N11_ARGUE_RESULT"]
}
```

并对每个候选差异选择填写：

```json
{
  "choice_id": "D01_A",
  "is_causal": true,
  "annotator_confidence": "high"
}
```

完整记录还必须保存 `presentation_order = AB|BA`。界面随机交换 A/B，存储前映射回 canonical A/B。

对应 Schema：`tasks/T2/human_annotation_schema_v0.2.json`。

## 8. 人类 Ground Truth

假设 5 名有效标注者对 sadness 的方向判断为：

```text
higher_in_a       3人
similar           1人
higher_in_b       1人
cannot_determine  0人
```

计算：

```text
P_human(label) = 选择该标签的人数 / 有效标注人数
```

得到：

```json
{
  "higher_in_a": 0.6,
  "similar": 0.2,
  "higher_in_b": 0.2,
  "cannot_determine": 0.0
}
```

主 Ground Truth 使用未加权频数，不按 annotator confidence 加权。被质检拒绝的标注不进入分母。

Causal choice ground truth 是每个 choice 的独立选择比例：

```text
P_causal(choice) = 标为 causal 的人数 / 有效标注人数
```

例如 5 人中 4 人认为 D01_A 是原因，则 relevance ground truth 为 0.8。

## 9. Confidence

### 9.1 模型 Confidence

每个状态的主 confidence：

```text
model_confidence = max direction_probabilities
```

辅助量：

```text
margin = p_top1 - p_top2
entropy_confidence = 1 - H(P) / log(4)
```

模型不额外自由填写 confidence。

Causal choice confidence 直接使用该 choice 的 `relevance_probability`。

### 9.2 人类 Annotator Confidence

```text
low=1, medium=2, high=3, very_high=4
```

```text
mean_human_confidence = Σ value / N
normalized_human_confidence = (mean - 1) / 3
```

它只表示标注者认为证据是否充分，不用于加权主标签。

### 9.3 人类一致性

单个状态：

```text
human_consensus = 1 - H(P_human) / log(4)
```

整个数据集同时报告 nominal Krippendorff’s alpha。方向标签虽然具有 A/B 对称结构，但不应简单映射成连续差值后只报告相关系数。

## 10. A/B 顺序

canonical 数据固定 History A 和 History B。标注和模型评测时随机显示 AB 或 BA：

- 保存 `presentation_order`；
- BA 展示时同步交换 `higher_in_a` 与 `higher_in_b`；
- 输出解析后映射回 canonical 顺序；
- 同一 semantic instance 的 text/video variant 使用平衡顺序；
- 报告位置偏差。

## 11. 视频条件

同一个 T2 semantic instance 固定生成：

```text
text
text_video
```

两个 variant 的文字历史、A/B 对照和当前场景必须完全相同。视频只增加预注册的 talking-head 信息。

需要区分：

- `media_shared_prefix`：共享前史中的相同视频；
- `media_a_delta`：A 分歧历史特有视频；
- `media_b_delta`：B 分歧历史特有视频；
- `shared_current_media`：当前完全共享的视频。

如果 A/B 当前媒体不相同，该实例不能作为严格 T2 merge comparison。

## 12. Metadata

每条 T2 应保存：

```json
{
  "comparison_id": "IA001_MC_D01_A_VS_B",
  "merge_node_id": "N20_CONFLICT_MERGE",
  "shared_current_scene_hash": "sha256:...",
  "shared_prefix_length_rounds": 5,
  "history_a_length_rounds": 8,
  "history_b_length_rounds": 8,
  "divergence_round": 6,
  "merge_round": 9,
  "causal_distance_rounds": 3,
  "decision_depth": 1,
  "merge_depth": 1,
  "canonical_history_a_choice_path": ["D01_A"],
  "canonical_history_b_choice_path": ["D01_B"],
  "candidate_causal_choice_ids": ["D01_A", "D01_B"],
  "controlled_current_scene": true,
  "presentation_order_policy": "balanced_ab_ba"
}
```

## 13. 指标

T2-A：

- Direction Accuracy；
- macro-F1；
- Brier score；
- NLL；
- Jensen–Shannon divergence；
- ECE。

T2-B：

- Evidence Recall@K；
- Evidence Precision@K；
- Evidence F1。

T2-C：

- Causal-choice AUROC/AUPRC；
- Recall@K；
- 多标签 Brier score。

联合指标：

```text
Joint Accuracy = 方向正确 AND 至少一个关键原因选择正确
```

必须同时按历史距离、分歧轮次、状态类别、模态和 A/B 展示顺序分层报告。

## 14. 当前实现状态

v0.2 已实现：

- 每个 world 固定 3 个 T2 semantic instances；
- 每个 semantic instance 固定生成 `text` / `text_video` 配对，共 6 条物理记录；
- 历史拆分为共享前缀与 A/B 差异段，当前场景仅保存一次；
- 6–10 个目标状态和四类方向概率（含 `cannot_determine`）；
- 专用模型输出、人类标注 Schema 与概率计算工具；
- 共享当前场景 hash、历史距离、标准 A/B 路径与展示顺序策略；
- 候选原因选择及其独立 relevance probability。

后续新增 world 必须通过 Story Schema、converter 和自动测试的相同门禁。
