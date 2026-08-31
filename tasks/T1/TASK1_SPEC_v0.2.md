# EmoTree Task1 v0.2 任务定义

## 1. 目标

输入目标角色的完整历史和当前 checkpoint，预测目标角色当前主观状态的强度、相对上一锚点的变化方向，并定位证据。每个 world 固定 5 个 semantic instances；每个生成 `text` 与 `text_video` 两个 variant，共 10 条物理记录。

## 2. 输入约束

- `history_view=full_history`；
- 当前 checkpoint 前至少覆盖 8 轮；
- 提供 `change_anchor_node_id`；
- 双模态 variant 的语义输入和答案相同，仅媒体条件不同；
- 作者 effects、flags、终局效果不得进入模型输入。

## 3. 输出

每个目标状态输出：

- 强度概率：`absent/mild/moderate/strong/very_strong/cannot_determine`；
- 变化概率：`increase/similar/decrease/cannot_determine`；
- 两组概率各自归一化为 1；
- 预测标签必须对应最大概率；
- 提供历史证据节点。

T1 只标注主观情绪、动机/应对和关系状态，不包含毕业风险、职业风险、用户安全风险等客观风险。

## 4. Confidence 与 Ground Truth

模型不自由填写 confidence。主 confidence 为最大概率，辅助报告 margin 和归一化熵。人类 annotator confidence 使用 `low/medium/high/very_high`，不参与主标签加权。正式 ground truth 为质检通过的人类标签未加权频数分布；作者 effects 不是答案，未标注实例保持 `ground_truth=null`。

## 5. 固定采样

```json
{
  "semantic_instances_per_world": 5,
  "required_variants": ["text", "text_video"],
  "physical_instances_per_world": 10,
  "selection_strategy": "round_robin_checkpoint_then_path",
  "seed": 42,
  "require_distinct_choice_paths_when_available": true
}
```

优先轮询不同 checkpoint，再选择同一 checkpoint 的不同历史。semantic instance 及其双模态 variant 必须处于同一数据 split。

## 6. 文件与指标

- 模型输出：`tasks/T1/model_output_schema_v0.2.json`；
- 人类标注：`tasks/T1/human_annotation_schema_v0.2.json`；
- 概率工具：`tasks/T1/t1_probability_utils.py`。

主指标为分布交叉熵/Brier、强度与变化 macro-F1、序数 MAE；校准报告 NLL、ECE 和 reliability diagram。`cannot_determine` 单独报告覆盖率与分类表现。
