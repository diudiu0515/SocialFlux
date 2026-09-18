# API model role benchmark（2026-09-17）

## 结论

本轮在不修改 prompt、validator、状态更新或任务定义的条件下，对六个 API 模型进行了
156 个组件样本、共 188 次 HTTP 请求尝试。结果属于开发模型对照与 Codex 语义复核，不是人工验收，也不是
正式 benchmark 结论。

选定路由：

| 角色 | 模型 | 选择依据 |
| --- | --- | --- |
| Policy | DeepSeek-V4-Pro-0813 | 6/6 结构成功；在 IA019 上未自行声称持有资金流水、会议排除等关键新事实，事实边界最佳。 |
| Structured Appraisal | Qwen3.8-Max | 6/6；提案、请求、承诺和状态证据绑定整体最准确，保留原路由。 |
| Response | DeepSeek-V4-Pro-0813 | 6/6；在 IA003 和 IA013 上比其他候选更谨慎，ledger 事件更贴近文本。 |
| T2 task construction | DeepSeek-V4-Pro-0813 | 2/2；两组改编历史最简洁，较少提前泄露或新增关键事实。 |
| T2/task answer | DeepSeek-V4-Pro-0813 | 2/2；双侧证据、差异方向和不确定性解释优于更快候选。 |
| Semantic precheck | MiniMax-M3 | 4/4，平均 8.14 秒；能检出 IA001、IA009 的明显空转，且未误拒 IA003。 |

## 结构成功率与平均延迟

以下成功只表示完成该角色的既有 schema/validator，不表示语义合格。

| 角色 | Qwen3.8-Max | DeepSeek-V4-Pro-0813 | Kimi-K3 | Kimi-K2.6 | MiniMax-M3 | Qwen3.5-397B-A17B |
| --- | --- | --- | --- | --- | --- | --- |
| Policy（6） | 6/6 · 3.35s | 6/6 · 13.95s | 1/6 · 7.30s | 6/6 · 2.16s | 6/6 · 4.69s | 6/6 · 7.62s |
| Appraisal（6） | 6/6 · 13.84s | 6/6 · 135.47s | 2/6 · 49.38s | 6/6 · 14.71s | 6/6 · 8.57s | 6/6 · 20.75s |
| Response（6） | 6/6 · 11.98s | 6/6 · 42.96s | 0/6 | 6/6 · 13.19s | 4/6 · 17.20s | 5/6 · 25.12s |
| T2 construction（2） | 2/2 · 18.10s | 2/2 · 145.00s | 0/2 | 2/2 · 16.66s | 2/2 · 11.18s | 2/2 · 21.53s |
| T2 answer（2） | 1/2 · 46.71s | 2/2 · 239.85s | 1/2 · 238.06s | 1/2 · 65.29s | 2/2 · 18.65s | 1/2 · 57.88s |
| Semantic precheck（4） | 4/4 · 11.22s | 4/4 · 91.59s | 2/4 · 93.97s | 4/4 · 13.74s | 4/4 · 8.14s | 4/4 · 12.91s |

原始逐样本输出、失败和实际请求数保存在
`build/api_model_role_benchmark_v1/results.json`。失败未隐藏；Kimi-K3 在较长负载上频繁
返回 HTTP 400，MiniMax Response 有 JSON 转义失败，Qwen3.5 Response 在 IA013 未通过
直接台词检查。现有结果文件的成功记录保存了 147 次请求；旧异常路径未写入
`request_count`，其余 41 次依据 20 个 HTTP 400 单次尝试、三个四次结构重试和三个三次
结构重试从错误记录重建。脚本现已修复，后续错误记录会直接保存真实 `_call_index`。

## 语义发现

- 单纯换模型不能根治 IA019：六个 Response 候选都不同程度补造了授权材料、法务流程、
  股东权利或资金事件。DeepSeek 相对谨慎，但仍不能据此宣称制度事实边界已解决。
- Appraisal 不宜追求最低延迟。MiniMax 虽快，但出现漏掉提案、把坚定承诺判为条件承诺、
  或无证据改变情绪等问题；因此继续使用 Qwen3.8-Max。
- MiniMax 的 T2 答案虽然 2/2 通过 schema，第二组把若干表达解释成“复读”和行动降级，
  证据弱于 DeepSeek；因此不以速度替代答案质量。
- Semantic precheck 的四例中，没有模型识别 IA019 的无依据制度细节。该 Judge 只能作为
  机器预检，不能替代全文语义复核或人工 Gate。

## 端到端验证

IA003、IA019 的六条完整对照已在取得明确外发授权后完成，共产生 169 次实际请求。
生成层面为一条主候选、三条自然短轨迹和两条结构失败；全文语义复核后，仅两条 IA003
短轨迹可接受，主窗口合格数为 0。完整结果和最终路由判断见
[API model integrated probe](2026-09-17_api_model_integrated_probe.md)。
