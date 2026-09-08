# SocialFlux

SocialFlux 是一个用于长期社会互动推理的 stateful benchmark pipeline。它用同一套私有状态环境生成自然模型轨迹、构建 T1/T2/T3 离线任务，并提供 T4 在线交互；正常生成过程不含预定义 repair/neutral/escalation 策略，也不查 action transition table。

当前代码架构、20 个 scenario bundle（原 10 个保留，新增 10 个影视高层结构启发的原创场景）、版本化固定 prompt、可视化网站和九项验收框架已经迁移到 v2。20 个 scenario 均已完成 Qwen3.5-9B 三 seed 开发 rollout 与 T1/T2/T3 实际提取，共 60 条机器清洗通过的轨迹、180 个结构合格 instance；每个 bundle 都有完整对话和人工抽查 Markdown。每个 scenario 另有两条 EchoMimicV2 Talking Head MP4，共 40 条，经音轨、时长、分辨率与帧率自动验收并可在网站播放。现有 scenario 的质量门、S0/D0 和视频语义观感仍待真人复核，仓库不会把开发产物伪装成正式研究验收结论。

## 核心约束

- action 是任意自然语言文本，不含 action ID 或固定策略类别。
- 离线生成与 T4 共用 `environment.StatefulEnvironment`。
- 状态变化由 persona、相关可观察历史、S_t/D_t 与当前 action 经 appraisal 和 state update 两个独立阶段产生。
- T1/T2/T3 来自自然轨迹 checkpoint；受控操作仅用于局部诊断。
- 多模型只扩大 raw candidate search，不形成最终配额；质量门后 T1/T2/T3 按各自能力权重独立选源，T3 只接受带历史且完整跑通局部分支的 checkpoint。
- narrative-derived 只抽象影视作品的高层社会机制并强制原创化表层内容；它与 synthetic-script 归一化到同一个 scenario schema。
- 模型看不到 hidden intention、latent state、delta、trigger threshold 或未来分支。
- 普通轮次为文本；达到私有阈值时才产生稀疏 Talking Head media specification。

## 快速检查

```bash
python scripts/scenario_docs.py --check
python scripts/check_markdown_links.py
python -m unittest discover -s tests -v
python -m unittest discover -s web/tests -v
python scripts/run_acceptance.py
python scripts/evaluate_instance_quality.py --pipeline-output build/pipeline_v2
python scripts/run_quality_gates.py \
  --scenario-root configs/scenarios \
  --pipeline-output build/pipeline_v2 \
  --raw-root data/formal/raw \
  --output build/quality_gates/report.json \
  --strict
python scripts/verify_gate_md.py
```

启动人工标注工作台：

```bash
python -m web.server --host 127.0.0.1 --port 8000
```

服务器本机访问 `http://127.0.0.1:8000/`。远程浏览先执行 `ssh -L 8000:127.0.0.1:8000 <host>`，再打开同一地址。网站可视化全部 scenario 情节、S0/D0、视频阈值、自然 rollout 和 180 个 T1/T2/T3 待标注实例，并在 task 卡片显示质量门来源与专项分数；标注草稿仅保存在浏览器并可导出 JSON。

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

场景创建、审核顺序、产物位置见 [Pipeline](docs/architecture/PIPELINE.md)，架构不变量见 [Architecture](docs/architecture/ARCHITECTURE.md)，完整定义见 [Framework Definition](EmoTree_Framework_Definition_v4.md)，prompt 审计见 [Prompt Audit](docs/prompts/PROMPT_AUDIT.md)。完整导航与论文证据入口见 [文档索引](docs/README.md)。

正式多模型生成、双 Judge、历史干预、骨干敏感性、每场景 1 条 canonical trajectory 选择与三人 GT 顺序见 [Formal Rollout Runbook](docs/operations/FORMAL_ROLLOUT_RUNBOOK.md)，约束原文见 [gate.md](docs/protocols/gate.md)。
正式发布必须以 `scripts/verify_gate_md.py --strict` 返回成功为准；当前真人 Gate 1/2/4 与正式 GT 尚未提供，因此开发数据不能标为 final benchmark。

## 目录

- `configs/scenarios/scenario_NNN/`：canonical JSON、同名自然语言说明，以及 `rollouts/` 内的本地轨迹、完整对话和 T1/T2/T3 人工抽查包。
- `environment/`：唯一状态环境、appraisal、state update、response、memory、termination 与 multimodal trigger。
- `rollout/`、`offline/`：自然轨迹与 T1/T2/T3 构建。
- `evaluation/`、`annotation/`：九项验收、泄漏审计与人工标注 overlay。
- `prompts/`：全部运行时固定模型 prompt、说明及 SHA-256 manifest。
- `docs/`：架构、协议、操作手册、Prompt 审计、设计输入与论文证据索引。
- `reports/`：当前结论级实验报告；中间轮次保留在 `reports/experiments/archive/`。
- `schemas/`：scenario、blueprint、质量报告、初始状态与 trajectory 合同。
- `web/`：scenario/rollout/task 人工标注工作台；浏览器本地草稿与 JSON 导出。
- `build/`：可再生且默认不提交的聚合产物。
