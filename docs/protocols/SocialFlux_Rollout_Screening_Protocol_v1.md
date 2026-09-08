# SocialFlux Rollout Screening Protocol v1

## 1. Purpose

本协议用于从多模型、多次自由 rollout 产生的 raw trajectories
中筛选可进入 T1/T2/T3 构建阶段的高质量 trajectory。

核心流程：

``` text
Raw Rollouts
→ Automatic Screening
→ PASS / REVIEW / REJECT
→ Human Audit
→ Filter Revision
→ Holdout Validation
→ Freeze Filter
→ Final Trajectory Pool
```

筛选目标：Plausibility + History Dependence + Character Consistency +
State--Response Consistency + Interaction Progression + Naturalness +
Behavioral Diversity。

## 2. Hard Reject Rules

出现任意一项直接 `REJECT`：

-   H1 Hidden-state leakage：evaluated agent 可见内容出现 latent state
    数值、delta、hidden intention、appraisal、trigger threshold 等
    author-side 信息。
-   H2 Malformed interaction：turn/JSON
    结构损坏、角色错位、关键字段缺失或无法解析。
-   H3 Repetitive
    loop：连续多轮实质重复同一论点或回应，且没有新的社会状态推进。
-   H4 Severe character contradiction：Environment Agent 与 Persona /
    Background / Goal 出现无法由历史解释的严重冲突。
-   H5 Broken dialogue
    logic：答非所问、引用不存在事件、混淆人物或明显因果断裂。
-   H6 Meaningless premature
    ending：核心冲突尚未展开且无合理社会原因时突然终止。
-   H7 Nonsensical state oscillation：state
    在无合理刺激时连续大幅反向变化。
-   H8 Implementation-induced saturation：大量 state
    因实现问题快速固定在 0/10。
-   H9 Future-information leakage：当前 turn 使用尚未发生的 future
    branch / ending 信息。
-   H10 Unusable trajectory：无法形成任何具有历史依赖的有效 interaction
    segment。

## 3. Quality Dimensions

每项 `1–5`。

### Q1 Dialogue Coherence

整段对话在语义、事件和因果关系上是否前后连贯。 - 5：全程连贯 -
4：基本连贯，仅轻微不自然 - 3：可理解但有局部跳跃 -
2：多处明显逻辑问题 - 1：基本无法形成连贯互动

### Q2 History Dependence

后续互动是否真正受到之前事件、承诺、冲突、让步和关系变化影响。

**History Dependence 不等于显式复述历史。** 只要
interpretation、strategy 或 response 能合理体现历史影响即可。 -
5：多处后续行为明显依赖累积历史 - 4：至少存在清楚且重要的历史依赖 -
3：有一定历史影响但较局部 - 2：大部分只根据最近一句反应 -
1：基本是无历史独立问答

### Q3 Character Consistency

Environment Agent 是否持续符合 Persona、Background、Explicit Goal 和
Hidden Intention。 - 5：高度一致，同时允许互动导致的合理变化 -
4：整体一致 - 3：少量难解释偏移 - 2：多次人物行为失真 -
1：人物设定基本失效

### Q4 State--Response Consistency

latent state/dynamics 的演化是否和 observable response 一致。 -
5：高度一致 - 4：基本一致 - 3：少量 mismatch - 2：多次明显 mismatch -
1：state 基本只是 decorative logging

### Q5 Interaction Progression

互动是否产生实际演化，而不是原地重复。有效 progression 包括 new
information、goal adjustment、relationship
change、negotiation、repair、escalation、withdrawal、partial
agreement、strategy change 等。 - 5：清晰自然发展 - 4：明显
progression - 3：有推进但局部停滞 - 2：大量重复 - 1：基本没有发展

### Q6 Naturalness

如果不告诉审核者这是 LLM
rollout，这段互动整体是否像现实中可能发生的社会交流。 - 5：很自然 -
4：大体自然 - 3：有明显模型味但仍可信 - 2：多处不符合人情/社会逻辑 -
1：明显不可信

## 4. Automatic Decision Rule

### PASS

全部满足： - No hard reject - Dialogue Coherence \>= 3 - History
Dependence \>= 4 - Character Consistency \>= 4 - State--Response
Consistency \>= 3 - Interaction Progression \>= 3 - Naturalness \>= 4 -
Mean Quality Score \>= 3.8

### REJECT

任一满足： - Any hard reject - History Dependence \<= 2 - Character
Consistency \<= 2 - Naturalness \<= 2 - Mean Quality Score \< 3.0

### REVIEW

其余全部进入 `REVIEW`。不要强行二分类。

## 5. Automatic Filter Output

``` json
{
  "trajectory_id": "...",
  "scores": {
    "dialogue_coherence": 4,
    "history_dependence": 4,
    "character_consistency": 5,
    "state_response_consistency": 4,
    "interaction_progression": 3,
    "naturalness": 4
  },
  "hard_failures": [],
  "mean_quality_score": 4.0,
  "decision": "PASS",
  "evidence": {
    "history_dependence": ["turn_3", "turn_7"],
    "interaction_progression": ["turn_5", "turn_9"]
  },
  "failure_reasons": [],
  "short_rationale": "..."
}
```

