# SocialFlux Documentation Index

该目录是项目文档的统一入口。根目录的 DESIGN_CONTRACT.md 是唯一设计约束入口；本目录保存操作手册、协议、Prompt 说明、论文证据和历史输入。

## 权威入口

- [项目 README](../README.md)：安装、快速检查、网站和目录概览。
- [设计约束与核心机制](../DESIGN_CONTRACT.md)：当前研究对象、运行合同、任务来源、验收和发布条件的唯一权威定义。
- [Project Progress](../PROJECT_PROGRESS.md)：2026-10-10 开发题、网站与正式准入状态。
- [Self Check / TODO](../self_check.md)：不可删除的持续任务清单。

## 架构

- [Architecture](architecture/ARCHITECTURE.md)：模块职责、依赖方向、当前/正式配置、产物分层与清理恢复规则。
- [Pipeline](architecture/PIPELINE.md)：从 scenario 创建到 rollout、任务构建、视频和网站的运行顺序。

## 协议与 Gate

- [Offline T1–T3 选择题协议](protocols/OFFLINE_T1_T3_CHOICE_V1.md)：题型、人物与时间语义、统一答案、证据诊断、生成和评测入口。

- [Rollout Screening Protocol v1](protocols/SocialFlux_Rollout_Screening_Protocol_v1.md)：三态筛选、六维评分、10 项 hard reject、抽审与 freeze 规则。
- [Formal Rollout Strategy](protocols/gate.md)：正式多模型 raw pool 和发布门槛。
- [Data Production Quality Gate](protocols/quality_gate.md)：scenario、rollout 和 T1/T2/T3 的质量合同。
- [Gate Implementation](protocols/GATE_IMPLEMENTATION.md)：上述约束在代码与产物中的映射。
- [Initial State Review](protocols/INITIAL_STATE_REVIEW.md)：initial state 人工冻结与 runtime dynamics seed 机器校验说明。
- [State Transition Standard v3](protocols/STATE_TRANSITION_STANDARD_V3.md)：四 family 的 S0 形状、变量级快慢变化、防趋同规则与 20 轮实现要求。

## 操作手册

- [Active Batch Pipeline](operations/ACTIVE_BATCH_PIPELINE.md)：GPT50/Claude150、当前 offline 题库和网站的实际入口。
- [Formal Rollout Runbook](operations/FORMAL_ROLLOUT_RUNBOOK.md)：通用 Fable 正式路径，Gate 1/2、一场景一条 10–20 轮自然 rollout、Judge/history、Gate 4 与正式 GT 的顺序。
- [Annotation Studio](../web/README.md)：网站运行、素材审核和 T1–T3 标注草稿。

## Prompt

- [Prompt Audit](prompts/PROMPT_AUDIT.md)：每个 Prompt 的调用方、信息权限、输出合同和修订理由。
- [Runtime Prompt Catalog](prompts/RUNTIME_PROMPT_CATALOG.md)：运行时版本化 Prompt 与 manifest 使用方法。
- 所有真正送入模型的固定文本只存放在 [`prompts/`](../prompts/)；设计讨论稿不进入运行时 catalog。

## 论文与实验

- [Paper Evidence Index](paper/PAPER_EVIDENCE_INDEX.md)：论文 Methods、筛选、数据构建和局限性对应的证据位置。
- [Experiment Index](../reports/README.md)：当前结论级报告和中间轮次归档。

## 历史设计输入

[source-notes/](source-notes/) 保存用户给出的 revision、Prompt 检查、Talking Head 与 multimodal 设计稿。它们用于追溯设计决策，不直接覆盖 DESIGN_CONTRACT.md、schema 或代码。若历史设计稿冲突，以 DESIGN_CONTRACT.md、schema/code 和最新实验报告为准；冲突必须显式记录后再实现。

## 整理规则

1. 不删除被论文方法、实验结论、Prompt 版本或审计链引用的 Markdown。
2. 当前结论放在稳定目录；中间实验轮次移入 `reports/experiments/archive/`，不伪装成最终结果。
3. 只有 `_vN.md` Prompt 才能进入运行时 manifest；旧 Prompt 可保留为 legacy，但不得被新 caller 默认加载。
4. 空占位、随机笔记或已确认无引用且没有审计价值的文件才可删除。
