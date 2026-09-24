# SocialFlux Pipeline

当前生产结构与 batch size、模型供应商解耦：

```text
N 个 Scenario 候选
  → Gate 1：Scenario / initial-state 人工冻结
  → 每场景 1 条自然 rollout
      Policy 自由文本 action
      → Appraisal LLM
      → Python 确定性状态更新
      → Response LLM
      → Ledger / 下一轮 observation
  → Gate 2：Environment validity
  → Gate 3：唯一 Trajectory 准入或淘汰
  → T1 / T2 / T3 构建；T4 在线评测
  → Gate 4：任务实例与答案抽查
```

当前先运行 GPT 小规模端到端实验，用来发现 scenario、environment、task 和 score 设计漏洞；审核通过后再扩大 Claude 主批次。旧 Qwen/Scale300 数据已归档，不是 compatibility baseline，也不进入 active pipeline。

## 运行时边界

- 每个批次有独立的 scenario root、manifest、Gate 记录和输出 root。
- 每个 Gate-1-approved scenario 恰好生成 1 条自然轨迹；失败计入产率，不补抽。
- Policy 只输出自由文本 action，不读取 action transition table。
- Appraisal 与 Response 是独立语义调用；Python 在两者之间执行确定性状态更新。
- S 固定为 emotion、behavioral_disposition、relationship、
  consequence_risk 四个 family；每轮必须完整评估全部选中 S/D 变量，未变化项写
  `similar`，不能为了覆盖四维而强制数值变化。
- Ledger 只保存已发生的公开事件、action/response 与下一轮 observation，不暴露 hidden intention、persona、S/D、appraisal 或 delta。
- Policy 可见公开 background、关系/权力/冲突和既有历史；不可见 persona 性格、
  information asymmetry、meaningful choice space 或未来核验结果。
- 模型由版本化 route table 注入，业务模块不得写死 provider/model。
- 浏览器草稿、LLM judge 和机器建议都不能替代真人 Gate 或正式 GT。

## 四个 Gate

| Gate | 阻断条件 | 通过后的产物 |
|---|---|---|
| Gate 1 | scenario 未 approved，或 initial state 未 human_frozen | hash-bound frozen scenario |
| Gate 2 | environment 的 E1–E9 证据不足或失败 | environment-valid trajectory |
| Gate 3 | 唯一轨迹结构、自然结束、语义质量或 history evidence 不合格 | canonical trajectory |
| Gate 4 | T1/T2/T3/T4 实例或答案抽查未通过 | 可发布任务与答案 |

`pending` 不能被程序改成 `passed`。`--allow-unreviewed` 仅用于隔离诊断，不能产出正式数据。

## 批次执行

1. 模型创建完整 canonical scenario JSON。
2. schema/catalog 校验并生成只读文档；校验脚本不得修改语义。
3. 人工 Gate 1 绑定最终 JSON 的 SHA-256，冻结 initial state；runtime dynamics seed 只做机器合同校验。
4. 对已批准场景各运行一个 rollout slot。
5. Gate 2 完成 E1–E9 环境证据（E9 为 fast/medium/slow/context-dependent timescale 审核）；Gate 3 用一个质量审核模型全量主筛唯一轨迹，人工抽检。
6. 仅从 selected root 构建 T1/T2/T3；T4 使用同一 environment runtime。
7. Gate 4 对机器建议进行同样本双人抽查和分歧仲裁。
8. strict audit 通过后才能称为正式发布。

命令参数示例见仓库根 [README](../../README.md)，正式证据格式见 [Formal Rollout Runbook](../operations/FORMAL_ROLLOUT_RUNBOOK.md)，完整约束见 [DESIGN_CONTRACT](../../DESIGN_CONTRACT.md)。
