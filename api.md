# SocialFlux LLM 分工与当前模型路由

本文件是所有需要 LLM 的生产环节清单。唯一运行时映射位于
`configs/model_routes.frontier_api.json`；业务代码不得写死模型名。当前结论来自
AutoDL 同 endpoint、同输入、同 validator 的项目内对照，不是通用排行榜，也不等于人工验收。

| 板块 | Canonical route | 模型 | 模型做什么 | 验证依据 |
| --- | --- | --- | --- | --- |
| Scenario 制作 | `scenario_authoring`、`scenario_normalization`、`scenario_initialization` | `claude-fable-5` | 生成人物、事实边界、目标、私有动机及初始状态候选；旧场景的叙事重构也由 `scenario_normalization` 路由承担 | 场景写作 4/4 schema/长度通过；重构 owner 为 `scenario_design/revision.py` |
| Rollout 行动方 | `policy` | `claude-fable-5` | 根据角色目标和可观察历史逐轮行动 | 6/6 通过，承接请求和自然表达优于另外两项 |
| Structured Appraisal | `appraisal` | `claude-fable-5` | 结构化解释社会意义及 ledger 事件 | 6/6 通过；之后由 Python 做确定性 calibration/state/risk 更新 |
| Environment Response | `response` | `claude-fable-5` | 读取更新后状态，生成对方回应与可观察表达 | 6/6 通过；与 Appraisal 始终是独立请求 |
| T2 配对 | `t2_branch_authoring`、`t2_pair_review` | `claude-fable-5` | 从优质 A 轨迹改写 B，并审查共享前史、差异历史和同一 ending | 构造 2/2；语义复核 4/4 |
| T2 答案 | `t2_answer`、`t2_answer_review` | `claude-fable-5` | 比较 A/B 状态、给双侧证据并复核答案 | scale-50 为 50/50；模型复读显示能保留证据不足和不确定性 |
| T3 候选行动 | `t3_action_authoring` | `claude-fable-5` | 在同一 checkpoint 提出可执行且有策略差异的行动 | 统一单模型重构后的正式 route；历史 scale-50 中 Claude 为 50/50，Astra 内容对照继续作为审计证据 |
| T3 分支续演 | 复用 `policy` → `appraisal` → Python → `response` | `claude-fable-5` | 让各候选沿正式环境链继续，不建立平行流程 | 沿用 rollout 三阶段实测结论 |
| Task checkpoint 提取 | `task_extraction` | `claude-fable-5` | 从公开轨迹选择 T1/T3 checkpoint、目标状态和证据 | 8/8 通过；正式 owner 为 `tasks/extraction.py` |
| T1 答案 | `t1_answer` | `claude-fable-5` | 状态强度、变化方向、证据与不确定性候选答案 | scale-50 为 50/50，且不确定性校准较保守 |
| T3 答案 | `t3_answer` | `claude-fable-5` | 比较即时/延迟状态影响并给可观察证据 | scale-50 为 50/50 |
| T4 Judge | `t4_judge` | `claude-fable-5` | 评价目标达成、适应、风险、恢复与关系结果 | scale-50 为 50/50 |
| 自动质量复核 | `quality_review` | `claude-fable-5` | 检查角色、事实、空转、动作归属与任务证据 | 8/8；两条已知问题轨迹均被标记，其中 IA252 命中预声明类别 |

`legacy_task_bundle` 仅供旧脚本恢复历史 T1/T2 合并产物，不能用于新的正式生成。
已删除含义模糊的生产 route：`task_construction`、`task_answer`、
`semantic_judge`。benchmark 文件中同名字段只表示历史对照板块。

密钥优先从 `AUTODL_API_KEY` 读取；后台进程未继承环境变量时，从服务器上
权限为 600 的私有文件 `/root/.config/socialflux/autodl_api_key` 读取。生产调用统一使用
标准 Anthropic Messages 协议，端点为
`https://www.autodl.art/api/v1/anthropic/v1/messages`，以 Bearer 鉴权直连且不经过
服务器 HTTP 代理。Claude Code CLI 只用于网关诊断，不用于数据集批量生成；业务代码
只能通过 `providers/anthropic.py` 和 route table 发起请求。任何 LLM 输出均为待人工
核验的 proposal/model review，不是 human acceptance 或 ground truth。

Provider 对 408/409/425/429/5xx 和网络超时做有界 transport retry；格式/语义
retry 仍由各领域 owner 处理。`request_count` 统计实际 HTTP 尝试，
`failed_request_count` 统计失败的 transport 尝试，不得以逻辑 stage 数代替。

完整证据与限制见
`reports/experiments/2026-09-17_autodl_board_model_selection.md`。
任务答案板块已完成冻结的 8 场景 pilot 和 50 场景扩大确认。扩大确认共 750 个
逻辑样本、1,028 次累计请求，725 条最终成功；25 条残余失败如实保留。
2026-09-18 起按已确认的新开发设置，所有 active route 统一使用
`claude-fable-5`；历史多模型结果不被重写。
