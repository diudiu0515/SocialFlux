# SocialFlux Project Progress

更新时间：2026-09-19

## 当前主线

- 唯一生产入口：`python -m pipeline`；网站入口用于人审，不代替 CLI Gate。
- 先用 GPT 小规模批次完成 Scenario → 单条 rollout → T1/T2/T3/T4 → score 的端到端设计审计，再扩大 Claude 主批次。
- 每个通过 Gate 1 的场景只生成 **1 条**自然 rollout；不做 3 seed、best-of-N 或模型配额。
- 旧 Qwen 产物与旧 300 场景不再是活跃数据。Claude 新批次不依赖旧 20/100/200/300 catalog。
- Policy 输出自由文本 action；Environment 固定为 Appraisal LLM → Python 确定性状态更新 → Response LLM → Ledger/observation。

## Gate 状态

| Gate | 当前状态 | 下一步 |
|---|---|---|
| Gate 1 | pending human | 在网站逐场景审核并冻结 Scenario、initial state；runtime dynamics seed 仅机器校验；JSON 变化后旧 hash 自动失效 |
| Gate 2 | pending | 对已冻结场景运行 Environment Validity E1–E9，并抽样人工复核 |
| Gate 3 | pending | 对每场景唯一自然 trajectory 做准入/淘汰和 canonical confirmation |
| Gate 4 | pending | 构建 T1/T2/T3、运行 T4，并对任务实例与机器建议答案做人审抽查 |

当前没有可发布 benchmark；机器 proposal、浏览器草稿和自动 judge 都不能冒充人工签名或 human GT。

## 人工与媒体边界

- Web 审核页面、Gate 合同、任务页面和导出能力保留。
- 旧 Talking Head 资产、归档副本、本地模型和本地生成工具已永久删除。
- 媒体 trigger、observable-expression 协议、prompt/schema、受限路由和审核框架保留，等待外部 API 接入。
- 外部 API 产生新媒体后，必须重新完成身份连续性、音画同步、语音自然度、表达一致性和信息效用审核。

## 当前操作

```bash
python -m web.server --host 127.0.0.1 --port 8000
python -m pipeline preflight
python -m unittest discover -s tests -v
```

先完成人工 Gate 1；未冻结的场景不得进入正式 rollout。
