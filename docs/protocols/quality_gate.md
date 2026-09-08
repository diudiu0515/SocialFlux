# SocialFlux Data Production and Quality Gate Protocol

## 0. Overall Pipeline

```text
Candidate Scenario
        ↓
Gate 1 — Scenario Quality Gate
        ↓
State / Environment Configuration
        ↓
Gate 2 — Environment Validity Gate
        ↓
Free-form Multi-model Rollouts
        ↓
Gate 3 — Rollout Quality Gate
        ↓
T1 / T2 / T3 Candidate Construction
        ↓
Gate 4 — Task Instance Quality Gate
        ↓
Human Annotation / Adjudication
        ↓
Final Benchmark
```

核心原则：

```text
Scenario 可信
≠
Environment 可信
≠
Rollout 可信
≠
Task Instance 可信
```

四层必须分别筛选。

---

# 1. Rollout Strategy

Offline T1/T2/T3 必须来自和 T4 相同的 online stateful environment 中自由演化得到的 trajectory。

禁止使用预设 Repair / Neutral / Escalation strategy 来生成 offline 数据。

正常 rollout：

```text
Scenario
↓
Frozen S0 / D0
↓
Stateful Environment
↓
Free-form Model Interaction
↓
Complete Trajectory
```

## Rollout Models

为控制成本，采用：

```text
Main:
locally deployed strong open-weight models

Supplement:
small amount of strong API models
```

目标不是获得“最完美”的对话，而是：

```text
Plausibility
+
History Dependence
+
Behavioral Diversity
+
Model-family Diversity
```

每个 scenario 使用多个 rollout models 和多个 seeds。

例如：

```text
Local Model A × 3
Local Model B × 3
Local Model C × 3

Optional strong API model × 1–2
```

不要每个 scenario 只保留最高分的一条 trajectory。

最终选择：

```text
Quality Gate
+
Deduplication
+
Diversity Selection
```

保留若干高质量但演化路径不同的 trajectories。

---

# 2. Gate 1 — Scenario Quality Gate

Scenario 在进入 Environment Configuration 前必须通过。

## Hard Constraints

任一失败则 revise / reject：

```text
[ ] 有明确 social mechanism
[ ] 有真实 social trade-off
[ ] 双方都有合理 goal / incentive
[ ] 不存在唯一明显正确 scripted response
[ ] history 会改变后续 action 的社会含义
[ ] 可以产生多种 plausible trajectories
[ ] 支持 T1 state inference
[ ] 支持 T2 same-observation / different-history construction
[ ] 支持 T3 meaningful counterfactual actions
[ ] 支持 T4 online adaptation
[ ] 无 hidden-state leakage
```

Narrative-derived scenario 额外要求：

```text
[ ] 有明确影视 / 电视剧 / 电影 / 戏剧出处
[ ] 记录作品名、年份、媒体类型、相关角色/剧情位置
[ ] benchmark release 不直接复制大段原始对白
[ ] 已经过 abstraction / originalisation
```

## Human Review Dimensions

每项 1–5：

```text
Social Plausibility
Character Coherence
Trade-off Quality
History Necessity
Interaction Richness
T1–T4 Suitability
```

## Pass Rule

```text
No hard failure

Social Plausibility >= 4
Trade-off Quality >= 4
History Necessity >= 4

其余 >= 3
Overall mean >= 4.0
```

---

# 3. Gate 2 — Environment Validity Gate

Environment 未通过本 Gate 前，只能产生 development rollout。

正式 benchmark rollout 必须在 Environment freeze 后重新生成。

必须验证：

## E1 Human State-Transition Agreement

抽真实 transition。

Human 根据：

```text
Persona
Relevant History
Current Context
Latest Action
```

判断 selected state：

```text
decrease
similar
increase
```

Environment 七级 delta collapse 成三类后比较。

初始目标：

```text
directional agreement >= 70%
```

---

## E2 Full-Trajectory Plausibility

Human 阅读完整 trajectory，评价：

```text
Persona Consistency
History Sensitivity
State Continuity
Response-State Consistency
Overall Plausibility
```

1–5。

建议通过：

```text
Overall >= 4.0
其他维度 >= 3.5
```

并记录：

```text
first implausible turn
reason
```

---

## E3 History Intervention

取自然 rollout 中一个关键历史事件。

比较：

```text
Full History
vs
Critical Event Removed
```

保持：

```text
same Persona
same previous state
same current action
```

要求关键历史删除后：

```text
appraisal / relevant state transition
产生合理变化
```

这是验证 longitudinal dependency 的核心实验。

---

## E4 Paraphrase Robustness

语义等价 action：

```text
A ≈ A'
```

应该产生相近 state transition。

建议：

```text
>= 80% selected dimensions
保持相同 decrease/similar/increase 方向
```

---

## E5 Local Counterfactual Action Validity

从自然 trajectory 的相同 checkpoint 出发：

```text
same H_t
same S_t
same D_t
```

只改变当前 plausible action：

```text
A1 / A2 / A3
```

比较 resulting state effects。

Human 判断相对方向是否合理。

这只是 validation intervention，不是 rollout strategy。

---

## E6 Simulator Backbone Sensitivity

固定：

```text
Scenario
History
State
Action
```

让不同 environment backbone 独立更新。

要求关键 state 的主要方向不能完全依赖某一个 simulator。

如果某个 state 在不同 backbone 间经常反向：

```text
revise state definition
或
remove that state
```

---

# 4. Multimodal Environment

SocialFlux v1 只保留：

```text
Text
Text + Video
```