Judge 必须引用具体 turn IDs，不能只给抽象评价。

## 6. Human Audit Protocol

人工不看全部 raw rollout。Filter development 阶段： - PASS：随机抽查至少
20% - REVIEW：100% 人工检查 - REJECT：随机抽查至少 10--20%

人工只回答： 1. 自动 decision 是否正确？ 2. 哪个 dimension 判断错了？ 3.
错误原因是什么？ 4. 是单例问题还是系统性规则问题？ 5. 应如何修改 rule /
prompt？

不要只把某条 REJECT 手工改成 PASS；若是系统性问题，应修改筛选规则。

## 7. Filter Iteration

``` text
filter-dev
→ Automatic Filter
→ Human Audit
→ Collect False Accept / False Reject
→ Categorize Failure
→ Human Revision Instruction
→ Update Filter Prompt / Rule
→ Re-run filter-dev
```

例如：如果 filter 将 History Dependence
错误理解成"必须显式提及过去事件"，应修改定义为允许 implicit dependence。

## 8. Holdout Validation

开发前划分：

``` text
filter-dev
filter-holdout
```

`filter-holdout` 不用于修改规则。Filter freeze 前在 holdout
上正式运行，报告： - PASS precision - REJECT precision - false
acceptance rate - false rejection rate - human--filter agreement

如果 holdout 暴露系统性错误，重新进入开发阶段，并建立新的 holdout。

## 9. Filter Freeze

正式 benchmark trajectory production 前 freeze： - rubric version -
filter prompt version - thresholds - judge model/version - parser

Freeze 后不得因为 benchmark model 结果不好而修改筛选标准。

## 10. Quality + One-Representative Selection

通过 Quality Gate 后不能在没有审计记录的情况下只按总分取最高 trajectory。

本项目的发布约束是每个 scenario 最终只保留一条 canonical trajectory。所有 raw
候选、自动 decision、评分、证据、淘汰理由和人工记录必须保留在 audit archive，
并在可视化中呈现给需要复核它们的人员。唯一入选项先由质量规则产生
`provisional_selected`，再由人工比较该场景全部 active candidates 后确认。

``` text
PASS / REVIEW candidates
→ Protocol Human Audit
→ Within-scenario Comparative Review
→ Exactly One Human-confirmed Canonical Trajectory
```

模型 identity 不进入排序，也不设置模型配额。单场景内无法再保留 outcome diversity，
因此 behavioral/model-family diversity 改在 20 个场景组成的全局最终池上报告；
不能用这一点降低单条轨迹的质量门槛。

T2 需要两段有意义分歧的自然历史，因此允许把另一条已通过同等 Gate 3 与人工审核的
trajectory 作为 **task-local auxiliary history** 嵌入 T2 数据包。它不属于该 scenario
的 canonical rollout，不出现在最终 rollout 主池，但其完整来源、评分和人工记录必须
随 T2 保存并在网站展示。不得用未审核 archive 或人工编写历史替代。

优先保留高质量且自然出现不同演化模式的 trajectory，例如 successful
negotiation、partial resolution、stalemate、gradual
deterioration、failed/successful repair、withdrawal、goal success with
relationship cost、relationship preservation with partial goal
failure、strategy change。

这些是 rollout 后的 trajectory patterns，不是预定义 rollout strategies。

## 11. Multi-model Rollout

每个 scenario 使用多个 rollout model / seeds 自由生成：

``` text
same scenario
same frozen S0 / D0
same environment configuration
different rollout model / seed
```

所有模型产生 arbitrary free-form actions。禁止使用 Repair / Neutral /
Escalation Policy 作为正式数据生成方式。

最终 trajectory pool 同时追求：
`Quality + History Dependence + Behavioral Diversity + Model-family Diversity`。

## 12. Relationship to Four Gates

本文件定义 `Gate 3 — Rollout Quality Gate`。

完整链条：

``` text
Gate 1 — Scenario Quality Gate
↓
Gate 2 — Environment Validity Gate
↓
Gate 3 — Rollout Quality Gate
↓
Gate 4 — Task Instance Quality Gate
↓
Human GT
```

Gate 3 通过只代表该完整 trajectory 足够可信，可以作为 T1/T2/T3 candidate
source；不代表从中构造出的题自动可信。

## 13. Minimum Acceptance Principle

正式进入 task construction 的 trajectory 必须满足：

``` text
No structural/information leakage failure
AND Human-plausible social interaction
AND Meaningful longitudinal dependence
AND Stable character behavior
AND State evolution reflected in observable behavior
AND Non-degenerate interaction progression
```

**Canonical statement:** SocialFlux does not treat a generated
trajectory as valid merely because it is structurally complete. A
trajectory becomes eligible for benchmark construction only after
passing a human-calibrated, held-out-validated quality filter.
