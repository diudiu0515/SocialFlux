# SocialFlux Runtime Prompt Catalog

2026-10-10 核对后的调用链。`prompts/manifest.json` 注册 50 份可加载模板；
被替代的 39 份中间实验稿已删除，不再出现在注册表中。删除依据、恢复方式和
历史配置限制见 [Prompt 审计](PROMPT_AUDIT.md)。

## 当前 GPT50 / offline 来源链

入口配置为 `configs/offline_choice_dev60.json` 引用的
`configs/gpt50_experiment/rollout.state_observed_evidence_v6_candidate.json`，
环境由 `UnifiedEnvironmentFactory` 装配，沿用现有 `StatefulEnvironment`。

```text
公开 observation
  → task_rollout_action_v2_decision_continuity：人物行动
  → 独立的 state appraisal 与 interaction appraisal
  → Python 校验、校准、更新 state / dynamics
  → environment_response_v31_contrastive_event_driven：人物回应
  → 公开事件、ledger、非语言观测、下一轮 observation
```

| 阶段 | 实际模板或规则 | 运行入口 |
|---|---|---|
| 行动 | `task_rollout_action_v2_decision_continuity` | `policies/model_policy.py` |
| 状态判断 | `environment_state_appraisal_v6_observed_evidence` | `environment/independent_appraisal.py` |
| 人物方向绑定 | `state_actor_binding_v1.txt` | `environment/actor_bound_appraisal.py` |
| 信任定义与证据 | `configs/state_trust_current_evidence_v1.json` | `environment/unified_appraisal.py` |
| 互动判断 | `interaction_schema_bound_v1.txt` | `environment/unified_appraisal.py` |
| 状态数值更新 | 确定性 Python；无 prompt | `environment/state_updater.py`、`environment/calibration.py` |
| 环境回应 | `environment_response_v31_contrastive_event_driven` | `environment/response_generator.py` |

环境每步名义上有 3 次模型调用：state、interaction、response；policy 另计，
重试会增加实际请求数。state 与 interaction 只做解释，数值由 Python 更新。

`environment_interaction_appraisal_v1` 仍是基础消息构造依赖；统一适配器在发出
请求前用 `interaction_schema_bound_v1.txt` 替换其用户消息正文。
配置中的 `environment_appraisal_v36_evidence_grounded_state_interpretation`
在此独立模式下是兼容元数据，不是第四次环境调用。
两个 `.txt` 文件是实际注入的规则，保留原路径与正文；它们不属于 Markdown 模板注册表。

## 题目生成与作答

| 用途 | Prompt |
|---|---|
| Offline T1–T3 选择题作者 | `offline_choice_author_v1` |
| Offline T1–T3 主评测作答 | `offline_choice_answer_v1`；统一输出 `{"answer":"B"}` |
| 已有 checkpoint 提取 | `task_checkpoint_extraction_v1` |
| T2 受控规格、历史改写、共同表达 | `task_t2_adaptation_spec_v1`、`task_t2_controlled_branch_v1`、`t2_shared_observation_v3` |
| T3 候选行动 | `task_t3_action_candidates_v1` |
| 保留的旧任务协议 | `task_t1_v1`、`task_t2_v1`、`task_t3_v1` |
| 在线 T4 行动与评分 | `task_t4_action_v21`、`t4_judge_v2` |

选择题作者入口可以复用已有来源和受控构造，不要求每题重新调用作者模型。
T2 制作时的环境回放和 T3 未来分支属于作者侧证据，不向被测模型开放。
在线 T4 行动不受离线语料最低轮数约束；二者不可混用。

## 场景、审核与媒体

| 用途 | 保留的模板 |
|---|---|
| 批次场景构建 | `scenario_brief_batch_v2`、`scenario_candidate_script_v2`、`scenario_candidate_quality_gate_v1`、`scenario_candidate_core_v1`、`scenario_candidate_runtime_design_v2`、`scenario_candidate_state_values_v1`、`scenario_candidate_expression_triggers_v1` |
| 场景来源、规范化与修订 | `narrative_structure_extraction_v1`、`scenario_script_generation_v1`、`scenario_normalization_v1`、`initial_state_configuration_v1`、`scenario_quality_gate_v1`、`scenario_revision_v1` |
| 场景语义审核与补充 | `scenario_state_reauthoring_v1`、`scenario_state_semantic_audit_v1`、`scenario_evaluated_persona_backfill_v1` |
| 环境干预、历史依赖、记忆 | `environment_paraphrase_probe_v1`、`environment_persona_intervention_v1`、`counterfactual_action_generation_v1`、`history_dependence_probe_v1`、`memory_retrieval_v2` |
| 轨迹与题目审核 | `rollout_quality_judge_v2`、`instance_quality_judge_v2` |
| Offline 公开台词视频 | `talking_head_generation_v4`、`video_public_line_compression_v2`、`video_public_rendering_adaptation_v1` |
| Online 无台词非语言片段 | `online_nonverbal_event_v3` |

媒体生成只读取公开台词和可观察表达；被测 policy 不获得私有 state、隐含意图、
appraisal、触发阈值或未来分支。Gate 4 的题目审核与任务 T4 的在线评分是不同入口。

## 仍实际使用的兼容入口

这些模板保留是因为仍有可调用入口，而不是为了保留全部版本：

| 模板 | 用途 |
|---|---|
| `environment_appraisal_v11`、`environment_response_v25` | `pipeline/constants.py` / `formal_rollout_pool.json` 通用基线，以及旧 T2 回放 |
| `environment_appraisal_v12` | 通用 `t4_evaluation.json` 和 GPT50 / Claude150 基础配置 |
| `environment_appraisal_v22_slow_first` | GPT50 / Claude150 `rollout.state_v3.json` 的既有批次入口 |
| `environment_appraisal_v36_evidence_grounded_state_interpretation` | 完整 combined 判断入口及独立模式的配置合同 |
| `environment_state_appraisal_v1_per_variable` | 通用独立 appraiser / factory 默认值 |
| `task_rollout_action_v1` | 通用 rollout 与基础批次配置 |

历史记录中的旧 prompt ID 仍可用于识别 schema 和读取 provenance；这不表示对应
模板仍可用于新调用。不要把仍保留的兼容入口当作当前 GPT50 / offline 推荐链。

## 修改与检查

模板由 loader 校验 SHA-256。版本文件名支持 `_vN.md` 与 `_vN_label.md`。
修改后运行 `python scripts/update_prompt_manifest.py`；只检查而不写入使用
`python scripts/update_prompt_manifest.py --check`。已撤下的 ID 不能重新注册或
自动映射为新版；语义变化需使用明确的新版本和新运行指纹。
