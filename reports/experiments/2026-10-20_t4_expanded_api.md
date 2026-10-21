# T4 扩展模型 API 补测

更新：2026-10-20T23:10:44+08:00（北京时间）。独立补测进程已结束，状态 `completed_with_recorded_outcomes`；已记录 96/96 个候选结果，累计 API 请求 1197/2200。

本轮通过 AutoDL 实测 8 个候选模型，在 002、014、019、024、026、031 六个既有问题场景上进行文字／多模态配对。这是针对结束时机缺陷的诊断样本，不能代表完整 GPT50 的总体能力。

[逐模型场景 CSV](2026-10-20_t4_expanded_api_scenes.csv) · [逐条件 CSV](2026-10-20_t4_expanded_api_episodes.csv) · [调用 CSV](2026-10-20_t4_expanded_api_calls.csv) · [完整审计 JSON](2026-10-20_t4_expanded_api.json)

**模型与实际媒体接收**

| 模型 | 本次时序探测 | 媒体成功场景 / 6 | 视频评分完成 | 有效配对 | 视频条件失败 |
|---|---|---:|---:|---:|---:|
| gpt-6-astra | 视频抽帧 2/2 | 5 | 3 | 2 | 3 |
| claude-fable-5 | 视频抽帧 2/2 | 5 | 3 | 3 | 3 |
| Qwen3.5-397B-A17B | 原生视频 2/2 | 5 | 4 | 3 | 2 |
| qwen3.7-max | 未通过 | 0 | 0 | 0 | 0 |
| qwen3-vl-plus | 原生视频 2/2 | 4 | 3 | 3 | 3 |
| Kimi-K3 | 原生视频 2/2 | 3 | 2 | 2 | 4 |
| GLM-5.3 | 未通过 | 0 | 0 | 0 | 0 |
| DeepSeek-V4.1-Flash | 视频抽帧 2/2 | 5 | 5 | 3 | 1 |

时序探测要求正确回答两组不同颜色顺序。媒体成功只表示含实际图片／视频块的请求返回非空输出，不等于理解情绪线索。视频抽帧条件没有音频；原生视频也尚未单独验证音频理解。

- gpt-6-astra 的 native_video 未通过：返回 {'colors': ['blue', 'red', 'green', 'black']}，预期 ['red', 'green', 'blue', 'yellow']。
- qwen3.7-max 的 native_video 未通过：provider HTTP 400: {"error":{"message":"\u003c400\u003e InternalError.Algo.InvalidParameter: The provided messages input is invalid. The error info is [Unexpected item type in content.].","type":"invalid_request_error","param":"","code":"invalid_parameter_error"}}。
- qwen3.7-max 的 video_frames 未通过：provider HTTP 400: {"error":{"message":"\u003c400\u003e InternalError.Algo.InvalidParameter: The provided messages input is invalid. The error info is [Unexpected item type in content.].","type":"invalid_request_error","param":"","code":"invalid_parameter_error"}}。
- GLM-5.3 的 native_video 未通过：temporal video transport probe failed JSON/schema validation after 1 attempts。
- GLM-5.3 的 video_frames 未通过：返回 {'colors': []}，预期 ['red', 'green', 'blue', 'yellow']。
- DeepSeek-V4.1-Flash 的 native_video 未通过：provider stream was truncated: length。

首次媒体结束规则已在 8 条视频轨迹中实际延后自然结束，其中 8 条随后已有成功媒体调用。这验证回应机会是否被保留，不代表后续环境调用或评分一定成功。

**多模态效果**

仅计算同一批次、同一模型、同一场景的两条完整轨迹，且视频侧必须有成功媒体调用。下表为多模态减文字的核心四维均分差；缺失或失败不填零。恢复维度不适用时保持空值，完整五维统计见 JSON。

| 模型 | 配对数 | 核心四维平均差 | 视频胜 / 平 / 负 |
|---|---:|---:|---|
| gpt-6-astra | 2 | -0.6250 | 0 / 1 / 1 |
| claude-fable-5 | 3 | -2.3333 | 0 / 0 / 3 |
| Qwen3.5-397B-A17B | 3 | -0.4167 | 1 / 0 / 2 |
| qwen3.7-max | 0 | 暂无有效配对 | 0 / 0 / 0 |
| qwen3-vl-plus | 3 | -0.0833 | 1 / 0 / 2 |
| Kimi-K3 | 2 | +1.3750 | 2 / 0 / 0 |
| GLM-5.3 | 0 | 暂无有效配对 | 0 / 0 / 0 |
| DeepSeek-V4.1-Flash | 3 | +0.2500 | 2 / 0 / 1 |

单次随机轨迹可能在首次媒体出现前就分叉，因此这里衡量整条条件路径的效果。样本小且只使用 Claude 自动裁判，尚不能据此认定模型排名或稳定的多模态收益；当 Claude 本身为被测模型时也存在同模型裁判偏差。人工复核材料由每条完成轨迹自动导出。

