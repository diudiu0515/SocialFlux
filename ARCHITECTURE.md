# SocialFlux 系统架构

更新时间：2026-08-31

## 1. 总体数据流

~~~text
Scenario JSON
    |
    v
StatefulEnvironment
    +--> Initialization: frozen initial state / dynamics
    +--> Memory: observable history retrieval
    +--> Appraisal + State Update: private transition
    +--> Semantic Delta Mapper: -3..3 -> bounded 0..10 values
    +--> Response Generator: observable response
    +--> Termination: threshold / priority / horizon
    |
    v
RolloutRunner + TrajectoryLogger
    |
    +--> complete trajectory with private transition fields
    +--> Offline builders
            +--> T1 state tracking
            +--> T2 history-sensitive merge
            +--> T3 counterfactual choice effect
    |
    v
Annotation overlay -> metrics / leakage / environment validity
~~~

## 2. 目录职责

| 目录 | 职责 |
|---|---|
| environment/ | 状态、记忆、appraisal、response、终止和环境循环 |
| providers/ | 统一 provider 接口及四类模型适配器 |
| policies/ | ControlledPolicy 和 ModelPolicy |
| rollout/ | 单策略、多策略、counterfactual、日志和 manifest |
| offline/ | 从私有 rollout 生成不含作者机制的公开候选 |
| annotation/ | 人工标注 overlay、聚合和导出 |
| evaluation/ | 环境有效性、指标和泄漏审计 |
| prompts/ | 所有固定模型 prompt、版本和 hash manifest |
| schemas/ | Phase-A scenario/trajectory schema 校验 |
| worlds/ | 交互 Story World、剧情树和 world 级任务实例 |
| tasks/ | T1/T2/T3 任务定义、输出 schema 和标注 schema |
| demo/ | 独立的 on-policy 人机交互展示层 |
| build/ | 可再生的 pipeline 和 benchmark 聚合产物 |

## 3. 隐私边界

环境内部维护 latent state、hidden intention、traits、appraisal、action effects 和 internal log。participant observation 只包含 observable cue、external signal、公开对话和可见轮次；研究视图才允许读取调试信息。

Offline T1/T2/T3 实例只保留模型应该看到的 history、scene、candidate options 和 target specification。作者设定、private effects、hidden intention 和内部 appraisal 不进入候选输入。evaluation/leakage.py 对该边界做自动检查。

## 4. Prompt 版本策略

prompts/ 是固定 prompt 的唯一源。调用方通过 prompts/loader.py 读取，loader 根据 prompts/manifest.json 校验 SHA-256。修改 prompt 时：

1. 新增带版本号的 Markdown 文件；
2. 更新 manifest；
3. 修改调用方的 prompt ID；
4. 重建受影响的 benchmark/build 产物；
5. 运行 tests、demo/tests 和 interactive_benchmark/tests。

shared/interactive_story_generation_prompt.md 仅保留为旧链接兼容入口。

## 5. 运行模式

### Controlled validation

scripts/run_pipeline.py 使用确定性 ControlledPolicy 运行所有场景，用于检查 action sensitivity、history sensitivity、state bounds、termination、counterfactual 和 leakage。

### Model-backed execution

ModelPolicy、ModelMemoryModule、ModelStateUpdater、ModelResponseGenerator 均通过 provider.complete() 工作。API key 只能由本地环境变量或外部 secret manager 注入，不能写入 scenario、prompt、build 或 Git 仓库。

### Interactive demo

demo/server.py 是展示层，不替代正式 benchmark pipeline。Participant、Researcher、Replay 使用不同视图；研究视图通过 EMOTREE_DEBUG_TOKEN 保护，公网部署还需要反向代理认证。

## 6. 可再生构建

完整 pipeline：

~~~bash
python -m scripts.run_pipeline   --scenarios configs/scenarios   --output build/pipeline_v1
~~~

Interactive benchmark：

~~~bash
python interactive_benchmark/scripts/convert_interactive_to_benchmark.py   worlds/IA001/story.json worlds/IA002/story.json   -o build/interactive_benchmark_v0.2/instances.jsonl
~~~

测试：

~~~bash
python -m unittest discover -s tests -v
python -m unittest discover -s demo/tests -v
python -m unittest discover -s interactive_benchmark/tests -v
~~~
