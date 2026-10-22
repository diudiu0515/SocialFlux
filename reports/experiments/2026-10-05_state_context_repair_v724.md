# State context repair v3.2.24

本轮只做工程边界修复，不新增场景特例或重跑模型样例。

## 修复

- 动作在 `_begin_turn` 定稿后才生成 `duplicate_evidence_matches`；匹配只记录当前动作与历史 evaluated-agent 动作的表面匹配。
- state/interaction 两路 appraisal 共享同一份更新前 `appraisal_context`，显式分开 `current_turn`、`historical_turns`、`latest_unanswered_question`。
- `state_evidence_history` 保存历史语义证据，`prior_numeric_update` 单独保存历史数值结果；后者不参与重复判定。
- v3/v4 state prompt 删除旧的“慢变量本轮可能不更新”规则，统一为有效新增证据立即产生最小方向性更新，强度只决定幅度。
- 公共背景、初始 ledger 和响应背景移除尚未发生的结果性句子，保留未来安排。例如保留“周一发布/公开”，删除“周一后来确认”。
- 运行修订绑定为 `v3.2.24`；旧 v3.2.23 结果和请求正文保留为历史证据。

## 证据

- 无模型上下文审计：`data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/context_contract_audit_v724.json`，全部检查通过。
- v7 接口审计：`data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/interface_consistency_audit_v724.json`，全部检查通过。
- 核心确定性回归：77 tests passed（environment、independent appraisal、calibration、transition contract、multimodal）。

## scale 前状态

候选配置已冻结到 `v3.2.24`，但尚未恢复全量生成。应先用该配置运行预定未看样例和小批量完整轨迹，保留全部请求与原始输出，再按人工审核入口决定放量。
