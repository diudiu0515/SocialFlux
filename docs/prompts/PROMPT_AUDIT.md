# SocialFlux 当前 Prompt 映射

本文件只说明 Claude150 与 GPT50 当前批次实际加载的 prompt。历史实验版本不属于当前调用链，也不得作为恢复入口。

## 两套场景池

| 阶段 | Claude150 | GPT50 | Prompt |
|---|---|---|---|
| coverage/brief | Claude 生成 150 个 brief | 固定 50 域矩阵提供 brief | Claude 独有 `scenario_brief_batch_v2` |
| 原创场景脚本 | Claude | GPT-6 Astra | 共享 `scenario_candidate_script_v2` |
| 候选质量自检 | Claude | GPT-6 Astra | 共享 `scenario_candidate_quality_gate_v1` |
| 核心 dossier | Claude | GPT-6 Astra | 共享 `scenario_candidate_core_v1` |
| runtime dynamics | Claude | GPT-6 Astra | 共享 `scenario_candidate_runtime_design_v2` |
| 初始状态值 | Claude | GPT-6 Astra | 共享 `scenario_candidate_state_values_v1` |
| 表达与触发器 | Claude | GPT-6 Astra | 共享 `scenario_candidate_expression_triggers_v1` |

两套 scenario 产物彼此独立，不从另一套场景池复制或抽样。

## 唯一共享 Environment 与 rollout

每个 scenario 只有一个 policy slot、一次正式生成机会和至多一条正式 trajectory。trajectory 必须在第 10–20 轮自然结束，不做 best-of-N，也不以失败样本触发替代采样。

| 顺序 | 职责 | Claude150 调用模型 | GPT50 调用模型 | Prompt/实现 |
|---:|---|---|---|---|
| 1 | evaluated participant 行动 | Claude Fable | GPT-6 Astra | 共享 `task_rollout_action_v1` |
| 2 | 私有 appraisal | Claude Fable | Claude Fable | 共享 `environment_appraisal_v11` |
| 3 | 状态与 dynamics 更新 | deterministic Python | deterministic Python | `deterministic_social_delta_calibrator_v1`，无 LLM prompt |
| 4 | environment response | Claude Fable | Claude Fable | 共享 `environment_response_v25` |

Environment 是唯一基座：Claude appraisal、确定性 Python 更新、Claude response。GPT50 只替换被测 policy，并在 rollout 后由 GPT-6 Astra 执行该分支的下游 T1–T4；Claude150 的下游任务仍由 Claude 完成。

## 信息边界

- `task_rollout_action_v1` 只接收公开角色卡、显式目标、可观察历史、公开 ledger 与 timeline；不得接收 hidden intention、S/D、appraisal、delta 或 trigger threshold。
- `environment_appraisal_v11` 是 Environment 的第一个私有调用，只解释最新 evaluated-agent 行动并输出结构化语义候选，不写回复、不直接决定数值。
- Python 校准器是唯一数值更新器。
- `environment_response_v25` 是 Environment 的第二个且最后一个 LLM 调用，只输出 environment-agent 的可观察回复与表达字段。
- 在线 T4 评测仍使用 `task_t4_action_v21`；它不用于本次离线 10–20 轮 rollout。

## 版本纪律

`prompts/manifest.json` 保存 prompt 文件路径与 SHA-256，loader 在使用前校验。当前批次配置只允许上述 rollout prompt ID；旧 appraisal/response/T4-action 版本已经删除，代码不再保留对应兼容集合。旧 scenario authoring provenance 只用于识别已经生成且可复用的 Claude 场景，不会再次调用旧 prompt。

## Gate、Task 与多模态实际调用补充

- Gate 1：scenario_candidate_quality_gate_v1，由两套场景生成器调用。
- Gate 2：environment_paraphrase_probe_v1、environment_persona_intervention_v1、history_dependence_probe_v1；E9 timescale 是确定性实验，无 LLM prompt。
- Gate 3：rollout_quality_judge_v2，由 review_active_rollouts.py 调用。
- Gate 4：instance_quality_judge_v2 对 T1–T3 做全量 LLM 预筛，由 review_active_tasks.py 调用；人工抽查仍是最终语义审核。
- T1/T3 构造点由 task_checkpoint_extraction_v1 提取；T2 受控改编分别使用 task_t2_adaptation_spec_v1 与 task_t2_controlled_branch_v1；T1/T2/T3 作答分别使用 task_t1_v1、task_t2_v1、task_t3_v1；T3 候选行动使用 task_t3_action_candidates_v1。
- talking_head_generation_v1 是在线与离线视频请求的唯一生成 prompt；observable behavior 直接来自 environment_response_v25。
