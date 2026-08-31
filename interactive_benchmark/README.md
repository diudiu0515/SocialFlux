# EmoTree Interactive Benchmark

本目录把可选的 `worlds/*/story.json` 完整故事世界转换为模型实际评测的独立实例。当前旧 IA001/IA002 world 源文件已按项目整理要求移除；转换器、schema 和测试工具保留，后续加入新 world 即可复用。故事 JSON 是创作与因果结构层；benchmark JSONL 才是模型输入层；人类标签单独保存在 annotation overlay 中。

## 三层数据

```text
Story World
  角色、20轮对话、选择、分支、汇合、状态与视频生成说明
        ↓ converter
Benchmark Instance
  T1/T2/T3 的模型可见输入、预测格式与元数据
        ↓ independent annotation
Annotation Overlay
  独立标注者回答、置信度、质量状态和聚合分布
```

作者 `effects`、`flags_set` 和 `terminal_effects` 不进入模型输入，也不会成为自动 ground truth。

## 构建

```bash
python interactive_benchmark/scripts/convert_interactive_to_benchmark.py \
  worlds/IA001/story.json \
  worlds/IA002/story.json \
  -o build/interactive_benchmark_v0.2/instances.jsonl
```

当前 pilot 生成 48 条未标注实例：

- IA001：24 条；
- IA002：24 条；
- T1：20 条；
- T2：12 条；
- T3：16 条；
- text 与 text_video 各 24 条。

T1/T2/T3 均已按每个 Story World 的预注册上限平衡采样；同一语义实例的双模态 variant 必须成对划分和统计。

## Schema

- `schema/benchmark_instance_schema_v0.2.json`：单条模型评测实例；
- `schema/annotation_overlay_schema_v0.1.json`：跨任务通用标注容器；
- `schema/t1_model_output_schema_v0.2.json`：T1 模型概率输出；
- `schema/t1_human_annotation_schema_v0.2.json`：T1 人类序数标注；
- `schema/t2_model_output_schema_v0.2.json`：T2 状态方向概率、证据与原因选择输出；
- `schema/t2_human_annotation_schema_v0.2.json`：T2 人类方向、证据与原因选择标注；
- `schema/t3_model_output_schema_v0.2.json`：T3 行动×状态×时间窗概率输出；
- `schema/t3_human_annotation_schema_v0.2.json`：T3 人类反事实后果标注；
- Story World Schema 位于 `shared/schema/interactive_story_schema_v0.1.json`。

## 测试

```bash
python -m unittest discover -s interactive_benchmark/tests -v
```

测试覆盖实例数量、ID 唯一性、每 world 固定 3 个 T2、text/text_video 配对、T2 共享当前场景、6–10 个状态、原因选择、history selector 可解析，以及作者 effects 不泄漏。

## Demo 应读取什么

Benchmark Demo 默认读取 `instances.jsonl`，而不是直接让用户游玩 story JSON：

- Dataset Explorer 可以额外读取 story world 来画 DAG；
- Task Viewer 读取 benchmark instance；
- Annotation Viewer 读取 overlay；
- Evaluation Dashboard 读取模型 predictions 与人类聚合标签；
- text_video 实例当前携带 `generation_spec`，实际视频生成后把 `asset_status` 和 `asset_path` 写入独立媒体 manifest，避免修改冻结的任务文本。
