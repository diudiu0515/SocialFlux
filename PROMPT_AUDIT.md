# SocialFlux Prompt Audit

审计日期：2026-09-03。范围：`prompts/*.md`、`prompts/manifest.json`、对应 schema 与 Python caller。共保留 20 个版本化 prompt；未登记 Markdown 数为 0。

## Prompt 逐项审计

| Prompt | 层 / 当前职责与调用方 | 输入与隐藏信息权限 | 输出合同 | 发现的问题与本次处理 |
|---|---|---|---|---|
| `scenario_script_generation_v1` | author-side；`scenario_sources generate-script` 生成原创新社会剧本 | 只读机制、关系、权力、冲突、信息差 brief；不读 state/task | Markdown narrative | 拆出旧“直接生成 benchmark JSON”，明确不考虑 schema/S0/任务 |
| `narrative_structure_extraction_v1` | author-side；`scenario_sources extract-structure` 从影视作品提取高层社会机制 | 只读作品标题、媒介与分析请求；不读 state/task | `narrative_structure.schema.json` | 只保留关系、权力、目标与信息差结构；强制丢弃角色、台词、标志性物件、机构及情节序列，并要求原创表层文本 |
| `scenario_quality_gate_v1` | validation；`scenario_sources quality-check` 在 normalization 前审 source | 只读 source/provenance | `scenario_quality_report.schema.json` | 修正昨日的错误顺序；LLM 只能 pending，真人才能 approved |
| `scenario_normalization_v1` | author-side；`scenario_sources normalize` | 只读已批准 source 与 quality report | `scenario_blueprint.schema.json` | 不再同时生成 S0/D0、阈值、action effects 或 checkpoint |
| `initial_state_configuration_v1` | author-side；`scenario_sources initialize` | 读 approved blueprint 与 private design fields | `initial_state_proposal.schema.json` | 从 normalization 分离；输出 candidate，模型不能 human-freeze |
| `environment_appraisal_v2` | author-side runtime；`ModelAppraiser` | 可读 persona、goal、hidden intention、S/D、observable memory、exact action | inline strict JSON | 从旧单步 transition 拆出解释；禁止分类/关键词 lookup，不更新 state |
| `state_update_v1` | author-side runtime；`ModelStateUpdater` | 读 previous S/D、已完成 appraisal、observable memory；不直接读 action | inline strict JSON delta | 与 appraisal 分离；只允许七级 delta、全变量等形状 |
| `environment_response_v2` | author-side runtime；`ModelResponseGenerator` | 读 persona/private intent、history、appraisal、updated S/D、action | observable text only | 强制 state update 后响应；禁止输出私有字段或模板 |
| `memory_retrieval_v2` | author-side optional；`ModelMemoryModule` | 只读 observable history/action | inline memory JSON | 移除 private-state access；校验 ID 均来自历史。默认 runtime 可用等价确定性 retriever |
| `observable_expression_v1` | author-side media specification；媒体接入协议 | 读 updated private social context | `observable_expression.schema.json` | 从视频生成中拆出可观察表达；禁止一对一刻板编码和私有标签 |
| `talking_head_generation_v1` | media-side；外部视频 adapter 协议，当前尚未接真实供应商 | 只读安全人物外观、observable response/expression | `talking_head_request.schema.json` | 改为 trigger 后稀疏生成；禁止 latent/threshold/答案泄漏 |
| `counterfactual_action_generation_v1` | benchmark construction；`ModelCandidateGenerator` | 只读真实 checkpoint 的 public observation | string array，经 caller 转 `{"text": ...}` | 移除策略标签与显然好/坏二分；只生成局部可行动自由文本 |
| `t2_shared_observation_v1` | benchmark construction；`ModelCandidateGenerator` | 读两段 public natural histories | inline O* JSON | 强制完全共享 O*；禁止 private state 与 trajectory provenance 泄漏 |
| `local_intervention_validation_v1` | author-side validation protocol | 可读真实 checkpoint private experiment packet | `local_intervention_review.schema.json` | controlled 只保留为局部实验，不再驱动多轮策略 |
| `task_t1_v1` | evaluated-agent-side；T1 baseline/evaluation | 只读 public longitudinal instance | `task_t1_output.schema.json` | 移除作者 effects/oracle；证据 ID 必须可见 |
| `task_t2_v1` | evaluated-agent-side；T2 baseline/evaluation | 只读 A/B history 与相同 O* | `task_t2_output.schema.json` | 明确 O* byte-identical，禁止构建 metadata/private state |
| `task_t3_v1` | evaluated-agent-side；T3 baseline/evaluation | 只读 public checkpoint、2–4 action、horizon | `task_t3_output.schema.json` | 主任务禁止 oracle state/未来分支；所有 option 同 protocol/horizon |
| `task_t4_action_v1` | evaluated-agent-side；`ModelPolicy` 用于自然 rollout/T4 | 只读 policy observation | natural-language action only | 替换旧 policy prompt；不返回分析或策略 label |
| `t4_judge_v1` | validation；T4 judge protocol | 只读 packet 明示的 allowed evidence | `t4_judge_output.schema.json` | 多维评分，不把低冲突当目标；明确 not human GT |
| `human_annotation_v2` | human-facing validation/GT protocol | 只读冻结 annotation packet；author-side 实验必须显式标识 | packet-supplied schema / overlay | simulator candidate 仅是假设；人类标签、证据、不确定性独立记录 |

## Conceptual problems 与修复

删除了旧版 direct scenario generation、story world、合并 appraisal/update、旧 response、旧 memory、旧 T1/T2/T3/T4、policy action 和 human annotation prompt。同步删除 action interpreter、controlled policy、template response、world benchmark schema 与旧任务合同。`prompt_check.md` 第 16 节关于 escalation/neutral/repair 三种多轮 policy 的旧建议与更新后的 `revision.md` 冲突；按较新的 revision，三类固定策略不进入生成 pipeline，只保留真实 checkpoint 上的局部自由文本 intervention。

所有当前 prompt 已采用 task-first、quality/constraints 居中、output/schema-last。Appraisal → semantic state update → deterministic numeric mapping → response 的顺序已在代码和测试中固定。Source quality → normalization → initial state 的顺序也已在 CLI、schema 和文档中固定。

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

新增 narrative structure、blueprint、source quality、candidate initial state、T1/T2/T3 输出、T4 judge、observable expression、Talking Head request 与 local intervention review schemas。更新 canonical scenario/trajectory schema，删除 action effects/action ID 合同。更新 `scenario_sources.py`（含 `extract-structure`）、`environment/appraisal.py`、`environment/state_updater.py`、`environment/response_generator.py`、`environment/memory.py`、`offline/candidate_generation.py`、`policies/model_policy.py` 与 `scripts/run_pipeline.py`。

## 未决设计问题

- 20 个现有 scenario 的 provenance/quality/S0-D0 仍需真人审核，不得自动批准。
- task 输出概率和为 1 需要运行时 validator；JSON Schema 只能约束单值范围。
- `observable_expression_v1` 与 `talking_head_generation_v1` 已固定协议，但真实视频 provider、资产存储和人工连续性审核尚未接入。
- human annotation 的具体字段按 T1/T2/T3 packet supplied schema 冻结；正式标注平台与 adjudication 尚未执行。
- T4 judge 与人类评分的相关性/一致性尚未建立。
