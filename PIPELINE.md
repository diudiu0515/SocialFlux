# EmoTree 完整 Pipeline

实现对应框架文档的工程链路：

    Scenario config
      -> StatefulEnvironment
      -> Memory + appraisal/state update
      -> semantic delta mapper
      -> environment response
      -> state-triggered observable expression/media spec
      -> complete rollout JSON
      -> T1 / T2 / T3 candidate instances
      -> annotation overlay
      -> metrics / leakage / environment validation

## Scenario 配对文档契约

每个 `configs/scenarios/scenario_*.json` 必须有同名 `.md`。Markdown 由 `scripts/scenario_docs.py` 从 JSON 生成，包含故事初始化、角色目标与隐藏意图、初始 state/dynamics、各 action 的变化方向、默认外显表达、视频触发模式、AND 阈值、cooldown 和采样配置。文档记录源 JSON 的 SHA-256。

    python scripts/scenario_docs.py configs/scenarios/scenario_001.json
    python scripts/scenario_docs.py --check

生成器同时重建 `configs/scenarios/manifest.json`。`run_pipeline` 和 `run_acceptance` 都会拒绝缺失/过期的 scenario Markdown，以及与目录不一致的 manifest。

运行全部 10 个场景：

    python -m scripts.run_pipeline \
      --scenarios configs/scenarios \
      --output build/pipeline_v1

产物包括：

- 每个场景的 rollouts、rollout manifest 和 pipeline manifest；
- 全局 build/pipeline_v1/instances.jsonl；
- T1/T2/T3 候选均不含作者 effects、隐藏意图、appraisal 或内部状态；
- validation/counterfactual_effects.json 保存环境验证用的私有 T3 分支；
- 默认 10 场景、每场景 T1=5、T2=3、T3=4，共 120 条候选；ground_truth_status 明确为 pending_human_annotation，正式 GT 必须由独立人工标注和 adjudication 产生。

模型接入统一使用：

    action = policy.generate(observation)

Talking Head 状态触发配置位于 configs/scenarios/scenario_*.json。环境在 state/dynamics 更新后计算 trigger，再把公开 expression/media 写入 observation，把 trigger event 写入私有 trajectory；当前资产状态为 spec_only，尚未伪造视频文件。

Provider 支持 OpenAI-compatible、Anthropic、Gemini 和 local/vLLM。没有 API key 时使用 ControlledPolicy 完成环境验证和端到端 smoke test。

## Prompt catalog

所有固定 prompt 统一位于 prompts/，按用途和版本命名，例如 policy_action_v1.md、environment_appraisal_v1.md、task_t1_v0.2.md。prompts/manifest.json 记录每个文件的 SHA-256，prompts.loader 是运行时代码的唯一读取入口，并会校验 hash。

环境 appraisal、memory retrieval、model policy、模型 response、任务转换器和故事生成均从该目录读取；shared/interactive_story_generation_prompt.md 只保留兼容指针。修改 prompt 时新增版本文件、重新生成 manifest、更新调用方的 prompt ID，再运行核心 tests、web/tests 和 interactive_benchmark/tests（若保留旧 world 源文件）。

验收命令：

    python scripts/run_acceptance.py       --scenarios configs/scenarios       --output build/pipeline_v1

当前验收报告位于 build/pipeline_v1/acceptance_report.md 和 acceptance_report.json。当前 automated engineering gate 已通过：State 210/210、Persona passed、Paraphrase 30/30、Controlled Policy 10/10、Full Trajectory 10/10 结构+专家预审通过。第 5 项的正式人工语义 review 仍由真实评审者完成。

标注导出入口位于 annotation/overlay.py，指标和泄漏审计位于 evaluation/。web/ 是唯一网站层，只读展示当前 scenario、rollout、状态转移、策略分支和 Talking Head 事件；不维护第二套状态机。
