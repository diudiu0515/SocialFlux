# SocialFlux Prompt Audit

审计日期：2026-09-09。范围：`prompts/*.md`、`prompts/manifest.json`、对应 schema 与 Python caller。共保留 32 个版本化 prompt；未登记 Markdown 数为 0。

## Prompt 逐项审计

| Prompt | 层 / 当前职责与调用方 | 输入与隐藏信息权限 | 输出合同 | 发现的问题与本次处理 |
|---|---|---|---|---|
| `scenario_script_generation_v1` | author-side；`scenario_sources generate-script` 生成原创新社会剧本 | 只读机制、关系、权力、冲突、信息差 brief；不读 state/task | Markdown narrative | 拆出旧“直接生成 benchmark JSON”，明确不考虑 schema/S0/任务 |
| `narrative_structure_extraction_v1` | author-side；`scenario_sources extract-structure` 从影视作品提取高层社会机制 | 只读作品标题、媒介与分析请求；不读 state/task | `narrative_structure.schema.json` | 只保留关系、权力、目标与信息差结构；强制丢弃角色、台词、标志性物件、机构及情节序列，并要求原创表层文本 |
| `scenario_quality_gate_v1` | validation；`scenario_sources quality-check` 在 normalization 前审 source | 只读 source/provenance | `scenario_quality_report.schema.json` | 修正昨日的错误顺序；LLM 只能 pending，真人才能 approved |
| `scenario_normalization_v1` | author-side；`scenario_sources normalize` | 只读已批准 source 与 quality report | `scenario_blueprint.schema.json` | 不再同时生成 S0/D0、阈值、action effects 或 checkpoint |
| `initial_state_configuration_v1` | author-side；`scenario_sources initialize` | 读 approved blueprint 与 private design fields | `initial_state_proposal.schema.json` | 从 normalization 分离；输出 candidate，模型不能 human-freeze |
| `environment_appraisal_v2` | legacy author-side runtime | 旧自由文本 appraisal | inline JSON | 仅保留旧轨迹复现，不再由 canonical factory 调用 |
| `environment_appraisal_v3` | author-side runtime；每轮第 1 个 LLM call | 读 persona、goal、hidden intention、S/D、observable memory、exact action | 固定 event features + 稀疏 variable impact candidates | 不生成 response/delta；direction 由语境判断，magnitude 与数值更新交给统一 deterministic calibrator |
| `state_update_v2` | legacy，不在 canonical runtime | 旧 appraisal → semantic delta LLM call | inline JSON delta | 已由 `deterministic_social_delta_calibrator_v1` 替代；保留文件仅用于旧产物审计 |
| `environment_response_v3` | author-side runtime；`ModelResponseGenerator` | 读 persona/private intent、evaluated role、history、appraisal、updated S/D、action | observable text only | 实测后加入 environment-only 身份锁、单轮长度、无舞台说明与非重复约束 |
| `environment_response_v4` | author-side runtime；历史长程版本 | persona/private intent、角色、history、appraisal、updated S/D、action、turn_id | observable text only | 针对 20 轮加入未决承诺、时间跳跃和单议题拉长约束；保留历史复现 |
| `environment_response_v5` | legacy 长程版本 | 阶段进度 + 全部历史发言 | observable text only | “每轮强制新增实际命题”会诱发 artificial escalation，已退出 canonical runtime |
| `environment_response_v6` | author-side runtime；每轮第 2 个且最后一个 LLM call | updated S/D、structured appraisal、history、lightweight interaction ledger | observable text only | 优先回答当前请求；新 consequential content 稀疏；区分 proposal 与 external fact；不靠新增条件制造进度 |
| `environment_response_v7` | author-side runtime；当前正式每轮第 2 个 LLM call | v6 输入 + public longitudinal context/time/event records | observable text only | 允许片段级合理暂停；按语义新信息而非话题轮数判断进展；期限不等于履约；正式 runtime 仅用 hard-error validator，词面重复保留为诊断 |
| `memory_retrieval_v2` | author-side optional；`ModelMemoryModule` | 只读 observable history/action | inline memory JSON | 移除 private-state access；校验 ID 均来自历史。默认 runtime 可用等价确定性 retriever |
| `observable_expression_v1` | author-side media specification；媒体接入协议 | 读 updated private social context | `observable_expression.schema.json` | 从视频生成中拆出可观察表达；禁止一对一刻板编码和私有标签 |
| `talking_head_generation_v1` | media-side；provider-neutral 外部 API 输入协议 | 只读安全人物外观、observable response/expression | `talking_head_request.schema.json` | trigger 后稀疏生成；禁止 latent/threshold/答案泄漏；旧本地资产与引擎已删除，等待外部 API |
| `counterfactual_action_generation_v1` | benchmark construction；`ModelCandidateGenerator` | 只读真实 checkpoint 的 public observation | string array，经 caller 转 `{"text": ...}` | 移除策略标签与显然好/坏二分；只生成局部可行动自由文本 |
| `t2_shared_observation_v3` | benchmark construction；`ModelCandidateGenerator` | 读显式 target/evaluated 身份与两段 public natural histories | inline O* JSON | 实测修复 O* 角色互换；强制由 environment target 发话、双历史兼容且禁止 private provenance 泄漏 |
| `local_intervention_validation_v1` | author-side validation protocol | 可读真实 checkpoint private experiment packet | `local_intervention_review.schema.json` | controlled 只保留为局部实验，不再驱动多轮策略 |
| `instance_quality_judge_v2` | historical validation prompt；当前 Gate 4 使用 `python -m pipeline audit` 的结构检查与 hash-bound 人工抽查 | 只读去除 model/provider/trajectory/private state/metadata 后的 participant-visible packet | `instance_quality_judge.schema.json` | 无 active caller；仅保留旧实验审计，不得作为 human GT |
| `rollout_quality_judge_v1` | legacy validation；仅用于解释旧开发证据，不再用于新生成 | 只读 state-free 场景参考（背景、角色、显式目标、persona）和 observable action/response/expression；不读 hidden intention、private state、provenance 或阈值 | `rollout_quality_judgment.schema.json` | 固定 gate.md 六维评分与 hard reject；补充 1–5 锚点（4=良好仅轻微瑕疵、3=存在明显实质限制）并要求 rationale 与分数一致；caller 按 trajectory ID 派生确定性 seed，跨模型族二审缺失时不能形成正式合并记录 |
| `rollout_quality_judge_v2` | production screening；`run_rollout_quality_judge` 与 repair prefilter | 只读 state-free 场景参考和 observable trajectory | `rollout_quality_judgment_v2.schema.json` | 固定 Protocol v1 六维、10 项 hard reject；每个维度强制 1–3 个真实 turn ID，caller 校验引用存在；PASS/REVIEW/REJECT 由确定性代码计算 |
| `history_dependence_probe_v1` | evaluated-policy-side counterfactual；`run_history_dependence` | policy prompt 只读 full/recent-k/critical-event-removed 三种 public observation；同一脚本另外在 author-side restore 相同 S/D/action 做环境解释重放 | natural-language action only；脚本把 action 差异与 environment appraisal/state-delta 差异写入 `history_dependence_result.schema.json` | 三个 policy 条件改为同配置、同 seed 重新采样，原 rollout action 只留作审计；环境探针只运行 canonical appraisal/state update，不生成不会反向影响 delta 的回复；支持逐条断点与新 ID 定向复验 |
| `task_t1_v1` | evaluated-agent-side；T1 baseline/evaluation | 只读 public longitudinal instance | `task_t1_output.schema.json` | 移除作者 effects/oracle；证据 ID 必须可见 |
| `task_t2_v1` | evaluated-agent-side；T2 baseline/evaluation | 只读 A/B history 与相同 O* | `task_t2_output.schema.json` | 明确 O* byte-identical，禁止构建 metadata/private state |
| `task_t3_v1` | evaluated-agent-side；T3 baseline/evaluation | 只读 public checkpoint、2–4 action、horizon | `task_t3_output.schema.json` | 主任务禁止 oracle state/未来分支；所有 option 同 protocol/horizon |
| `task_t4_action_v2` | evaluated-agent-side；`ModelPolicy` 用于自然 rollout/T4 | 只读 policy observation | natural-language action only | 实测后加入 evaluated-only 身份锁、1–3 句、语义重复时强制换策略、禁止虚构政策/材料/已完成外部动作；运行时另拒绝 prompt-facing 元叙述、列表输出、换行和超过 180 字的 action |
| `task_t4_action_v3` | evaluated-agent-side；历史长程版本 | 显式角色卡（name/role/explicit goal）+公开背景/历史/回应/expression/media | natural-language action only | 面向 20 轮长程互动强化持续目标、局部推进与信息边界；保留历史复现 |
| `task_t4_action_v4` | evaluated-agent-side；历史诊断基线 | v3公开输入 + anti-repetition ledger | natural-language action only | 保留旧 full-regex 测量路径以复现实验，不再作为正式默认 |
| `task_t4_action_v21` | evaluated-agent-side；当前 T4 与 rollout 默认 prompt | 公开角色卡、`longitudinal_context`、public time/event records 和 anti-repetition ledger | natural-language action only | 同话题有新解释/立场/取舍/证据即可继续；必要确认不因词面规则拒绝；允许自然结束；承诺、实际履约、风险、信任和未来意愿分别判断 |
| `t4_judge_v1` | validation；T4 judge protocol | 只读 packet 明示的 allowed evidence | `t4_judge_output.schema.json` | 多维评分，不把低冲突当目标；明确 not human GT |
| `t4_judge_v2` | validation；当前 T4 终局 judge | 只读角色公开目标与最多20轮 observable trajectory；不读 persona 私有值/S/D/delta | `t4_judge_output.schema.json` + caller严格字段/turn-ID校验 | 固定 Goal/Adaptation/Risk/Recovery/Relationship 五维；仅自然结束或预算结束后调用；自动分数仍可能过度乐观，保留 not-human-validated 标记 |
| `human_annotation_v2` | human-facing validation/GT protocol | 只读冻结 annotation packet；author-side 实验必须显式标识 | packet-supplied schema / overlay | simulator candidate 仅是假设；人类标签、证据、不确定性独立记录 |

