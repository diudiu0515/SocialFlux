# GPT50 实验配置

GPT50 是独立的 50 场景试验分支。场景由 GPT-6 Astra 构建；它不读取 Claude150 场景池。

旧 `rollout.json` 只保留为 pre-v3 证据。新的正式入口固定使用
`rollout.state_v3.json` 与 `scenarios_state_v3/`，输出到独立的
`rollouts_state_v3/`，禁止混入旧 rollout：

- GPT-6 Astra 生成 evaluated-participant action；
- 唯一共享 Environment 由 Claude Fable appraisal、确定性 Python 状态更新、Claude Fable response 组成；
- 每个场景一个 policy slot、一次正式生成机会、至多一条正式 trajectory；
- trajectory 在第 10–20 轮自然结束，最多运行 20 轮；
- 不做 best-of-N，不用失败轨迹触发替代采样。

状态转换使用 `environment_appraisal_v15` 与
`evidence_independent_hysteretic_v3`。配置显式声明
`socialflux_state_transition_standard_v3`，并在 API 请求前检查四维 S0、快慢
变量、双向证据计划、自然 10–20 轮合同和人工冻结状态。轨迹结束后检查四族真实变化、
快变化和合规慢变化；失败轨迹保留为分母证据，不补写 delta、不放宽阈值。

`model_routes.astra.json` 用于 GPT 场景构建以及 rollout 后的 GPT 分支 T1–T4。`model_routes.hybrid.json` 只用于 rollout：policy 路由读取 GPT 凭据，appraisal/response 路由读取 Claude 凭据。两张路由表共享 prompt 家族，但不改变模型职责。

当前场景构建入口：

```bash
python scripts/generate_gpt50_scenarios.py
```

当前 rollout 入口（全部 state 人工签字后再运行）：

```bash
bash scripts/run_gpt50_pipeline.sh
```

启动器默认要求 `scenarios_state_v3/human_review/scenario_state_review.signed.json`
并只运行 rollout；Gate 和视频下游默认关闭。所有 API 失败都作为该场景唯一一次
生成的失败证据保留，不产生第二条候选。

## 当前候选批次的交付语言（2026-10-07）

`unified_current_trust_v1_gpt50_active` 的原始 rollout 使用中文，最终交付需要英文。
保留原始中文轨迹供审查和追溯；英文版是同一轨迹的翻译，不是新增 rollout。
英文导出需覆盖对话及中文的判断说明，并将 evidence_span 与对应英文对话中的实际片段对齐。
scenario_id、trajectory_id、turn_id、角色归属、state/dynamics 数值、delta 和判断标签保持不变。
既有英文场景内容保留；翻译不得把承诺改成已完成事实，或改变否定、条件和不确定性。
翻译版本需记录原始产物哈希、翻译配置与核查状态；中文轨迹的 Gate2 结论不自动构成英文译文的等义核查结论，人工待审状态继续保留。
按用户明确要求，已启动英文迁移：已有中文只翻译，不重新生成；后续新调用使用英文。
运行器在 `language_migration/` 保留迁移前的调用前缀和修订记录，复用每个已保存的模型输出。
语言适配与忠实翻译由 `pipeline/localization.py` 集中实现，配置为 `localization.json`，
翻译入口为 `scripts/translate_rollouts.py`；每个场景的英文版本保存在原目录的 `english/`。
网站默认展示已完成翻译的同一轨迹，原始记录继续保留。英文译文不自动获得人工通过结论。
网站美工和布局保持现状。

## T4 与多模态

t4.json 是 GPT50 的在线任务 T4 合同：evaluated policy 与 T4 judge 使用 GPT-6 Astra，appraisal/response 继续使用同一个 Claude Environment。T4 行动 prompt 固定为 task_t4_action_v21，不复用 10–20 轮离线采集的 task_rollout_action_v1。

Claude150 与 GPT50 共用 online_multimodal_v2 触发合同。Online T4 的无台词资产读取 ../online_multimodal_assets.json 并使用 online_nonverbal_event_v1；offline 重要节点 talking head 读取 ../multimodal_generation.json 并使用 talking_head_generation_v4。两类资产不可互换；v3 delivery 证据保持兼容，历史 v1/v2 只作审计证据。
