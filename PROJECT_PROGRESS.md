# SocialFlux Project Progress

更新时间：2026-09-08

| 模块 | 状态 | 证据/限制 |
|---|---|---|
| v2 架构迁移 | 已完成 | 自由 action、单一环境、自然 rollout、局部 intervention |
| Hybrid scenario source | 结构已完成 | 10 narrative-derived + 10 synthetic-script；影视十场景已有作品/年份/媒介/抽象位置 provenance，来源与原创性最终判断仍待真人复核 |
| 两阶段 scenario 创建 | 已完成 | source quality approval → normalization → candidate S0/D0 |
| 20 个 scenario bundle | 候选完成 | 保留原 10 个并新增 10 个影视结构启发场景；全部带 JSON、同名 Markdown、coverage，S0/D0 尚未 human_frozen |
| Prompt catalog | 已完成 | 24 个版本化 prompt、SHA-256 manifest、职责与边界审计；新 rollout Judge 使用 Protocol v1 六维、10 项 hard reject 与逐维 turn-ID 证据合同 |
| Provider/model pool | 已完成 | OpenAI-compatible、Anthropic、Gemini、vLLM；真实密钥/endpoint 由本地配置提供 |
| 自然 rollout | 20 场景开发运行及严格筛选已完成 | 每 scenario 3 条 × 6 turns，共 60 条活跃自然轨迹；经定向重采样后来源为 Qwen3.5-9B 42、Qwen3-32B 16、GLM-4-9B 2。逐轨迹双 Judge + history 为 60/60；scenario 未 human-freeze，且不是正式 20×12 池 |
| T1/T2/T3 builders | 已完成 | 统一质量门后按任务专项择优：T1=来源质量+历史深度+状态信息量，T2=来源质量+private-state 分化，T3=来源质量+中后段 checkpoint utility；模型身份不计分、不设配额 |
| Instance 质量审计 | 自动部分已完成 | 按最终 60 个活跃 trajectory ID 专项选源并重建 T1=120、T2=40、T3=20；选源审计 20/20、结构 180/180、bundle 20/20，人工 plausibility/标签仍待评审 |
| GPT–Qwen rollout 对照 | GPT 侧受凭据阻塞 | 官方 Qwen3.5-9B 已下载并完成 pilot；匹配配置、同模型 T2 分层和盲审已就绪；当前环境未设置 `OPENAI_API_KEY`，不能宣称胜负 |
| T4 | 核心交互已完成 | 与离线共用环境；正式 judge/human 校准待完成 |
| Talking Head | 机器生成与验收已完成 | EchoMimicV2 四卡生成 40/40 MP4；音轨、时长、分辨率与帧率自动校验通过，表达—状态与时序自然度待真人检查 |
| 九项验收 | 框架已完成 | 当前正式结果为 pending；需要自然轨迹、模型实验与真人评审 |
| gate.md 正式池约束 | 工程完成、正式证据待生成 | 20×12 三模型族（含 32B）配置、六维/hard reject、post-hoc 每场景唯一 canonical 选择、history、跨族双 Judge、backbone sensitivity、三人 GT 与 12 条总闸门均已实现；真人 freeze 尚未签名，因此 formal raw 不得启动 |
| 正式本地模型准备 | 模型服务可用、正式运行受 Gate 阻塞 | Qwen3-32B-AWQ、GLM-4-9B、DeepSeek-V2-Lite-Chat 与 Qwen3.5-9B 环境服务已完成本地部署实验。模型目录不提交 Git；Gate 1 真人 freeze 与 Gate 2 通过前不得启动 formal raw |
| 网站 | 已部署 | 标注工作台覆盖 20 个 scenario、184 条完整人工筛选队列、协议三态/六维/10 项 hard reject/五问/唯一赢家、180 个开发 Task、40 个视频，以及 Gate 1–4、Formal GT、holdout、污染审核总清单；草稿本地保存并导出 JSON |
| 文档与清理 | 已完成 | 根目录保留 4 个权威入口；架构/协议/操作/Prompt/设计输入/论文证据归入 `docs/`，中间实验轮次归档但不删除；移除无引用的 12-byte `API.md` 垃圾占位 |
| 测试 | 已完成本轮工程验证 | core 149/149、web 7/7、20/20 scenario 文档一致性检查、`git diff --check` 与新版 API/page smoke 均通过；研究人工验收不由工程测试替代 |

## 20-scenario development pool

