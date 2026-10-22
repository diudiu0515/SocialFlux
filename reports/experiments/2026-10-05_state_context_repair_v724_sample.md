# v3.2.24 小样例复查

## 旧结果

`human_confirmed_fixed_set_results.json` 是旧请求的结果：请求正文仍是旧 v3 prompt，不能作为本轮修复后的验证。

## 新请求尝试

曾启动一次 8 例固定集复测，输出为：
`data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/human_confirmed_fixed_set_results_v724.json`。

首例请求已完整返回，但发现固定集 runner 当时没有传入正式环境新增的 `appraisal_context`，因此该首例不计入 v3.2.24 语义结论；其模型判断为 `no_relevant_evidence`、最终 delta 为 `similar`。第二例 provider 请求在超时前未返回，进程已停止，未重跑。

随后已修正 runner：固定集回放现在会从真实历史构造 `current_turn`、`historical_turns`、重复匹配和历史证据上下文；背景过滤也覆盖了 `later records will show` 类型的未来结果句。真实首例的无模型构造检查已确认：当前轮 `t3`、历史轮 2 轮、历史数值更新字段独立保存、未来结果被移除。

因此目前没有可宣称通过的新版模型小集结果；下一次模型复测必须使用修正后的 runner，且只运行预定一轮。
