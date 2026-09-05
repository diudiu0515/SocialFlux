# SocialFlux Architecture

## 总体数据流

```text
film/TV analysis request / synthetic brief
        ↓
originalized structure extraction / original script
        ↓
source quality report → real reviewer approval
        ↓
canonical blueprint (no S0/D0)
        ↓
candidate S0/D0 + trigger specification → real reviewer freeze
        ↓
one canonical StatefulEnvironment
        ├── natural multi-model / multi-seed rollout
        ├── T1 natural checkpoints
        ├── T2 naturally divergent histories + exact shared O*
        ├── T3 local branches from one real checkpoint
        └── T4 online free interaction
        ↓
nine-criterion acceptance + human annotation
```

## 唯一环境

`ModelEnvironmentFactory` 同时服务离线 rollout 与 T4，每轮严格按以下顺序执行：

1. 向 evaluated model 暴露 observable observation。
2. 接收任意自由文本 action。
3. 从可观察历史检索 memory；完整原始历史始终是权威记录。
4. `ModelAppraiser` 私下结合 persona、目标、hidden intention、S_t/D_t 与历史解释 action。
5. `ModelStateUpdater` 仅根据 appraisal 输出七级 semantic delta；确定性 mapper 将其映射到 0–10，并把边界裁剪后的标签归一到真实数值变化。
6. `ModelResponseGenerator` 在更新后的状态上生成自然回应。
7. trigger engine 检测 threshold/crossing/state-change，并只公开安全 expression/media。
8. logger 保存 private master trajectory；公开 task builder 必须通过 leakage audit。

环境没有 action interpreter、action effects 表、response template 或固定策略 runner。

## 信息边界

| 层 | 可见 | 禁止进入 |
|---|---|---|
| Evaluated policy / T4 | 角色、背景、显式目标、可观察历史、回应、expression、media | hidden intention、S/D、appraisal、delta、阈值、未来 |
| T1/T2/T3 输入 | 任务所需可观察历史/checkpoint/候选自由文本 | private trajectory fields、作者假设、模型生成答案 |
| Author-side environment | persona、hidden intention、S/D、相关 observable memory、action | 未来轨迹或预设 action 结果 |
| Human annotation | 冻结的公开实例、rubric、独立证据要求 | simulator delta 作为 ground truth |
| Website | 研究者视角 scenario 与本地 private rollout | 写入或第二套状态机 |

## 轨迹和局部干预

自然轨迹的多样性来自模型、temperature、seed 和自然历史，不来自策略类别。每条 run 保存 base seed；OpenAI-compatible provider 按 base seed + call index 推进随机流，既可复现又避免每回合重置同一采样。T2 先从同场景同深度的自然轨迹检索不同历史，再生成一个对双方都合理且字节级共享的 O*；模型对比时只在同来源模型内配对，并按来源模型分层轮询。T3 从真实 checkpoint restore 同一 private snapshot，为 2–4 个自由文本行动各执行一次局部 intervention，随后继续使用与源轨迹匹配的同一模型配置。受控 intervention 是实验工具，不是多轮 rollout policy。

## Scenario bundle

每个 `scenario_NNN/` 的 JSON 是机器事实源，同名 Markdown 是确定性生成的人类说明，含故事初始化、S0/D0、视频阈值、质量状态与 rollout 位置。每次 rollout 后，同目录 `rollouts/dialogues.md` 逐轮描述完整自然对话，`rollouts/tasks.md` 逐 instance 描述 T1/T2/T3 公开题面和隔离的私有诊断，供人工抽查。JSON 改动后必须运行 `scripts/scenario_docs.py`；`--check` 校验 Markdown 内 SHA-256 与 catalog/coverage matrix。

S0/D0 的候选值与真人冻结协议见 `S0_D0_REVIEW.md`。Talking Head 使用 `media/talking_head/manifest.json` 作为媒体事实源：每个 scenario 两条状态触发视频，请求只含公开表演指令，不泄漏 hidden state、阈值或任务答案；生成后由收集器验证视频流、音轨、时长、分辨率和帧率，再将 media ID 回填 scenario。网站通过受限 `/media/<asset_id>` 路由读取清单中的 MP4，不接受任意文件路径。

影视来源只允许贡献高层社会机制。`extract-structure` 的结构合同强制记录必须丢弃的表层元素以及原创化要求；后续 source 必须使用新人物、新场域、新事件、新 stakes 和原创语言，不复制台词、角色或标志性情节序列。

## Prompt 和 schema

所有固定模型指令只放在 `prompts/`，文件名以 `_vN.md` 结尾。运行时代码通过 `prompts.loader` 加载并校验 manifest hash；`scripts/update_prompt_manifest.py` 是唯一登记命令。模型结构化输出分别由 `schemas/` 合同和 Python validator 约束。完整职责映射见 `PROMPT_AUDIT.md`。

## Instance 质量

T1/T2/T3 均绑定持有 latent state 的环境角色，而不是输出 action 的 evaluated model。结构审计检查无泄漏、目标 state、历史形状、精确重复、T2 双方角色与 private-state 分化、T3 checkpoint/branch 完整性，并按 source model 与 scenario 双重汇总；轨迹审计另按 scenario 报 action/response 唯一率、简洁性和 latent 边界占比。语义质量采用移除 model/provider/trajectory provenance 的盲化 packet。九项验收自动读取该质量报告；轨迹质量未过时不得标 Full-Trajectory provisionally ready。自动或 LLM 分数均不能替代 human answerability 与标签有效性评审。

## 验收

当前 gate 固定为九项：State-Update Human Agreement、Persona Sensitivity、Paraphrase Robustness、History Intervention、Local Action Intervention、Neutral-State Stability、Response-State Consistency、Full-Trajectory Plausibility、Seed Robustness。自动结构证据只能标为 pending/evidence_ready/provisionally_ready；需要真人的项目没有评审记录不得标 pass。

`gate.md` 在九项环境验收之外约束正式数据来源：每场景至少 12 条、至少三种本地模型族、至少一个 20–40B 本地模型、API 不超过 30%、environment/policy 模型分离、六维质量评分、八类 hard reject、post-hoc outcome 去重后保留 4–6 条。主 Judge 覆盖全池，跨模型族第二 Judge 覆盖分层样本和争议/边缘项；`formal_selected` 的 manifest、轨迹文件与逐条质量 audit 必须 ID 完全一致，并绑定真人 scenario/S0-D0 签名、历史干预证据与双 Judge 合并记录。历史干预在同一 checkpoint 下同时比较 evaluated action 和 environment appraisal/state-delta interpretation。骨干敏感性通过同 checkpoint/action 在两个 environment backbone 下重放并比较 state-delta 方向。Gate 4 使用 T1/T2/T3 各自的实名、时间戳、实例哈希绑定人工清单；正式 GT 始终是三人标注→agreement→真人 adjudication。

## 架构不变量

- 正常生成不得出现固定 action taxonomy 或 scripted trajectory。
- 同一 canonical environment 必须用于离线和 T4。
- T1/T2/T3 必须由自然轨迹派生。
- T3 干预必须 restore 同一真实 checkpoint。
- LLM judge 不是 human ground truth。
- 公开实例不得泄漏 private fields。
- 未批准 scenario 默认拒绝正式 rollout。
- 正式 rollout 必须写入隔离的 `data/formal/`，不得复用开发轨迹。
- 单 Judge、同模型族双 Judge 或缺失历史/骨干证据不能生成 formal_selected。
- selected manifest、文件或 quality-audit ID 不一致时不得构建任务。
- secrets 只来自环境变量，公开 manifest 删除 secret 及环境变量名。
