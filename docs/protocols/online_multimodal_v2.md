# Online Multimodal v2 实施与实验协议

## 1. 分层边界

Online T4 与 offline T1–T3 使用不同媒体资产：

- Online T4：预生成、无台词、response-neutral 的短视频 cue。视频不能依赖当轮环境回复文本，也不改变环境回复。
- Offline T1–T3：完成 checkpoint 提取后，只为入选的重要节点生成与该节点文本对齐的 talking head。
- 两类资产不得互相替代。

旧 rollout 不重跑。其 appraisal_v11 + sparse_v1 provenance 保持不变，继续服务 offline 提取。旧 appraisal 没有保存每个 impact 的原话 evidence_span，因此不得把旧轨迹伪装成严格 v2 结果。

## 2. State 更新规则

T4 使用 environment_appraisal_v12 + evidence_balanced_v2：

- 普通事件最多更新 2 个 state 变量；
- 强事件最多更新 3 个；
- emotion 每轮最多 2 个；
- 其他三个维度每轮各最多 1 个；
- 每个变化必须有独立的 evidence_feature + evidence_span；
- 同一原话 span 不能支持两个变化；
- relationship 与 consequence_risk 需要直接 strength-2 证据，或同方向累计证据；
- 禁止仅因变量相关而连锁更新。

已有语义映射不变：mild → ±1，moderate → ±2，strong → ±3，最终裁剪到 [0, 10]。这些都是上限，不是强制配额。

## 3. Scenario 级在线触发

online_multimodal_v2 不改写 canonical scenario 的三个 authored triggers，而是按 scenario SHA-256 生成运行时 sidecar。

对四维 state 的每个叶子生成：

- increase：current >= S0 + 1
- decrease：current <= S0 - 1

State v3 每个 scenario 有 9–13 个变量，因此通常生成 18–26 个 trigger，覆盖
emotion、behavioral_disposition、relationship、consequence_risk。这里的“放宽”
仅指每个已选变量在真实发生一步变化时即可触发；`threshold_margin=0`，未变化的
S0 不触发，也不会为了视频而修改 state。

当同一轮多个变量同时跨阈值时，优先级在四个 state family 间轮转，并优先选择
此前展示次数更少的 family，避免 emotion 的多个叶子长期挤掉 relationship 或 risk。

trigger 映射到七个可复用事件族：activated_tension、easing_tension、open_engagement、guarded_withdrawal、firm_boundary、risk_concern、cautious_relief。
复用的是 cue 模板，不是人物视频；每个 clip 的身份与外观必须绑定所属 scenario。

所有 online clip 必须无台词、无字幕、无 state 标签、无阈值说明、无 hidden intention，只表现细微面部、注视、呼吸、姿态或短暂停顿。

## 4. 节流

- 每轮最多 1 个事件；
- 每个 trigger 每条 interaction 最多 1 次；
- 全局最小间隔 2 轮；
- 同 event family 最小间隔 3 轮；
- 每条 interaction 最多 5 个事件；
- 多个 state 同轮跨阈值时，其余持续满足阈值的事件可在冷却后依次出现。

目标是自然出现 2–3 次 cue，不通过重复同一阈值刷次数。

## 5. Text / Text+Video 隔离

两组共享完全相同的 scenario、public history、environment text、prompt、sampling、checkpoint 与 rubric。

文字 prompt 中一律移除 observable_cues、observable_expression、media metadata、trigger ID、event family、state 和 threshold。

Text 组只发送文字。Text+Video 组发送完全相同的文字块，再额外附加真实 video_url content block。缺少 asset_url 时必须 fail closed，不能退化成文字描述。

## 6. 两级实验

### Primary：matched checkpoint A/B

在同一个已触发 checkpoint 上冻结 public history 与当轮 environment text：

1. Text 组生成下一行动；
2. Text+Video 组在相同文字输入上生成下一行动；
3. 盲评 cue-consistent adaptation；
4. 对同一 scenario/checkpoint 做配对比较。

主要假设：state_adaptation(text+video) > state_adaptation(text)。

同时报告 goal achievement、risk management 和 relationship outcome，防止模型只迎合表情却损害任务表现。统计使用 scenario 分层、配对 bootstrap、配对置换检验和 win/tie/loss。

### Secondary：end-to-end T4 A/B

分别运行完整 Text 与 Text+Video interaction。由于后续行动会使轨迹分叉，它衡量总体收益，但不替代 matched checkpoint 的因果隔离。

## 7. 可达性基线

运行：python scripts/audit_online_multimodal_reachability.py