- 主轨迹：20 个 scenario × 3 条 × 6 轮上限，共 60 条。初始来源为 Qwen3.5-9B 三 seeds；质量修复后活跃来源为 Qwen3.5-9B 42、Qwen3-32B-AWQ 16、GLM-4-9B 2。
- 离线实例：每 scenario T1=6、T2=2、T3=1；全量 T1=120、T2=40、T3=20。每个 T3 有 3 个候选行动、3 个即时分支和每分支 5 轮延迟 continuation。T3 公开历史最少 4、均值 8.4 条；全量生成中 18 个不可行 checkpoint 被拒并留痕。
- 人工抽查材料：20/20 scenario 均在自身 `rollouts/` 下包含完整自然语言 `dialogues.md` 与逐 instance 的 `tasks.md`；bundle audit 为 20/20 ready。
- Instance：最终 60 条 ID 确定后已按任务专项重建 T1=120、T2=40、T3=20，共 180 个实例；20 个 T3 各含 3 条局部分支。T1 历史均值 4.72 轮，T2 为 3.70 轮；结构审计 180/180、选源审计 20/20 通过，且所有 source trajectory 均属于当前 Gate 3 单轨迹通过集合。结构通过不替代人工语义评审。
- 完整轨迹：Qwen3-32B 主审和 GLM 二审均覆盖 60/60；同 seed 的 Full/Recent-k/Critical-event-removed history probe 经三条失败轨迹替换后为 60/60。累计 80 个候选尝试均有 JSONL 留痕；旧文件移出活跃 manifest 并保留在 `rollouts/rejected/` 审计目录。详细过程见 `reports/experiments/2026-09-06_gate_filtering_log.md`。
- 选源结果：模型只作为 provenance。按“每个任务使用到的唯一来源 trajectory”统计，T1 为 Qwen3.5=38、Qwen3-32B=9、GLM=2；T2 为 32/12/1；T3 为 15/4/1；DeepSeek=0。该不均衡分布是质量排序结果，不是配额目标，详见 `reports/experiments/2026-09-07_task_source_selection_audit.json/.md`。
- Gate 3 边界：当前 active development pool 每场景只有 3 条，不是“四个配置各 3 条”的 12-run raw pool。60 个逐轨迹 audit 均通过，但仍不满足正式 raw pool 的每场景 12 条、三本地模型族和 environment/policy separation，因此总 Gate 3 状态保持 rejected，而不是 formal clean pool。正式规则现为 12 条 raw 过门、协议审核后每场景保留 1 条，不强制模型均衡；所有候选与淘汰依据继续留档并进入人工网站。
- Protocol v1 全库存筛选：184 条可恢复轨迹全部入册（60 active、123 rejected archive、1 orphan archive），自动判定 PASS=64、REVIEW=108、REJECT=12。每场景已经计算 1 条 provisional winner，共 20 条；分布为 Qwen3.5-9B 15、Qwen3-32B-AWQ 3、GLM-4-9B 2。该分布只反映旧开发证据下的自动排序，不证明 9B 优于 32B。旧 Judge 没有逐维 turn-ID 证据，且唯一赢家仍需逐场景比较确认，所以 184/184 全部保留在网站人工队列；确认前不得写成 human-confirmed 或 formal selected。详细留痕见 `reports/experiments/2026-09-07_rollout_screening_protocol_v1.md`。
- 最终自动报告：`reports/experiments/2026-09-06_four_gate_final_development.json`；Gate 1=pending、Gate 2=rejected、Gate 3=rejected、Gate 4=pending，`research_ready=false`。其中 Gate 3 单轨迹为 60/60，Gate 4 结构为 180/180；总状态未用局部通过冒充正式通过。
- 九项 gate：Local Action Intervention 与 Seed Robustness 为 `evidence_ready`；其余（含 Full-Trajectory Plausibility）保持 `pending`；research acceptance 为 false。

本地可再生产物位于 `build/pipeline_v2/`，轨迹、`dialogues.md` 与 `tasks.md` 位于各 `configs/scenarios/scenario_NNN/rollouts/`；private/generated 数据按 `.gitignore` 不提交，筛选摘要与实验方法保存在 `reports/experiments/`。

## 不能提前宣称完成的研究工作

- 20 个 scenario 的来源、质量门与 S0/D0 人工审核；
- Gate 2 E1/E2 的三名实名评审及 E3–E5 的实名人工有效性确认；
- 正式 20×12、三本地模型族且 environment/policy 分离的真实自然 rollout pool；
- 30–50 transition 的三人 state-update 标注；
- 15–20 完整轨迹的三人 plausibility 评审；
- Persona、Paraphrase、History、Neutral、Response-State 和 Seed 实验结果；
- T1/T2/T3 正式 human ground truth 与 T4 judge 校准；
- Talking Head temporal/semantic 人工检查（实际 40 条资产和机器媒体验收已完成）。

工程完成与研究验收分开记录；没有证据时状态保持 pending。

## Rollout 模型升级决策

当前 60 条 active trajectory 是开发/修复池，不是最终模型能力实验。它大量使用已经常驻的 Qwen3.5-9B，是为了快速迭代环境、prompt 和筛选器；同时让 Qwen3.5 同时承担 environment 与多数 policy 会削弱正式的模型隔离，因此不能直接作为最终 clean pool。

正式 raw pool 仍按 20×12 生成，并优先做质量匹配 pilot：Qwen3-32B-AWQ 4 seeds；GLM-4-32B 量化版 4 seeds（下载和显存实测通过后替换现有 GLM-4-9B）；DeepSeek 模型族 4 seeds，其中若配置到合规 API 凭据，可用不超过总池 30% 的旗舰 API 轨迹，否则保留本地 DeepSeek-V2-Lite。Qwen3.5-9B 只作为 environment，不再作为正式 policy。每条仍经过相同 Judge、history 与人工比较，不因为参数量大而自动入选。

本机四张 48GB GPU 当前分别运行 environment、Qwen3-32B、GLM-4-9B 和 DeepSeek-V2-Lite。235B/671B 级 MoE 虽每 token 只激活部分参数，部署时仍需容纳总权重并跨多卡并行，不适合在保持独立 environment/Judge 服务的当前资源上直接常驻。GLM-4-32B 是当前更现实的本地升级目标；更大 API 模型只在凭据存在后做同配置盲测，避免用模型名代替实测质量。