## Conceptual problems 与修复

删除了旧版 direct scenario generation、story world、合并 appraisal/update、旧 response、旧 memory、旧 T1/T2/T3/T4、policy action 和 human annotation prompt。同步删除 action interpreter、controlled policy、template response、world benchmark schema 与旧任务合同。[`prompt_check.md`](../source-notes/prompt_check.md) 第 16 节关于 escalation/neutral/repair 三种多轮 policy 的旧建议与更新后的 [`revision.md`](../source-notes/revision.md) 冲突；按较新的 revision，三类固定策略不进入生成 pipeline，只保留真实 checkpoint 上的局部自由文本 intervention。

所有当前 prompt 已采用 task-first、quality/constraints 居中、output/schema-last。Structured-appraisal LLM call → deterministic state/dynamics calibration 与 numeric update → 独立 response-generation LLM call 的顺序已在代码和测试中固定。Source quality → normalization → initial state 的顺序也已在 CLI、schema 和文档中固定。

## Information-boundary audit

- Evaluated model 的 T1/T2/T3/T4 prompt 不接收 hidden intention、S/D、appraisal、delta、trigger conditions、future branch 或 source trajectory metadata。
- Environment appraisal/state/response 是 author-side private caller；response 返回值只允许 observable text。
- Memory prompt 只能访问 observable history，且 caller 校验 evidence ID。
- T2 O* 与 T3 action candidate 的 construction caller 只传 public checkpoint/history。
- Private local intervention 数据不进入 benchmark input，`evaluation.leakage.assert_no_leaks` 在写实例前执行。
- Talking Head request 只使用 safe observable specification；trigger ID/threshold 保留在 private log。
- 网站是研究者调试视图，会展示 private state，但不作为 participant context，也不生成第二套环境。