**六场景投递状态**

| 场景 | gpt | claude | qwen | qwen37 | qwen_vl | kimi | glm | deepseek_flash |
|---|---|---|---|---|---|---|---|---|
| GPT50_002 | 评分✓ 媒1 配对✓ | 失败 媒1 | 评分✓ 媒1 配对✓ | 探测未过 | 失败 媒1 | 失败 未见触发 | 探测未过 | 失败 未见触发 |
| GPT50_014 | 失败 媒1 | 失败 未见触发 | 失败 媒1 | 探测未过 | 失败 未见触发 | 失败 未见触发 | 探测未过 | 评分✓ 媒1 |
| GPT50_019 | 失败 媒1 | 评分✓ 媒2 配对✓ | 评分✓ 媒2 配对✓ | 探测未过 | 评分✓ 媒2 配对✓ | 失败 媒1 | 探测未过 | 评分✓ 媒1 配对✓ |
| GPT50_024 | 评分✓ 媒1 | 评分✓ 媒1 配对✓ | 失败 未见触发 | 探测未过 | 评分✓ 媒1 配对✓ | 评分✓ 媒1 配对✓ | 探测未过 | 评分✓ 媒2 配对✓ |
| GPT50_026 | 评分✓ 媒2 配对✓ | 失败 媒3 | 评分✓ 媒1 | 探测未过 | 评分✓ 媒2 配对✓ | 评分✓ 媒2 配对✓ | 探测未过 | 评分✓ 媒1 配对✓ |
| GPT50_031 | 失败 未见触发 | 评分✓ 媒1 配对✓ | 评分✓ 媒1 配对✓ | 探测未过 | 失败 未见触发 | 失败 未见触发 | 探测未过 | 评分✓ 媒1 |

**未成功接收媒体的原因**

- 视觉能力探测未通过，未运行视频轨迹：12。
- 第一轮完成前调用失败，未到触发环节：8。
- 已保存轮的状态未变化，未达到触发条件：1。

探针原始错误类别（包括之后成功回退的传输）：

- deepseek_flash：`provider stream was truncated: length`；[调用记录](../../build/t4_expanded_api_20261020/run/capabilities/deepseek_flash/native_video/0/0001.json)。
- qwen37：`provider HTTP 400: {"error":{"message":"\u003c400\u003e InternalError.Algo.InvalidParameter: The provided messages input is invalid. The error info is [Unexpected item type in content.].","type":"invalid_request_error","param":"","code":"invalid_parameter_error"}}`；[调用记录](../../build/t4_expanded_api_20261020/run/capabilities/qwen37/native_video/0/0001.json)。
- qwen37：`provider HTTP 400: {"error":{"message":"\u003c400\u003e InternalError.Algo.InvalidParameter: The provided messages input is invalid. The error info is [Unexpected item type in content.].","type":"invalid_request_error","param":"","code":"invalid_parameter_error"}}`；[调用记录](../../build/t4_expanded_api_20261020/run/capabilities/qwen37/video_frames/0/0001.json)。

**冻结设置与验证**

- `first_event_response_v1`：首次真实媒体事件后若原本自然结束，则保留一次回应机会；两条件同规则，保持原状态、阈值和硬停止条件。
- policy 请求统一省略 seed，temperature=0.6、top_p=0.9；环境和裁判采样沿用原设置。此项显式记录在配置中，旧结果不与本轮合并。
- 环境状态及交互评估为 GPT-6 Astra，环境回应和终局裁判为 Claude Fable 5；被测模型仅负责 policy。最多 20 轮，4 并发，2200 次请求硬预算；每场景生成健康报告，诊断批次保留失败并继续，不按得分重抽轨迹。
- [配置](../../configs/gpt50_experiment/t4_multimodal_experiment.expanded_api_20261020.json) · [计划](../../build/t4_expanded_api_20261020/run/plan.json) · [代码冻结清单](../../build/t4_expanded_api_20261020/runtime_manifest.json) · [模型目录快照](../../build/t4_expanded_api_20261020/model_catalog.json)

审计异常计数：`{"text_controls_with_media": 0, "policy_calls_with_seed": 0, "initial_message_mismatches": 0, "initial_sampling_mismatches": 0, "completed_video_without_verified_media": 0}`。各项应为 0，非零需要先排查再解释成绩。

本地刷新：`python scripts/report_t4_expanded_api.py`。后台报告进程每 30 秒刷新，实验退出后保存最终快照。

**额外固定节点对照**

状态：`completed`；API 请求数 36，不计入上面 96 个候选结果。
用户已明确授权。两次文字重复及一次媒体回应来自相同公开节点，不计作完整 T4 轨迹或评分。
[固定节点回应原文](2026-10-20_t4_checkpoint_media.md)。

[固定节点最终核验与语义复核发现](2026-10-20_t4_checkpoint_findings.md)。