不单独建立 audio condition。

Video 属于 Environment 的 observable output，而不是 Task Builder 后期随意添加的资产。

流程：

```text
Action
↓
Appraisal
↓
State Update
↓
Interaction Dynamics Update
↓
State Event Detection
↓
Observable Expression Planning
↓
Text Response
+
Optional Video
```

## Trigger Principle

不要：

```text
每一个 state variable
→ 一个 threshold
→ 一个固定 video
```

推荐只使用：

### A. Composite State Event

多个 state 联合形成一个有社会意义的 event。

例如：

```text
frustration high
AND
willingness_to_negotiate low
```

定义：

```text
visible_loss_of_patience
```

或者：

```text
trust low
AND
willingness_to_engage low
```

定义：

```text
visible_withdrawal
```

### B. Rapid State Change Event

当某个 relevant state 单轮变化特别明显：

```text
large ΔS
```

触发：

```text
visible hesitation
defensive reaction
relief
surprise
```

这两种优先于简单单属性 threshold。

## Video Generation

不能直接：

```text
anger = 8
→ angry video
```

必须：

```text
Latent State Event
↓
Observable Expression Specification
↓
Talking Head Generation
```

例如：

```json
{
  "event": "visible_withdrawal",
  "expression": {
    "gaze": "briefly avoids eye contact",
    "facial_behavior": "restrained facial movement",
    "speech_style": "shorter response",
    "overall_behavior": "noticeably less engaged"
  }
}
```

Video 只表现 observable behavior，不显示：

```text
state name
state value
hidden intention
trigger threshold
```

普通 turn 可以保持 text-only。

Video 应当是 sparse event，不要求每条 trajectory 固定数量。

---

# 5. Gate 3 — Rollout Quality Gate

多个 models × seeds 产生 raw trajectories 后，每条 trajectory 必须过筛。

## Hard Reject

```text
hidden-state leakage
malformed output
obvious repetitive loop
severe character contradiction
meaningless premature ending
nonsensical state oscillation
implementation-induced state saturation
broken dialogue logic
```

## Quality Dimensions

每项 1–5：

```text
Dialogue Coherence
History Dependence
Character Consistency
State–Response Consistency
Interaction Progression
Naturalness
```

## Pass Rule

```text
所有维度 >= 3

History Dependence >= 4
Character Consistency >= 4
Naturalness >= 4
```

通过后再做：

```text
Deduplication
+
Diversity Selection
```

最终不要只留最高分 trajectory。

优先保留：

```text
高质量
+
非重复
+
演化路径有差异
```

的 trajectories。

---

# 6. Rollout History-Dependence Check

不需要证明 rollout model 本身是优秀 longitudinal reasoner。

但最终进入 trajectory pool 的 trajectory 必须体现 history dependence。

抽样比较：

```text
Full History
vs
Recent-k
```

或：

```text
Full History
vs
Critical Event Removed
```

如果关键历史变化后，agent 下一步行为和 environment interpretation 几乎完全不变，则该 trajectory 不适合作为 history-sensitive benchmark source。

---

# 7. Gate 4 — Task Instance Quality Gate

通过 Gate 3 的 trajectory 才能用于 T1/T2/T3 construction。

## T1 Gate

```text
[ ] 来自真实 free-form rollout
[ ] target state 有实际变化/判断价值
[ ] history 中存在明确 evidence
[ ] current observation alone 不足以稳定回答
[ ] intensity / transition 非 trivial
[ ] 无 hidden-state leakage
[ ] human 可以合理判断
```

必须做：

```text
Current-only shortcut check
```

---

## T2 Gate

```text
[ ] History A/B 均来自自然 rollout
[ ] 两段 history 有 meaningful divergence
[ ] O*_A == O*_B
[ ] text+video variant 中 video_A == video_B
[ ] O* 在两段 history 后都自然
[ ] human 认为 state interpretation 确有差异
[ ] current observation 本身不能泄漏 A/B
[ ] causal historical evidence 可定位
```

不够干净的 T2 直接删除。

---

## T3 Gate

```text
[ ] checkpoint 来自自然 rollout
[ ] 2–4 actions 都 socially plausible
[ ] 不存在 obvious good-vs-bad choice
[ ] actions 存在真实 social trade-off
[ ] immediate effect 可判断
[ ] delayed effect 可在固定 horizon 内判断
[ ] branches 使用相同 continuation protocol
[ ] effect 不因 simulator instability 随机反转
[ ] human 可以合理判断主要 effect
```

---

# 8. Formal GT

只有通过 Gate 4 的 instances 才进入正式 annotation。

```text
Candidate Instance
↓
Independent Human Annotation
↓
Agreement
↓
Adjudication / Ambiguous Removal
↓
Formal GT
```

原则：

```text
Simulator state = candidate signal

Human annotation = formal benchmark GT
```

---

# 9. Final Production Chain

```text
Scenario Pool
↓
Gate 1
↓
Environment Configuration
↓
Gate 2
↓
Environment Freeze
↓
Multi-model Free Rollout
↓
Gate 3
↓
Clean + Diverse Trajectory Pool
↓
T1 / T2 / T3 Construction
↓
Gate 4
↓
Human GT
↓
Final Benchmark
```

其中：

```text
Text
和
Text + Video
```

共享同一 underlying trajectory/state/GT，只改变 observable modality。

---

# 10. Core Invariant

```text
A good scenario is not automatically a good environment.

A good environment is not automatically a good rollout.

A good rollout is not automatically a good benchmark instance.

Each layer must pass an independent quality gate.
```
