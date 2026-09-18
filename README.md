# SocialFlux

SocialFlux 是一个用于长期社会互动推理的 stateful benchmark pipeline。它用同一套私有状态环境生成自然模型轨迹、构建 T1/T2/T3 离线任务，并提供 T4 在线交互；正常生成过程不含预定义 repair/neutral/escalation 策略，也不查 action transition table。

当前唯一生产目录是 `configs/scale300_v1/scenarios`，共 300 个 scenario。每场景生成 3 个 Fable seed 候选；offline rollout 最多 20 轮，10–20 轮自然结束才进入主候选。旧 20 场景、六轮轨迹和历史 task 只保留为诊断或审计材料。

## 核心约束

全部核心约束、轮数、状态更新、信息边界、任务来源、验收和发布条件以 [DESIGN_CONTRACT.md](DESIGN_CONTRACT.md) 为准；本 README 只提供运行入口。

**每次运行前必读：**运行 rollout、T1–T4 构造、质量筛选、媒体生成或评测之前，先阅读 [代码结构与修改纪律](DESIGN_CONTRACT.md#21-每次运行前必读代码结构与修改纪律)。不得用场景特判、词面规则、重复 wrapper 或平行入口继续堆补丁；本批代码、prompt、schema 和配置确认后再冻结运行。

**Git 交付：**每个通过相关检查的完整工作单元都要及时 commit 并 push
当前工作分支；提交粒度、message、secret/artifact 排除、远端同步和禁止
改写共享历史的规则见
[Git 提交与推送纪律](DESIGN_CONTRACT.md#22-git-提交与推送纪律)。

## 快速检查

```bash
python -m pipeline preflight
python scripts/scenario_docs.py --check
python scripts/check_markdown_links.py
python -m unittest discover -s tests -v
python -m unittest discover -s web/tests -v
python scripts/verify_gate_md.py
```

启动人工标注工作台：

```bash
python -m web.server --host 127.0.0.1 --port 8000
```

服务器本机访问 `http://127.0.0.1:8000/`。远程浏览先执行 `ssh -L 8000:127.0.0.1:8000 <host>`，再打开同一地址。网站同时展示研究者可见的完整 persona、hidden intention、S0/D0、三条视频阈值，以及被测模型实际收到的角色身份、explicit goal、公开历史和固定 prompt 实参；私有字段排除清单也直接可见。旧 184 条六轮 rollout 与 180 个历史开发 Task 继续作为人工审计材料展示，但均不代表新版 10–20 轮主候选通过。标注草稿仅保存在浏览器并可导出 JSON。

## 运行真实 rollout

当前 frontier API 角色统一定义在
[`configs/model_routes.frontier_api.json`](configs/model_routes.frontier_api.json)：
Scenario、policy、Structured Appraisal、Response、T1–T4 构造/答案与质量复核
全部使用 `claude-fable-5`，但每个语义 role 仍建立独立请求和 provenance。
历史多模型对照保留为实验记录；模型语义复核不等于人工验收。
业务代码不得再次写死模型名。

AutoDL 的非敏感 Chat Completions endpoint 已绑定在路由文件中，并配置为绕过服务器
HTTP 代理直连。运行前只在进程
环境中设置密钥；不要将密钥写入 JSON、shell 脚本、日志或 Git：

```bash
export AUTODL_API_KEY='YOUR_API_KEY'
```

服务器后台任务若没有继承交互 shell 环境，会自动回退到权限为 600 的
`/root/.config/socialflux/autodl_api_key`；该文件位于仓库外。

板块级选择证据见 [api.md](api.md) 和
[`2026-09-17_autodl_board_model_selection.md`](reports/experiments/2026-09-17_autodl_board_model_selection.md)。

唯一公开入口是 `python -m pipeline`。正式运行顺序与代码阶段一致：

```bash
# 300 scenarios、3 seeds、Fable-only 路由预检
python -m pipeline preflight

# Gate 1 人工冻结后生成 300×3 raw candidates
python -m pipeline rollout \
  --review-registry reviews/scale300_scenario_review.json \
  --output data/formal/raw --workers 4 --retry-limit 3 --resume

# Gate 2 环境证据通过后完成 Gate 3 审计、筛选并物化 canonical pool
python -m pipeline gate3 \
  --raw-root data/formal/raw \
  --stage formal \
  --review-registry reviews/scale300_scenario_review.json \
  --environment-evidence data/formal/environment_evidence \
  --judgments data/formal/judgments.json \
  --history-evidence data/formal/history.json \
  --output data/formal/gate3_report.json \
  --selected-root data/formal/selected

# Gate 3 完成 canonical selection 后构建 T1/T2/T3
python -m pipeline tasks \
  --rollout-root data/formal/selected \
  --review-registry reviews/scale300_scenario_review.json \
  --environment-evidence data/formal/environment_evidence \
  --gate3-report data/formal/gate3_report.json \
  --output data/formal/tasks

# T4 使用同一 environment runtime
python -m pipeline t4 --output data/formal/t4

# Gate 4 与最终发布审计
python -m pipeline audit \
  --rollout-stage selected \
  --raw-root data/formal/selected \
  --pipeline-output data/formal/tasks \
  --review-registry reviews/scale300_scenario_review.json \
  --environment-evidence data/formal/environment_evidence \
  --judgments data/formal/judgments.json \
  --history-evidence data/formal/history.json \
  --human-task-review data/formal/gate4_review.json \
  --output data/formal/four_gate_report.json --strict
```

所有语义请求都由 `pipeline/runtime.py` 通过版本化 route table 交给 `claude-fable-5`；Python 只负责编排、确定性状态更新、校验和产物写入。`--allow-unreviewed` 只用于显式诊断，不能产生正式数据。

场景创建、审核顺序、产物位置见 [Pipeline](docs/architecture/PIPELINE.md)，架构不变量见 [Architecture](docs/architecture/ARCHITECTURE.md)，完整约束见 [DESIGN_CONTRACT](DESIGN_CONTRACT.md)，prompt 审计见 [Prompt Audit](docs/prompts/PROMPT_AUDIT.md)。完整导航与论文证据入口见 [文档索引](docs/README.md)。

正式三 seed 生成、Judge、history evidence、每场景 1 条 canonical trajectory 与 Gate 4 两人同样本抽查顺序见 [Formal Rollout Runbook](docs/operations/FORMAL_ROLLOUT_RUNBOOK.md)，约束原文见 [gate.md](docs/protocols/gate.md)。
正式发布必须以 `scripts/verify_gate_md.py --strict` 返回成功为准；当前真人 Gate 1–4 与正式 GT 尚未齐备，因此开发数据不能标为 final benchmark。

## 目录

- `pipeline/`：Gate 1–4 阶段顺序、Scale300 preflight、Fable-only runtime 与唯一公开 CLI。
- `configs/scale300_v1/scenarios/scenario_NNN/`：当前 300 个 canonical candidate JSON 及同名可读文档。
- `environment/`：唯一状态环境、appraisal、state update、response、memory、termination 与 multimodal trigger。
- `rollout/`、`offline/`：自然轨迹与 T1/T2/T3 构建。
- `evaluation/`、`annotation/`：九项验收、泄漏审计与人工标注 overlay。
- `prompts/`：全部运行时固定模型 prompt、说明及 SHA-256 manifest。
- `docs/`：架构、协议、操作手册、Prompt 审计、设计输入与论文证据索引。
- `reports/`：当前结论级实验报告；中间轮次保留在 `reports/experiments/archive/`。
- `schemas/`：scenario、blueprint、质量报告、初始状态与 trajectory 合同。
- `web/`：scenario/rollout/task 人工标注工作台；浏览器本地草稿与 JSON 导出。
- `build/`：可再生且默认不提交的聚合产物。
