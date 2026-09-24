# GPT50 实验配置

GPT50 是独立的 50 场景试验分支。场景由 GPT-6 Astra 构建；它不读取 Claude150 场景池。

`rollout.json` 是唯一 rollout 合同：

- GPT-6 Astra 生成 evaluated-participant action；
- 唯一共享 Environment 由 Claude Fable appraisal、确定性 Python 状态更新、Claude Fable response 组成；
- 每个场景一个 policy slot、一次正式生成机会、至多一条正式 trajectory；
- trajectory 必须在第 10–20 轮自然结束；
- 不做 best-of-N，不用失败轨迹触发替代采样。

`model_routes.astra.json` 用于 GPT 场景构建以及 rollout 后的 GPT 分支 T1–T4。`model_routes.hybrid.json` 只用于 rollout：policy 路由读取 GPT 凭据，appraisal/response 路由读取 Claude 凭据。两张路由表共享 prompt 家族，但不改变模型职责。

当前场景构建入口：

```bash
python scripts/generate_gpt50_scenarios.py
```

当前 rollout 入口（人工确认 prompt 后再运行）：

```bash
bash scripts/run_gpt50_pipeline.sh
```

正式运行应使用 Gate 1 签名；`--allow-unreviewed` 只用于明确标记的开发检查。所有 API 失败都作为该场景唯一一次生成的失败证据保留，不产生第二条候选。

## T4 与多模态

t4.json 是 GPT50 的在线任务 T4 合同：evaluated policy 与 T4 judge 使用 GPT-6 Astra，appraisal/response 继续使用同一个 Claude Environment。T4 行动 prompt 固定为 task_t4_action_v21，不复用 10–20 轮离线采集的 task_rollout_action_v1。

Claude150 与 GPT50 的在线触发参数、离线重要节点选择、视频请求构造和 prompt 完全统一，均读取 ../multimodal_generation.json 并使用 talking_head_generation_v1。
