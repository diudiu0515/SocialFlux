# Claude150 正式候选分支

Claude Fable 构建 150 个独立场景，并在唯一共享 Environment 上完成一个 10–20 轮 rollout。每个场景只有一个 policy slot、一次正式生成机会和至多一条 trajectory。

- `rollout.json`：冻结的 pre-v3 历史合同。
- `rollout.state_v3.json`：新离线数据采集合约，固定读取
  `scenarios_state_v3/` 并写入独立 `rollouts_state_v3/`。
- t4.json：在线任务 T4，policy 使用 task_t4_action_v21，judge 使用 t4_judge_v2。
- model_routes.chat.pool2.json：该分支所有 LLM 角色均由 Claude Fable 独立调用。
- 多模态统一读取 ../multimodal_generation.json；新视频请求固定使用 talking_head_generation_v4，v3 delivery 证据保持兼容。

Environment 始终是 Claude appraisal、确定性 Python 数值更新、Claude response。
State v3 显式绑定 `environment_appraisal_v15`、
`evidence_independent_hysteretic_v3` 与第 10–20 轮自然结束、最多 20 轮。API
前必须通过完整 state 合同和真实人工冻结；自然结束后四族覆盖及快慢转换不满足时
记录为失败，不强制变化。Claude v3.3 使用独立配置和早期非强制慢变量机会。
`run_claude150_pipeline.sh` 默认只运行 v3 rollout，Gate 和视频下游保持关闭。

- post_rollout_policy.json：rollout 完成后跳过全部真人审核/签署阶段；机器产物继续保留，skipped 不视为 passed。