脚本只重放保存的 state_before/state_after，模型调用数为 0，不重写轨迹，不重新生成环境回复。

2026-09-26 对 GPT50 旧 sparse_v1 轨迹的保守结果：

- 45/50（90%）scenario 至少触发 2 次；
- 18/50（36%）至少触发 3 次；
- 中位数 2，范围 1–5；
- 每 scenario 有 12–16 个 trigger。

正式 v2 pilot 的验收门槛：至少 90% scenario 触发 ≥2 次，目标中位数 3，且不能重复同一 trigger 达标。

## 8. 上线门槛

1. 每个 scenario 所需的 event family 都有人工审核通过的 response-neutral 资产；
2. T4 event_assets 按 scenario_id → family 提供可访问 asset_url；
3. matched pair 的文字块 hash 完全一致；
4. 视频不含台词、字幕、benchmark 答案或私有 state；
5. 小规模 pilot 先通过触发覆盖与媒体传输审计；
6. 主要实验按预注册指标报告，包括负结果。


## 9. Online 资产生产顺序

GPT-50 的资产计划由 `configs/online_multimodal_assets.json` 冻结。当前 50 个 scenario 共需 323 条短片：50 条 `activated_tension` 锚点和 273 条依赖锚点的其他事件族短片。准备阶段不发起网络请求：

```bash
python scripts/prepare_online_multimodal_assets.py \
  --batch-root data/gpt50/experiment \
  --scenario-root data/gpt50/experiment/scenario/scenarios \
  --expected-count 50
```

付费生成必须分两阶段执行，不能在锚点不存在时直接跑 dependents。首次先用前 5 个 scenario 做 32 条资产的 pilot：

```bash
python scripts/run_multimodal_video_queue.py \
  --batch-root data/gpt50/experiment \
  --manifest data/gpt50/experiment/online_multimodal/manifest.json \
  --selection anchors --scenario-limit 5 --workers 4 --submit-new

python scripts/run_multimodal_video_queue.py \
  --batch-root data/gpt50/experiment \
  --manifest data/gpt50/experiment/online_multimodal/manifest.json \
  --selection dependents --scenario-limit 5 --workers 4 --submit-new
```

第一阶段每个 scenario 的 `activated_tension` clip 由固定的 fictional identity spec 生成；第二阶段同 scenario 的其余 clip 将该锚点作为 `reference_video`。跨 scenario 禁止复用锚点。Pilot 通过后，移除两条命令中的 `--scenario-limit 5` 即可扩展到完整 323 条。

生成后运行 `scripts/finalize_online_multimodal_assets.py`。它检查视频流、4 秒时长容差，以及同步非语言音轨存在；只有每条资产人工审核全部通过、且提供公共 HTTPS 资产基址后，才会输出 `runtime_ready: true` 的 `event_assets.reviewed.json`。T4 配置只能加载该 reviewed 映射，不能加载 `event_assets.pending.json`。

## 10. 首次媒体事件后的回应机会

2026-10-20 的逐场景审计发现 6 条轨迹在第 1 轮生成了真实视频事件，但同轮自然结束，
因此没有下一次 policy 调用接收视频。这是触发后的结束时机问题；这些记录的状态阈值已经满足。
另有调用失败前尚未完成第一轮、状态未变化、视觉能力探测未过和未启动等情况，分别保留原因。

新增独立实验配置项 `media_completion_policy: first_event_response_v1`。
运行器据此设置 `multimodal_trigger_policy.defer_first_media_completion: true`：

- 只在首次真实视频事件已经产生、资产可用且该轮原本要自然结束时，保留下一轮回应机会。
- 两个条件的环境采用相同规则；文字条件继续仅发送文字，视频条件在后续请求中附加媒体。
- 仅保护首次事件，不因后续事件不断延长对话；无状态变化时不强行产生事件。
- 显式场景停止条件和最多 20 轮的上限优先，接口失败仍如实记为失败。
- 不改变 S0、状态更新、阈值、事件冷却、当前环境回复或已保存结果。
- 轨迹私有日志保存 `media_completion_guard`，记录原自然结束判断、是否延后及下一次回应轮。
  这些字段不进入 policy 的文字输入。

该选项默认关闭，旧配置及冻结运行保持原规则。启用后是新的结束协议，
应独立保存结果，不能用新的分数覆盖或拼接旧实验。
目标六场景的 [新版配置](../../configs/gpt50_experiment/t4_multimodal_experiment.first_media_response_v1_20261020.json)
只用于机制验证，不代表随机抽取的性能样本；详见 [修复与本地验证](../../reports/experiments/2026-10-20_t4_media_completion_fix.md)。
