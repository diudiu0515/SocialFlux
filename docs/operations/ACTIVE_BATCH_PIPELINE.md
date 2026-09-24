# GPT50 / Claude150 当前全流程

本文件是当前活跃批次的唯一流程说明。旧 Qwen / Scale300 数据不参与任何阶段。

## 不变量

- Claude 主批次固定为 150 个全新场景，影视结构来源与原创剧本来源严格为 45:105，即每 10 个为 3:7。
- GPT50 是 GPT-6 Astra 构建的 50 场景试验批次；Claude150 是 Claude 构建的 150 场景全量批次。两者共享同一个 Claude/Python/Claude Environment，但场景池和下游 T1–T4 模型彼此独立。
- 每个场景只有一次正式生成机会，至多保留一条在第 10–20 轮自然结束的 rollout，不做 best-of-N。
- Gate 1–4 不阻塞候选生成。所有候选先生成，机器检查只作诊断，最后由人工筛选。
- 每个可用 rollout 必须形成 T1、T2、T3、T4 四个 task，并且四个 task 都必须带模型答案。
- 任一失败、缺文件、缺 task 或缺答案都不能被标记为“流程完成”。

## Claude150 阶段

| 顺序 | 阶段 | 是否调用 API | 完成条件 |
|---|---|---:|---|
| 1 | `scenarios` | 是 | 150/150 schema 有效；来源严格 45:105；生成 Gate1 全量人工包 |
| 2 | `rollouts` | 是 | 每个场景恰好一条有效 rollout，共 150 条 |
| 3 | `gate2_packet` | 否 | 立刻生成稳定抽样的 E1/E2 与 E9 timescale 人工审核包；不等待 Gate2 结论 |
| 4 | `multimodal_plan` | 否 | 每条 rollout 选 4 个重要节点并生成 provider-neutral 视频请求；150 条默认共 600 个请求，零网络调用 |
| 5 | `gate2_experiments` | 是 | 完成 E3 history、E4 paraphrase、E5 local counterfactual、E6 双 backbone、E7 persona-only，并校验 E9 抽样覆盖；E8 视频未生成时记为 `awaiting_video_api`，但不阻塞后续阶段 |
| 6 | `sources` | 否 | 150 条 rollout 全部物化为下游 source package 和 Gate3 全量人工包 |
| 7 | `t2_specs` | 是 | 每个 rollout 都有可构造 T2 的受控分叉 spec |
| 8 | `t2_pairs` | 是 | 每个 spec 都完成 A/B pair、答案和诊断记录 |
| 9 | `tasks` | 是 | 150 个 package 均含 T1–T4 的 instance、答案和 provenance；生成 Gate4 全量人工包 |
| 10 | `gate3_review` | 是 | 单个质量审核模型对 150 条 trajectory 做六维全量 pass/reject；保留人工抽检入口 |
| 11 | `review_index` | 否 | 汇总 Gate1、Gate2、Gate3、Gate4、视频队列与 task/T2 清单 |

各阶段不会因为人工 gate 尚未签字而停止。Gate2 文本实验在 rollout 后立即执行；
视频请求只准备队列，待配置视频 API 后生成资产并运行
`scripts/finalize_multimodal_video_queue.py`。生成资产后 E8 仍需人工核验状态外显、
人格一致性、时序连续和口型自然度。
E9 的机器统计只负责抽样和变化摘要，真人仍需判断变化速度是否符合具体语境。

多模态分成两条路径：offline 对每条完整轨迹的高状态变化、关键承诺/拒绝、已有
trigger 和后段 history-bearing 节点优先生成视频；online 使用
`online_relaxed_v1`，将阈值和变化阈值各放宽 1、cooldown 缩短为 2，并允许
crossing trigger 在持续满足阈值时触发，但每轮仍最多一个最高优先级事件。

## 断点与失败规则

- 成功且 fingerprint 一致的产物会复用。
- API 失败记录不会再被 `--resume` 当作成功；下一轮只补失败或缺失项。
- T2 pair 的 `--resume-incomplete` 会跳过 completed，resume failed，并新建 missing。
- task package 只有同时存在 T1–T4、四个 instance 和四个答案时才可复用。
- `--require-complete` 使 T2 spec、T2 pair 和 task 阶段在不完整时返回失败，交给监督器续跑。

## 零 API 状态审计

随时可运行：

```bash
python scripts/audit_active_batch.py \
  --batch-root data/claude150_v1 \
  --expected-count 150 \
  --scenario-id-prefix CF150_
```

该命令不构造 provider，不发网络请求，并原子更新：

- `data/claude150_v1/pipeline_status.json`：各阶段真实计数与完整性。
- `data/claude150_v1/pipeline_failures.json`：缺失、无效和不完整 ordinal。

## 有界执行

`scripts/run_claude150_pipeline.sh` 负责从断点执行一次有界批次。场景补齐后，编排器按上表推进；视频 API 未配置时不会空转重试。GPT50 使用 `scripts/run_gpt50_pipeline.sh` 与独立目录，二者不会混写。
