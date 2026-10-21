# T4 首次媒体回应修复与原因核验

已修复首次视频事件产生后立即自然结束、模型因此没有后续观察机会的问题。新版规则只调整该轮的自然结束判定；真实状态、触发阈值及原有结果保留。
原因统计来自 2026-10-20T18:42:11+08:00 的逐场景快照；主批次继续使用自己的冻结代码。

**未获得成功媒体输入的原因**

| 原因 | 视频条件数 |
|---|---:|
| 第一轮完成前调用失败，未到触发环节 | 12 |
| 视觉能力探测未通过，未运行视频轨迹 | 33 |
| 自然结束轮才触发，缺少后续模型调用 | 6 |
| 已触发，但媒体请求失败 | 2 |
| 已保存轮的状态未变化，未达到触发条件 | 1 |
| 尚无完整轮，不能判定不触发 | 1 |
| 尚未启动 | 23 |

6 条终局触发轨迹是 GPT 的 002、014、019、026 和 Claude 的 024、031。它们第一轮已经触发，随后自然结束；并非阈值未达到。
Claude 029 第一轮所有 state 数值均未变化，所以没有事件；第二轮环境 state 调用又失败。该案例保留未触发事实。第一轮完成前失败的案例尚未走到事件生成环节；接口超时、流错误、HTTP 502 不能通过放宽状态阈值消除。
另两条已触发但媒体请求没有成功的记录：Claude 027 的 policy 请求超时，GPT 030 的 policy 请求被上游以不支持 seed 参数拒绝。DeepSeek 是当前接口的视觉探测未过。尚未启动和未纳入的场景分别标识。
具体逐场景原因和失败角色见 [CSV](2026-10-20_t4_multimodal_exposure_scenes.csv)；完整覆盖见 [审计报告](2026-10-20_t4_multimodal_exposure.md)。

**修改后的规则**

新版本为 `media_completion_policy: first_event_response_v1`。首次真实视频事件产生、资产可用且本轮原本要自然结束时，保留下一轮回应机会。文字和视频两条件的环境采用同一规则；文字请求继续只有文字。后续视频事件不会再次延长对话，显式场景停止和 20 轮上限优先。
触发阈值仍是初始状态 S0±1，未变化的 S0 不触发。未改写状态数值、模型输出、原始轨迹或已完成成绩。新日志 `media_completion_guard` 记录原结束判断、延后原因及下一轮位置，不进入模型文字输入。
规则默认关闭，只有新版配置启用。运行中的 parallel33 使用 build 下的独立 runtime，继续按原协议运行；新旧协议结果分开分析。

**验证结果**

- 70 项相关测试通过，覆盖真实环境循环中的文字／视频隔离、首次和延后触发、状态不变、默认规则、硬上限和显式停止。
- 将上述 6 条保存轨迹的结束判定代入新规则，6/6 都会保留第 2 轮回应机会；全部源文件 SHA 保持不变。此检查只验证结束逻辑，不是新增模型测试或能力收益。
- 正式入口的 prepare-only 校验通过：6 场景 × 2 个模型 × 2 条件，共 24 个计划项。API 调用数为 0。
- [机器验证记录](2026-10-20_t4_media_completion_fix.json)保存来源哈希和逐例结果。

**独立验证配置**

[新版配置](../../configs/gpt50_experiment/t4_multimodal_experiment.first_media_response_v1_20261020.json) · [已保存计划](../../build/t4_first_media_response_v1_20261020/run/plan.json) · [协议说明](../../docs/protocols/online_multimodal_v2.md)

目标场景是已发现结束时机问题的六个场景，用于机制验证，不是随机性能样本。配置包括 GPT、Claude，双条件同规则，最多 1200 次请求预算及健康检查；尚未运行真实补测。

本地校验命令：

```bash
python -m unittest tests.test_t4_media_completion tests.test_multimodal tests.test_t4_contract tests.test_t4_experiment_cohort tests.test_t4_route_distribution tests.test_t4_exposure_audit tests.test_model_environment
python scripts/run_t4_multimodal_experiment.py --config configs/gpt50_experiment/t4_multimodal_experiment.first_media_response_v1_20261020.json --output build/t4_first_media_response_v1_20261020/run --prepare-only
```
