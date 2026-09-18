# SocialFlux Project Progress

更新时间：2026-09-18

## 当前 Scale300 / Fable 状态

- 唯一生产入口是 `python -m pipeline`，阶段顺序为
  Gate 1 → rollout → Gate 2 → Gate 3 → T1/T2/T3 与 T4 → Gate 4。
- canonical catalog 为 `configs/scale300_v1/scenarios` 的 300 个 scenario；
  preflight 验证 300 × 3 = 900 个 rollout slot。
- Policy、Appraisal、Response、construction、review 与 T4 全部通过同一
  route table 解析到 `claude-fable-5`，Appraisal/Response 保持独立请求。
- Gate 1：300 个 scenario 机器检查通过，正式 hash-bound 人工 freeze 未完成。
- Gate 2：机器框架证据存在，Scale300 E1–E5 人工验证未完成。
- Gate 3：正式 900 条 raw pool、双 Judge/history evidence 与 300 条
  human-confirmed canonical trajectories 尚未生成。
- Gate 4：必须等待 Gate 3 selected pool 和新 T1/T2/T3 instances；当前未通过。
- `data/formal/raw`、`data/formal/selected`、`data/formal/tasks` 当前没有
  可发布正式产物，因此不能宣称 benchmark release ready。

以下内容是 2026-09-11 的 R3/20-scenario 历史快照，只用于审计，不代表当前
active baseline。

## 历史快照：2026-09-11

| 模块 | 当前状态 | 可复核证据与边界 |
|---|---|---|
| Scenario | 20 个候选 bundle 已迁移 | 10 synthetic-script + 10 narrative-derived；每个都有 JSON、配对自然语言 Markdown、明确 evaluated role/goal、完整 persona/hidden intention、S0/D0、3 个视频触发器和 `max_turns=20`。来源质量与 S0/D0 仍待真人冻结 |
| Agent / Environment 模型 | 当前 R3 诊断栈已明确 | 当前 v29 诊断的 evaluated-agent policy、structured appraisal 和 visible response 都使用 `Qwen/Qwen3-32B-AWQ`，但 appraisal 与 response 是两个独立 LLM call，中间 state/dynamics/ledger 与 0–10 数值更新完全由 deterministic Python 执行。正式 baseline 仍是 Qwen3.5-9B environment；若正式替换须重跑受影响的 E4/E6 |
| Gate 2 | E3–E6 机器实验完成，E1/E2 与 E3–E5 真人复核待完成 | E3：32 checkpoints/18 machine-pass；E4：20/20 strict pairs 通过等价预检，overall/state/dynamics direction=0.9400/0.9429/0.9333，sign reversal=0；E5：20/20 checkpoints machine-pass；E6：Qwen/GLM 20 scenarios，exact direction=0.7078、change/no-change=0.7128、sign reversal=0.005、0 replay failure，且两侧 active checkpoints=19/17，非退化 gate 通过。机器不得代签真人字段 |
| 最多 20 轮合同 | 工程已完成，真实新池生成中 | offline rollout 以 20 为上限，10–20 轮自然结束才进入主候选；少于10轮归档，20轮预算截断如实记录。T4 同样最多20轮并允许自然结束；generate_long_rollout_pool.py 支持逐槽原子落盘、失败留痕和 resume |
| 旧 rollout 库存 | 全部失效但保留审计 | 184 条旧轨迹均只有 6 轮；新版 Protocol 报告为 REJECT=184、provisional winner=0，不再进入 Task 1–4 |
| 新最多20轮开发池 | v29 联合短测阻塞，未运行新 IA003 | 13 个 appraisal/ledger 短样例 13/13 通过（14 requests）；真实两阶段短测因 `social_act=acceptance` 不在固定 schema vocabulary 而在 appraisal 阶段失败（appraisal 4、response 1 requests）。按预先声明的停止条件未跑 v29 IA003、第二 seed 或异类场景；v25 IA003 19轮 rejected 轨迹已上网站供人工诊断 |
| 20 轮 smoke | 仅历史结构 smoke，不再算质量通过 | 旧 Qwen3-32B × IA_PIPE_001 只证明曾走到 20 轮；固定长度不再是 offline rollout 的质量条件，且该样本在当前语义循环、未发生完成和说话人动作所有权规则下不构成合格候选 |
| T1/T2/T3 | builder 可用，新正式实例未生成 | 旧 180 个六轮来源 instance 仅作历史审计。必须等新的最多20轮候选完成、Judge/history/人工筛选并每场景确认 1 条后重新提取三个任务；T3 只从后续 5–10 轮窗口足够且外生条件受控的 checkpoint 构造 |
| T4 | runner 与 prompt 已完成 | 被测模型使用 config 显式指定的 T4 prompt（当前示例为 task_t4_action_v17），收到自己的角色身份、explicit goal、历史自身发言 ledger 和最新可观察回应，但不接收目标人物 hidden intention、persona 数值、S/D、appraisal、delta、阈值或未来 |
| Prompt catalog | 68 个版本化 prompt | `prompts/manifest.json` 固定 SHA-256；当前 R3 显式使用 `task_t4_action_v17`、`environment_appraisal_v9` 与 `environment_response_v21`，中间 state/dynamics/ledger calibration 与数值更新为确定性代码；兼容默认值未冒充当前实验配置 |
| Talking Head | 60/60 机器生成通过 | 每个 scenario 3 个视频事件；音轨、时长、分辨率、帧率和结构检查通过，表达—状态一致性、时序、语音自然度与效用仍待真人 |
| 网站 | 已部署本机并加入当前 R3 诊断 | `127.0.0.1:8000` 的人工总清单展示 v29 短测与确切 schema 卡点；IA003 → Rollout 轨迹首条展示 v25 的19轮 rejected 样本，每轮可展开 appraisal/response event、owner/action_owner、obligation、proposal、commitment、公开事件及结束分类。人工结论只存浏览器草稿，不会晋升 rejected 样本 |
| 正式研究验收 | 未完成 | E4/E6 机器回归已通过；Gate 1、Gate 2 真人签名、R3完整轨迹自然度复核、60条新池完成、Judge/history、逐场景从3条中选1条、Gate 4 两人同样本抽查及必要仲裁均不得被工程测试替代 |

