# GPT50 / Claude150 当前全流程

本文件是当前活跃批次的唯一流程说明。旧 Qwen / Scale300 数据不参与任何阶段。

## 当前 GPT50 候选：英文续跑与翻译（2026-10-07）

当前正在执行的是 `unified_current_trust_v1_gpt50_active`，不是下文历史
`rollouts_state_v3` 主批次。场景、原始轨迹、英文译文和人工判断分别保存，
每个场景仍只有一条逻辑 rollout，翻译不增加样本数。

| 职责 | 当前入口 / owner |
|---|---|
| 生成与复用已完成调用 | `scripts/run_unified_gpt50_resilient.py` |
| 英文语言约束、忠实翻译 | `pipeline/localization.py` |
| 英文数值与引用核对 | `pipeline/translation_checks.py` |
| 批量翻译编排 | `scripts/translate_rollouts.py`，配置 `configs/gpt50_experiment/localization.json` |
| 自动 Gate2、保留人工待审 | `scripts/auto_gate2_unified_gpt50.py` |
| 只读网站数据适配 | `web/live_rollouts.py`，页面 `/gpt50-live` |

数据根为
`data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/`。
`unified_current_trust_v1_gpt50/manifest.json` 确定 50 个场景，当前输出写入
`unified_current_trust_v1_gpt50_active/`。每个场景的 `english/` 保存译文、
文本缓存和翻译状态；原始 `trajectory.json`、中断记录和调用日志保留。
`language_migration/` 保存语言切换的原始调用前缀及修订依据。

运行状态以 `results.json`、`translation_job.json`、`automatic_gate2_job.json`
及实际 PID 为准，不能只看进程存在或历史网页的完成数。运行中不要重复启动。
生成续跑使用 `--run --resume --language en`，必须先保存中断调用前缀；
已完成和已有失败结论的场景跳过，不以重采样替换它们。

`run_unified_gpt50.py`、`resume_unified_gpt50.py`、
`run_unified_gpt50_corrected.py`、`continue_unified_gpt50_corrected.py`
目前仍被当前入口导入，用于重建冻结计划，不能当作无用文件删除或另起批次。
这些是尚待解除的历史依赖，不是推荐启动入口；运行中的批次结束前不改写其哈希。
重复备份和无调用者的实现直接删除，历史研究证据与有效产物继续保留。
例外：`prompts/manifest.json.orig` 已被旧预注册收录为冻结输入，当前批次仍
依赖其原始哈希 `d2610b534354f649e8ec672e2c03a62eb0ed77e86480cfbac00c21734237b7aa`。
批次归档前保留并纳入 Git；它不是运行时使用的 prompt 注册表。

## 历史主批次：State v3 切换状态（2026-09-27）

旧 GPT50/Claude150 rollout 已冻结。两个 API 启动器现在只读取各自的
`scenarios_state_v3`、`rollout.state_v3.json`，并写入独立的
`rollouts_state_v3`；缺少真实人工签署的 state review registry 时会在构造
provider 之前退出。启动器默认只运行 rollout，不自动进入 Gate 或多模态阶段。

每轮固定执行：evaluated action → environment appraisal → deterministic
calibration → environment state update → environment response。轨迹必须在第
10–20 轮自然结束，并由真实证据实现四族至少一次变化，同时包含合规快变化与慢变化；失败项完整保留，
不得补写变化、放宽阈值或用替代样本覆盖。

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

### 当前多模态分阶段执行

1. GPT50 首批使用 `--nodes-per-trajectory 1` 准备 50 个不同场景的关键节点，
   Gate2 通过稳定哈希固定其中 40 个审查项。该覆盖批是正式 E8 的低成本入口，
   不冒充完整的 4 节点离线集。
2. 先对固定审查序列的前 5 个请求做 Seedance canary；结构、语音、身份稳定、
   私有信息边界与人工口型检查通过后，才补齐 40 个固定审查视频。
3. 使用 `scripts/finalize_multimodal_video_queue.py` 注册下载资产、探测时长和媒体流，
   然后完成人工 E8 记录。模型或机器筛查不能代替人工签字。
4. 完整离线集仍为每轨迹 4 个节点（GPT50 为 200 个请求，Claude150 为 600 个）。
   只有在跨片段角色身份连续方案通过 canary 后才扩展，避免把彼此无关的独立人物
   视频错误标成同一角色的时间连续观测。

Seedance 队列执行器默认只准备 provider state，不产生付费请求。新任务必须显式加
`--submit-new`；已有 task ID 会继续查询和下载，不会重复提交：

```bash
python scripts/run_multimodal_video_queue.py \
  --batch-root data/gpt50/experiment \
  --selection gate2 --limit 5

python scripts/run_multimodal_video_queue.py \
  --batch-root data/gpt50/experiment \
  --selection gate2 --limit 5 --workers 2 --submit-new
```

2026-09-25 的首轮 5 个付费 canary 已完成：4 个成功下载且媒体结构有效，1 个被
provider 以版权策略拦截。成功的 4 个中，快速画面抽检有 3 个未见明显违规，1 个
出现了明确禁止的英文字幕。因此当前结论为 3 个粗视觉通过、1 个画面约束失败、
1 个 provider 失败；在人工播放检查口型并确定修订策略前，不得扩到固定 40 个。

2026-09-26 经单独授权又执行了 2 个定向 replacement：版权误拦样本移除娱乐行业
专名和场景后成功生成；意外字幕样本强化零文字约束后也成功生成。两条均通过媒体
结构和联络表粗视觉检查，未见可辨识字幕，原始失败证据仍保留。当前只剩人工播放
核验逐字语音和口型；剩余 35 条未授权、未提交。

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
