# SocialFlux Runtime Prompt Catalog

本目录只保存运行时实际加载的固定 prompt。每个 prompt 使用稳定 prompt_id 与 _vN.md 文件名，由 manifest.json 记录路径和 SHA-256；caller 通过 prompts.loader 校验后加载。

## 当前实际 caller

| 阶段 | Prompt | Caller |
|---|---|---|
| Gate 1 场景候选筛选 | scenario_candidate_quality_gate_v1 | Claude150/GPT50 场景生成器 |
| Gate 2 改写与 persona 干预 | environment_paraphrase_probe_v1、environment_persona_intervention_v1 | run_environment_interventions.py |
| Gate 2 历史敏感性 | history_dependence_probe_v1 | run_history_dependence.py |
| Gate 2 E9 timescale | 无 LLM prompt | evaluation/timescale_validity.py |
| Gate 3 rollout 语义筛选 | rollout_quality_judge_v2 | review_active_rollouts.py |
| Gate 4 T1–T3 LLM 预筛 | instance_quality_judge_v2 | review_active_tasks.py |
| T1/T3 checkpoint 提取 | task_checkpoint_extraction_v1 | tasks/extraction.py |
| T1 作答 | task_t1_v1 | tasks/T1/answering.py |
| T2 受控窗口规格 | task_t2_adaptation_spec_v1 | tasks/T2/spec_authoring.py |
| T2 完整 History B 改编 | task_t2_controlled_branch_v1 | tasks/T2/branch_authoring.py |
| T2 作答 | task_t2_v1 | tasks/T2/answering.py |
| T3 候选行动 | task_t3_action_candidates_v1 | tasks/T3/action_authoring.py |
| T3 作答 | task_t3_v1 | tasks/T3/answering.py |
| 10–20 轮离线 rollout 行动 | task_rollout_action_v1 | policies/model_policy.py |
| 在线 T4 行动 | task_t4_action_v21 | policies/model_policy.py |
| T4 终局评分 | t4_judge_v2 | tasks/T4/answering.py |
| 环境 appraisal/response | environment_appraisal_v11、environment_response_v25 | environment runtime |
| 统一 talking-head 视频请求 | talking_head_generation_v1 | environment/video_requests.py |

Gate 4 不是任务 T4：Gate 4 的 LLM 预筛当前覆盖 T1–T3，之后仍进入人工抽查；任务 T4 使用独立在线互动 prompt 和五维终局评分。

## 两条必须分开的行动合同

- 离线语料 rollout 使用 task_rollout_action_v1，要求自然对话达到 10–20 轮。
- 在线任务 T4 使用 task_t4_action_v21，没有最低轮数，最多 20 轮，可自然结束。
- Claude150 与 GPT50 分支都遵守这个区分；两边仅模型路由不同。

## 多模态合同

Claude150 与 GPT50 共用 configs/multimodal_generation.json、environment/multimodal.py、environment/video_requests.py 和 talking_head_generation_v1。observable behavior 由 environment_response_v25 产生；没有 caller 的 observable_expression_v1 已删除。在线与离线视频请求都记录 prompt_id=talking_head_generation_v1。

## 修改流程

1. 只有研究语义变化时才新建版本；纯 caller 修复复用当前版本。
2. 同步 JSON schema、Python caller/validator 和本目录映射。
3. 运行 python scripts/update_prompt_manifest.py。
4. 运行 prompt、Gate、Task、T4 与多模态相关测试。

Evaluated-agent prompt 不得获得 hidden intention、latent state、appraisal、delta、trigger threshold、未来 branch 或 source-model metadata。Author-side environment prompt 只在对应私有阶段读取必要信息；talking-head 请求只包含公开台词和可观察表达。
