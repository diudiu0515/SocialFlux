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

每个 `scenario_NNN/` 的 JSON 是机器事实源，同名 Markdown 是确定性生成的人类说明，含故事初始化、S0/D0、视频阈值、质量状态与 rollout 位置。JSON 改动后必须运行 `scripts/scenario_docs.py`；`--check` 校验 Markdown 内 SHA-256 与 catalog/coverage matrix。

影视来源只允许贡献高层社会机制。`extract-structure` 的结构合同强制记录必须丢弃的表层元素以及原创化要求；后续 source 必须使用新人物、新场域、新事件、新 stakes 和原创语言，不复制台词、角色或标志性情节序列。

## Prompt 和 schema

所有固定模型指令只放在 `prompts/`，文件名以 `_vN.md` 结尾。运行时代码通过 `prompts.loader` 加载并校验 manifest hash；`scripts/update_prompt_manifest.py` 是唯一登记命令。模型结构化输出分别由 `schemas/` 合同和 Python validator 约束。完整职责映射见 `PROMPT_AUDIT.md`。

## Instance 质量

T1/T2/T3 均绑定持有 latent state 的环境角色，而不是输出 action 的 evaluated model。结构审计检查无泄漏、目标 state、历史形状、精确重复、T2 双方角色与 private-state 分化、T3 checkpoint/branch 完整性；轨迹审计另报 action/response 唯一率、简洁性和 latent 边界占比。语义质量采用移除 model/provider/trajectory provenance 的盲化 packet。九项验收自动读取该质量报告；轨迹质量未过时不得标 Full-Trajectory provisionally ready。自动或 LLM 分数均不能替代 human answerability 与标签有效性评审。

## 验收

当前 gate 固定为九项：State-Update Human Agreement、Persona Sensitivity、Paraphrase Robustness、History Intervention、Local Action Intervention、Neutral-State Stability、Response-State Consistency、Full-Trajectory Plausibility、Seed Robustness。自动结构证据只能标为 pending/evidence_ready/provisionally_ready；需要真人的项目没有评审记录不得标 pass。

## 架构不变量

- 正常生成不得出现固定 action taxonomy 或 scripted trajectory。
- 同一 canonical environment 必须用于离线和 T4。
- T1/T2/T3 必须由自然轨迹派生。
- T3 干预必须 restore 同一真实 checkpoint。
- LLM judge 不是 human ground truth。
- 公开实例不得泄漏 private fields。
- 未批准 scenario 默认拒绝正式 rollout。
- secrets 只来自环境变量，公开 manifest 删除 secret 及环境变量名。
