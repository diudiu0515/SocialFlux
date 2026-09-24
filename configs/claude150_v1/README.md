# Claude150 正式候选分支

Claude Fable 构建 150 个独立场景，并在唯一共享 Environment 上完成一个 10–20 轮 rollout。每个场景只有一个 policy slot、一次正式生成机会和至多一条 trajectory。

- rollout.json：离线数据采集，policy 使用 task_rollout_action_v1。
- t4.json：在线任务 T4，policy 使用 task_t4_action_v21，judge 使用 t4_judge_v2。
- model_routes.chat.pool2.json：该分支所有 LLM 角色均由 Claude Fable 独立调用。
- 多模态统一读取 ../multimodal_generation.json；视频请求固定使用 talking_head_generation_v1。

Environment 始终是 Claude appraisal、确定性 Python 数值更新、Claude response。

- post_rollout_policy.json：rollout 完成后跳过全部真人审核/签署阶段；机器产物继续保留，skipped 不视为 passed。
