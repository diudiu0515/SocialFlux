# SocialFlux Project Progress

更新时间：2026-10-11。这里记录已完成的工程能力；实时批次状态以 manifest 和运行记录为准。

## 当前交付

- GPT50 T1/T3 扩展固定 50 个场景、目标 400 题；T2 暂停新增。完成数和缺项以新批次 manifest 为准。
- 扩展批次复用同源视频形成文字／视频版本，答案保持一致；缺少匹配资产的题目单列。全部待人工审核。
- 用户已明确授权现有 `autodl.art` 的场景／对话／state 调用；正从已保存断点补齐。旧批次与失败记录保留。
- 网站支持新旧题库切换及增量题库的草稿保留；生成与数据状态见[扩展说明](docs/operations/OFFLINE_GPT50_T1_T3.md)。

- 公共命令入口为 `python -m pipeline`，T1–T3 新协议使用 `offline-build` / `offline-eval`；旧概率题路径保留用于复现。
- Offline 开发包来自 5 个现有 scenario 和对应 rollout，共 60 题，每个 task 20 题，覆盖四类 state，含 15 道组合题。
- 56 道题完成所需回放；GPT50_014 的 4 道 T3 仍为待补分支的开发候选。全部答案待人工审核，未写入正式 GT。
- 主作答协议为 `{"answer":"B"}`，证据诊断、组合分维诊断、格式失败与调用失败分别统计。
- 网站 `/offline-review` 已同步本批题目，支持历史/视频、按需查看作者参考，以及绑定版本的标注草稿导入导出。
- `/gpt50-live` 展示当前 GPT50 的场景、轨迹、state、Gate 结果和实际匹配的视频。当前多模态资产已存在；旧 Talking Head 清单为空不代表当前批次没有视频。

完整交付、provider 试答和已知问题见 [Offline 开发题报告](reports/experiments/2026-10-10_offline_t1_t3_dev60.md)。当前批次与恢复入口见 [活跃批次手册](docs/operations/ACTIVE_BATCH_PIPELINE.md)。

## 正式准入边界

一场景一条自然 rollout 的规则保持不变，失败仍计入产率。T2 受控改写和 T3 反事实分支都绑定真实来源；当前开发通过不代表正式来源 Gate 通过。

| 阶段 | 当前工程能力 | 正式准入仍需 |
|---|---|---|
| Gate 1 | 原始 scenario、初始 state 和哈希可审核 | 真人冻结及最终来源哈希 |
| Gate 2/3 | 自动检查、模型审核、失败与来源变更均可记录 | 对应批次的有效证据及人工要求 |
| Gate 4 | 完整题目、待审答案、证据与错项映射可审核 | 真实独立标注、分歧处理和答案确认 |
| 视频 | 现有素材可播放、配对、追溯来源 | 对应素材的人工质量与信息边界审核 |

浏览器草稿、LLM judge 和机器参考答案都不能冒充真人签名或 human GT。当前 60 题开发包不是可发布的正式 benchmark。

## 本轮架构整理

更新模块职责、配置层级、网站入口与产物保留规则；删除已被路由替代的旧前端实现，保留旧 URL 兼容。T2 共用运行服务由 `tasks/T2/runtime.py` 直接提供，仓库调用方不再经过 `scripts/t2_common.py` 转发。

原始数据、实验报告、待审标签和当前模型配置保持原位。网站与模块整理的删除清单及恢复副本在 `archives/cleanup-2026-10-10/`；验证记录在 `build/architecture_cleanup_20261010/`。

随后按确认的 prompt 链删除 39 份被替代模板，注册项由 89 减到 50，并清理旧文本测试和生成指纹依赖。保留模板正文未变；旧配置引用已撤下版本时明确报错，不自动切换。当前链路与兼容入口见 [Prompt 目录](docs/prompts/RUNTIME_PROMPT_CATALOG.md)，恢复及历史冻结限制见 [审计记录](docs/prompts/PROMPT_AUDIT.md)。224 项相关测试通过，56 道开发题入口检查及网站接口检查通过；记录在 `build/prompt_cleanup_20261010/`。
