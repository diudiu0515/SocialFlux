# S0 / D0 人工冻结说明

## S0 与 D0 是什么

- **S0（initial state）**：environment character 在第 0 轮的潜在人物状态。它按 scenario 选择少量 emotion、motivation 和 relationship 变量，并使用统一的 0–10 数值范围。
- **D0（initial dynamics）**：第 0 轮的互动局势，不属于人物人格本身，例如 escalation risk、goal failure risk、schedule pressure、negotiation open。

S0/D0 共同决定 rollout 的起点，但不规定后续 action 的效果，也不是任务答案。

## “人工冻结”是什么意思

candidate_pending_human_freeze 表示模型或作者已经提出候选值，但真人尚未签字。人工冻结要求 reviewer 对照故事、persona、目标、权力结构、历史与信息不对称，逐项确认：

1. 所选变量确实与该 scenario 有关，没有把全局 ontology 全塞进去；
2. 每个初值方向和强度有自然语言依据；
3. S0/D0 没有预先写入某个策略的效果或标准答案；
4. 初值不过度极端，并且任何 threshold/crossing trigger 在第 0 轮都未激活；
5. 至少两种合理策略仍可能把轨迹带向不同方向；
6. 同一 scenario 的所有 model、policy、seed rollout 使用完全相同的 S0/D0。

确认后，reviewer 记录姓名、UTC 时间、scenario JSON SHA-256 和备注，才可把状态改为 human_frozen。脚本校验通过、模型自评通过或已经生成 rollout，都不能代替真人签字。

同一签名记录还必须填写 Gate 1 的六项 1–5 分真人评分：Social Plausibility、Character Coherence、Trade-off Quality、History Necessity、Interaction Richness、T1–T4 Suitability。Social Plausibility、Trade-off Quality、History Necessity 必须 ≥4，其余必须 ≥3，且总均值必须 ≥4.0；任一未达标不能签为 approved。

## 当前项目状态

20 个 scenario 的 S0/D0 仍是候选值。开发 rollout 可以显式使用 --allow-unreviewed，但产物只能进入开发池；在真人冻结与 source quality approval 完成前，不能发布为正式 benchmark 或 human ground truth。

## 建议审核记录

    {
      "scenario_id": "IA_PIPE_001",
      "reviewer": "真实审核人",
      "reviewed_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
      "scenario_sha256": "冻结时 JSON 的 SHA-256",
      "decision": "approved | revise | rejected",
      "s0_notes": "变量选择与数值依据",
      "d0_notes": "局势变量与数值依据",
      "trigger_notes": "初始不触发与可达性判断"
    }
