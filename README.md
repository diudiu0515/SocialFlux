# SocialFlux

SocialFlux 是一个用于长期社会互动推理的 stateful benchmark pipeline。它用同一套私有状态环境生成自然模型轨迹、构建 T1/T2/T3 离线任务，并提供 T4 在线交互；正常生成过程不含预定义 repair/neutral/escalation 策略，也不查 action transition table。

当前代码架构、20 个 scenario bundle（原 10 个保留，新增 10 个影视高层结构启发的原创场景）、21 个固定 prompt、可视化网站和九项验收框架已经迁移到 v2。20 个 scenario 均已完成 Qwen3.5-9B 三 seed 开发 rollout 与 T1/T2/T3 实际提取，共 60 条机器清洗通过的轨迹、180 个结构合格 instance；每个 bundle 都有完整对话和人工抽查 Markdown。每个 scenario 另有两条 EchoMimicV2 Talking Head MP4，共 40 条，经音轨、时长、分辨率与帧率自动验收并可在网站播放。现有 scenario 的质量门、S0/D0 和视频语义观感仍待真人复核，仓库不会把开发产物伪装成正式研究验收结论。

## 核心约束

- action 是任意自然语言文本，不含 action ID 或固定策略类别。
- 离线生成与 T4 共用 `environment.StatefulEnvironment`。
- 状态变化由 persona、相关可观察历史、S_t/D_t 与当前 action 经 appraisal 和 state update 两个独立阶段产生。
- T1/T2/T3 来自自然轨迹 checkpoint；受控操作仅用于局部诊断。
- narrative-derived 只抽象影视作品的高层社会机制并强制原创化表层内容；它与 synthetic-script 归一化到同一个 scenario schema。
- 模型看不到 hidden intention、latent state、delta、trigger threshold 或未来分支。
- 普通轮次为文本；达到私有阈值时才产生稀疏 Talking Head media specification。

## 快速检查

```bash
python scripts/scenario_docs.py --check
python -m unittest discover -s tests -v
python -m unittest discover -s web/tests -v
python scripts/run_acceptance.py
python scripts/evaluate_instance_quality.py --pipeline-output build/pipeline_v2
```

启动只读可视化：

```bash
python -m web.server --host 0.0.0.0 --port 8000
```

浏览器访问 `http://<服务器地址>:8000/`。SSH 环境可用端口转发：`ssh -L 8000:127.0.0.1:8000 <host>`。网站只读展示 scenario、自然轨迹、Talking Head trigger，以及该 scenario 的 T1/T2/T3 人工抽查文档。

## 运行真实 rollout

复制并填写 `configs/rollout_pool.example.json`，把密钥写入配置指定的环境变量，不要把密钥写入 JSON 或提交 Git。scenario 完成人工质量审核与 S0/D0 freeze 后运行：

```bash
python -m scripts.run_pipeline \
  --rollout-config configs/rollout_pool.local.json \
  --output build/pipeline_v2
python scripts/run_acceptance.py \
  --pipeline-output build/pipeline_v2 \
  --output build/acceptance_v2
```

`--allow-unreviewed` 仅允许开发 smoke test，不能产生正式 benchmark 数据。

场景创建、审核顺序、产物位置见 [PIPELINE.md](PIPELINE.md)，架构不变量见 [ARCHITECTURE.md](ARCHITECTURE.md)，完整定义见 [EmoTree_Framework_Definition_v4.md](EmoTree_Framework_Definition_v4.md)，prompt 审计见 [PROMPT_AUDIT.md](PROMPT_AUDIT.md)。

## 目录

- `configs/scenarios/scenario_NNN/`：canonical JSON、同名自然语言说明，以及 `rollouts/` 内的本地轨迹、完整对话和 T1/T2/T3 人工抽查包。
- `environment/`：唯一状态环境、appraisal、state update、response、memory、termination 与 multimodal trigger。
- `rollout/`、`offline/`：自然轨迹与 T1/T2/T3 构建。
- `evaluation/`、`annotation/`：九项验收、泄漏审计与人工标注 overlay。
- `prompts/`：全部固定模型 prompt 及 SHA-256 manifest。
- `schemas/`：scenario、blueprint、质量报告、初始状态与 trajectory 合同。
- `web/`：只读 scenario/trajectory 可视化。
- `build/`：可再生且默认不提交的聚合产物。