## 为什么旧数据不能继续用

旧开发池和其 180 个 Task 是在 6 轮上限下生成的。它们可以证明早期代码路径曾运行，但不能检验长期目标保持、跨阶段适应、恢复能力或长期历史下的任务结果。新版 offline 协议允许 1–20 轮自然结束；`meaningless_premature_ending` 只拒绝轮数越界、结束元数据矛盾或 20 轮前错误使用 `max_turns`，不再因长度不足 20 本身拒绝。筛选器在所有候选 REJECT 时不再强行挑 winner。

## 新的最多20轮生成方案

- 每场景只生成 3 条高质量候选，每条最多20轮并允许自然结束；模型族不设配额，最终每场景只按质量选最合适的1条。当前 Qwen3-32B 三 seed 与 Qwen3.5-9B 对照尚未得到 IA001 人工可接受候选，不能按机器通过率强行选取。
- Qwen3.5-9B 只承担统一 environment，不作为本轮 policy，避免同模型自演自评。
- 每条生成后立即检查 1–20 轮、10–20 主候选窗口、连续 turn ID、ending 与实际终止一致、对话结构、未来承诺与已完成区分、隐藏信息泄漏和跨说话人动作所有权；近重复、话题时长与焦点切换先作为诊断信号并接受语义复核。失败样本进入 rejected，替代采样 seed 与原因写入 progress.json。
- 生成完成后依次运行 Rollout Judge v2、确定性二审audit、history dependence、Protocol v1 和人工比较；筛选前不构建新 Task。
- 32B Qwen 是当前四张48GB GPU布局下可稳定常驻的较大本地模型。更大的235B/671B MoE需容纳完整权重并占用多卡，会挤掉独立 environment/Judge；GLM-4-32B量化版仍应做同配置部署实验，不能只凭参数名替换。

## T4 被测模型合同

每轮给被测模型：

- `role.name`：公开角色名；
- `role.role`：模型必须扮演的社会身份；
- `role.explicit_goal`：贯穿20轮的任务目标；
- 公开背景、目标人物公开身份、已经观察到的对话、最新回应、表情和媒体。

明确不给：environment hidden intention、persona 数值、S/D、appraisal、delta、trigger conditions 和 future branches。自然结束或预算结束前不调用终局 judge；自动 judge 五维结果仍需真人校准。

## 当前剩余顺序

1. 完成并复验20×3质量优先候选池；失败槽位替代采样，不把旧六轮数据补丁式升级。
2. Gate 1由1人冻结20个 scenario；Gate 2由1人审 E1/E2 与 E3–E5 样本；E4/E6 机器回归已完成，不降低阈值。
3. 对新池执行双 Judge、history dependence、backbone sensitivity 与 Protocol v1；Gate 3由1人主审，第二人确定性 audit 20% 与争议项。
4. 网站展示新池全部需人工比较的候选；每场景确认唯一 canonical trajectory，再重新提取 T1/T2/T3。
5. Gate 4 两人独立审完全相同的10%分层样本，只有分歧才由第三人仲裁；Video由1人审核60个资产。
6. 抽查通过后才可把全量机器建议答案发布为明确标注来源的 audited-machine GT；只有 `verify_gate_md.py --strict` 和所有真人证据通过后才能 freeze/release。

工程状态与研究结论分开记录；没有落盘证据的项目保持 pending。
