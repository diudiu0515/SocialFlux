# EmoTree 完整 Pipeline

实现对应框架文档的工程链路：

    Scenario config
      -> StatefulEnvironment
      -> Memory + appraisal/state update
      -> semantic delta mapper
      -> environment response
      -> complete rollout JSON
      -> T1 / T2 / T3 candidate instances
      -> annotation overlay
      -> metrics / leakage / environment validation

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

Provider 支持 OpenAI-compatible、Anthropic、Gemini 和 local/vLLM。没有 API key 时使用 ControlledPolicy 完成环境验证和端到端 smoke test。

## Prompt catalog

所有固定 prompt 统一位于 prompts/，按用途和版本命名，例如 policy_action_v1.md、environment_appraisal_v1.md、task_t1_v0.2.md。prompts/manifest.json 记录每个文件的 SHA-256，prompts.loader 是运行时代码的唯一读取入口，并会校验 hash。

环境 appraisal、memory retrieval、model policy、模型 response、任务转换器和故事生成均从该目录读取；shared/interactive_story_generation_prompt.md 只保留兼容指针。修改 prompt 时新增版本文件、重新生成 manifest、更新调用方的 prompt ID，再运行三套测试。

验收命令：

    python scripts/run_acceptance.py       --scenarios configs/scenarios       --output build/pipeline_v1

当前验收报告位于 build/pipeline_v1/acceptance_report.md 和 acceptance_report.json。工程自动 gate 已通过；Persona Sensitivity、自然语言端到端 Paraphrase Robustness 和 Full Trajectory Plausibility 的研究验收仍未关闭，后两者需要实现/接入对应组件和人工判断。

标注导出入口位于 annotation/overlay.py，指标和泄漏审计位于 evaluation/。旧的 demo/ 保持为人工交互展示层，不承担完整 benchmark pipeline。
