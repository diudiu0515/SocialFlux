# GPT50 的 T1 / T3 开发题

本批固定 GPT50_001–050，暂停新增 T2。配置为
[`configs/offline_gpt50_t1_t3.json`](../../configs/offline_gpt50_t1_t3.json)，
每场景目标 4 道 T1、4 道 T3，共 400 道。是否实际完成以
`data/offline_gpt50_t1_t3/manifest.json` 的 `complete`、`scenario_coverage`
和 `replay_ready_count` 为准，不能用目标数冒充生成数。

T1 包含当前强度、两个区间方向、两变量组合；T3 包含即时影响、延迟影响、
行动比较、即时—延迟组合。公开历史截止 t2；即时是候选行动后的下一次
环境回应，延迟是包含即时回应的五次环境回应。题型、六档强度、唯一选项
回答和正式评分边界沿用[选择题协议](../protocols/OFFLINE_T1_T3_CHOICE_V1.md)。

## 来源与断点

复用当前 active 批次的 43 条完整轨迹和 3 条可用部分轨迹。
GPT50_001、009、023、033 没有足够对话，另建三轮开发前史；
不覆盖原失败轨迹，不把这个短前史记为完成了正式 rollout。
9 个原轨迹的模型语义审核为 reject，来源状态继续显示，不能变成已审核来源。
题目及答案均待人工审核，`ground_truth` 保持空值。

`offline/choice_pipeline.py` 负责共享出题与既有环境装配，
`offline/choice_batch.py` 负责固定场景集、按任务续跑、来源 SHA 核对及合并导出。
`scripts/build_offline_choice_dev.py` 只保留命令入口，不复制第二份生成器。
场景、state ontology、appraisal 和 response 仍走现有环境；仅 offline
传输适配移除已确认不被 GPT 路由接受的 `top_p`。

旧 60 题可复用的出题文件与完整 T3 分支按来源 SHA 引用。
新 T3 两种行动使用同一 snapshot、外部事件计划和续演策略。
`--reuse-factual-continuation` 可将原轨迹 t3 的行动固定为候选一，复用 t3–t7；
只有完整五轮、状态和 dynamics 连续、没有外部事件或阶段改变、续演 policy
契约一致时才允许复用。候选二单独执行环境分支，参考面板区分两种来源。
未来分支保留在作者侧；题目公开投影不含未来、私有 state 或参考答案。
调用失败、原始出题失败和中途回放逐次保存；重复运行不会抹去失败记录。
补建前史的 checkpoint 保存完整 `resume_snapshot` 并绑定 scenario SHA；下次运行
可保留已完成轮次，继续调用相同环境和 policy。没有完整快照的旧记录不推算恢复。
恢复保持完整环境状态及采样配置；新 provider 实例的请求计数重新开始，不声称与不中断运行逐 token 一致。
原始请求及每次恢复的来源快照保留，可区分实际续演与假定重现。
已完成的出题文件直接复用；改变题面应写独立 `*.curated.json`，并注明是
助手编辑而非人工审核。不得删除失败记录以改变实验结果。

## 命令

```bash
# 固定 50 场景，T1 / T3；会调用配置中的现有 provider
python -m pipeline offline-build --config configs/offline_gpt50_t1_t3.json

# 单独补作某个任务、某些场景，题号不随子集改变
python -m pipeline offline-build --config configs/offline_gpt50_t1_t3.json \
  --tasks T3 --scenarios 1 9 23 33

# 传输恢复参数独立记入本次运行，不改冻结的题库规格
python -m pipeline offline-build --config configs/offline_gpt50_t1_t3.json \
  --tasks T1 --scenarios 2 5 --request-timeout 600 --workers 2

# T3 对传输、空响应或明确截断自动恢复；不重试来源／内容校验错误
python -m pipeline offline-build --config configs/offline_gpt50_t1_t3.json \
  --tasks T3 --request-timeout 600 --transport-attempts 2 --workers 3 \
  --recovery-attempts 3 --reuse-factual-continuation

# 本地重新导出、审计、配对现有视频，不调用模型
python -m pipeline offline-build --config configs/offline_gpt50_t1_t3.json \
  --export-only \
  --pair-media data/gpt50/experiment/multimodal_delivery_v1/online_multimodal/manifest.json

python -m pipeline offline-eval --items data/offline_gpt50_t1_t3/items.jsonl \
  --output build/offline_gpt50_t1_t3/check --check-only

# 少量真实试答，输出目录必须是新的；明确记录调用/格式失败
python -m pipeline offline-eval --items data/offline_gpt50_t1_t3/replay_ready.items.jsonl \
  --output data/offline_gpt50_t1_t3/smoke_text --per-task 2
```

两个进程可以分别生成 T1 和 T3，合并导出使用文件锁。不要同时对同一场景、
同一任务重复生成；没有来源前史的四个场景要等前史完成后再运行 T3。
不要在运行中修改 prompt 及其 manifest，避免造成哈希校验失败。

## 交付与标注

本地机器文件为 `items.jsonl`，被测端用 `public.jsonl`；
完整可读题面、公开历史和作者参考解释在 `examples.md`。
`development_audit.json` 记录题型与四维覆盖，
`state_reference_crosscheck.json` 提供机器 state 的方向交叉检查，
不把机器一致性当作可见证据充分或人工通过。
`pairing_report.json` 如实列出缺少既有媒体的题目，不挪用其他轨迹视频。

网站默认 `/offline-review` 打开新批次，也可明确使用 `?bank=gpt50-t1-t3`；旧 60 题仍可在
`/offline-review?bank=dev60` 标注。页面展示生成进度、来源审核状态、
题面、分支参考和四项质量判断。新批次追加题目时保留未改变题目的本地草稿；
题目 SHA 改变时旧稿归档到导出备份，不能自动套用为新版标签。
参考答案按需打开，浏览器记录是否已经看过参考。

原始调用、私有分支与视频不上传 Git；代码、配置、可读开发题快照和报告
纳入版本管理。Git 快照只包含当前实际产出的题目，并明确记录生成状态。
