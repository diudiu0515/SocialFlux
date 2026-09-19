# SocialFlux

SocialFlux 是一个长期社会互动推理 benchmark pipeline。当前实现用同一套私有状态环境生成自然模型轨迹、构建 T1/T2/T3 离线任务，并以同一 runtime 执行 T4 在线评测。

当前不保留旧 300 场景为活跃 catalog。旧 Scale300 与 Qwen 生成产物已移到本地忽略目录 `archives/legacy_qwen_scale300_20260919/`，不参与运行或提交。现在先用 GPT 做小规模端到端设计审计；闭环通过后，再扩展 Claude 主批次。无论模型和批次大小，每个通过 Gate 1 的场景只生成 1 条自然 rollout，不做 3 seed 或 best-of-N。

## Pipeline

```text
N 个 Scenario 候选
→ Gate 1：Scenario / S0-D0 人工冻结
→ 每场景 1 条自然 rollout
    Policy 自由文本 action
    → Appraisal LLM
    → Python 确定性状态更新
    → Response LLM
    → Ledger / 下一轮 observation
→ Gate 2：Environment validity
→ Gate 3：Trajectory 准入或淘汰
→ T1 / T2 / T3 构建；T4 在线评测
→ Gate 4：任务实例与答案抽查
```

GPT 批次用于发现设计、任务构造和评分漏洞，不替代后续 Claude 主数据。失败 rollout 计入真实产率，不补抽另一个 seed。

全部不可变约束以 [DESIGN_CONTRACT.md](DESIGN_CONTRACT.md) 为准；运行顺序见 [Pipeline](docs/architecture/PIPELINE.md)，运行时边界见 [Architecture](docs/architecture/ARCHITECTURE.md)。

## 人工 Gate 1 网站

启动服务：

```bash
python -m web.server --host 127.0.0.1 --port 8000
```

本机打开：

```text
http://127.0.0.1:8000/gpt50
```

远程服务器先建立隧道，并保持终端不关闭：

```bash
ssh -p 22 -L 8000:127.0.0.1:8000 root@SERVER_IP
```

然后在本机浏览器打开同一地址。根路径 `/` 也会进入 GPT Gate 1。浏览器草稿不是正式签名，换浏览器或清缓存前必须导出 JSON。

## 运行与验证

场景批次必须有独立目录和 manifest，Gate 1 记录必须绑定最终 scenario 文件 SHA-256。正式命令统一从 `python -m pipeline` 进入：

```bash
python -m pipeline preflight --scenarios path/to/frozen-scenarios
python -m pipeline rollout --scenarios path/to/frozen-scenarios --review-registry path/to/gate1.json --output data/formal/raw --workers 4 --retry-limit 1 --resume
python -m pipeline gate3 --scenarios path/to/frozen-scenarios --raw-root data/formal/raw --stage formal --review-registry path/to/gate1.json --environment-evidence data/formal/environment --judgments data/formal/judgments.json --history-evidence data/formal/history.json --output data/formal/gate3.json --selected-root data/formal/selected
python -m pipeline tasks --scenarios path/to/frozen-scenarios --rollout-root data/formal/selected --review-registry path/to/gate1.json --environment-evidence data/formal/environment --gate3-report data/formal/gate3.json --output data/formal/tasks
python -m pipeline t4 --scenarios path/to/frozen-scenarios --output data/formal/t4
python -m pipeline audit --scenario-root path/to/frozen-scenarios --rollout-stage selected --raw-root data/formal/selected --pipeline-output data/formal/tasks --review-registry path/to/gate1.json --environment-evidence data/formal/environment --judgments data/formal/judgments.json --history-evidence data/formal/history.json --human-task-review data/formal/gate4.json --output data/formal/four_gate_report.json --strict
```

常用检查：

```bash
python scripts/check_markdown_links.py
python -m unittest discover -s tests -v
python -m unittest discover -s web/tests -v
python scripts/verify_gate_md.py
```

## 目录

- `pipeline/`：Gate 1–4 阶段顺序与公开 CLI。
- `environment/`：Appraisal、确定性状态更新、Response、Ledger 和终止逻辑。
- `rollout/`、`offline/`、`tasks/`：自然轨迹与 T1/T2/T3/T4。
- `evaluation/`、`annotation/`：质量门与人工标注合同。
- `prompts/`、`schemas/`：版本化 prompt 与数据合同。
- `configs/scale300_v1/CLAUDE_AUTHORING.md`：保留的 Claude 场景创作合同；不代表存在活跃 300 场景。
- `web/`：Gate、任务、示例和 Talking Head 人工审核页面。
- `media/talking_head/`：保留的 Talking Head 清单与资产。
- `archives/`：本地可恢复历史归档，默认不进入 Git。

## Git 提交纪律

每个通过相关检查的完整工作单元都应及时 commit 并 push 当前分支。只提交本工作单元相关文件；不得提交密钥、浏览器草稿、模型原始大产物或 `archives/`。提交信息使用 `type(scope): imperative summary`，例如 `feat(web): add GPT Gate 1 review`、`chore(data): archive legacy Qwen outputs`。不要改写共享分支历史；详细规则见 [Git 提交与推送纪律](DESIGN_CONTRACT.md#22-git-提交与推送纪律)。