审计结果：代码路径未发现 evaluated-agent hidden-state leakage；真实模型输出仍需运行时 schema validation、抽样人工检查和 release 前 dataset audit。

## Schema 与 caller 修改

新增 narrative structure、blueprint、source quality、candidate initial state、T1/T2/T3 输出、instance quality judge、T4 judge、observable expression、Talking Head request 与 local intervention review schemas。更新 canonical scenario/trajectory schema，删除 action effects/action ID 合同。更新 `scenario_sources.py`（含 `extract-structure`）、`environment/appraisal.py`、`environment/state_updater.py`、`environment/response_generator.py`、`environment/memory.py`、`offline/candidate_generation.py`、`policies/model_policy.py` 与 `scripts/run_pipeline.py`。

## 未决设计问题

- 20 个现有 scenario 的 provenance/quality/S0-D0 仍需真人审核，不得自动批准。
- task 输出概率和为 1 需要运行时 validator；JSON Schema 只能约束单值范围。
- `observable_expression_v1` 与 `talking_head_generation_v1` 保留 provider-neutral 协议；旧 EchoMimicV2/MuseTalk 资产、模型和工具已永久删除。待接入外部 API 后重新执行表达一致性、连续性、语音自然度和效用审核。
- human annotation 的具体字段按 T1/T2/T3 packet supplied schema 冻结；正式标注平台与 adjudication 尚未执行。
- T4 judge 与人类评分的相关性/一致性尚未建立。
