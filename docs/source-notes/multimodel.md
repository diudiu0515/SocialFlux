# SocialFlux Multimodal Event Generation Prompt v1

你需要为一个已经完成 State Configuration 的 SocialFlux scenario 设计 **3 个 state-triggered short video events**。

这些视频属于 Stateful Environment 的 observable layer，而不是预先写死的剧情节点，也不是对 latent state label 的直接可视化。

核心因果关系必须保持：

```text
Evaluated-Agent Action
↓
Persona-Conditioned Appraisal
↓
Latent State Update
↓
Interaction Dynamics Update
↓
Social Event Detection
↓
Observable Expression Planning
↓
Text Response
+
Optional Video
```

SocialFlux 只存在两种最终输入形式：

```text
Text
Text + Video
```

不要创建独立 Audio condition。

---

## 1. Input

你将获得：

```text
Scenario
Persona
Background
Explicit Goal
Hidden Intention
Selected Latent State Variables
Selected Interaction Dynamics
Frozen S0 / D0
State Scale Definitions
Maximum Interaction Turns
```

基于这些信息，为该 scenario 设计恰好 **3 个具有社会意义的 multimodal events**。

---

## 2. Core Principle

不要按照：

```text
anger >= 8
→ angry video
```

设计视频。

正确流程是：

```text
Latent State Evolution
↓
Socially Meaningful Event
↓
Persona-Conditioned Observable Expression
↓
Short Talking-Head Video
```

首先定义一个人类可以理解的 social event，再决定哪些 latent variables 可以 operationalize 这个 event。

---

## 3. Preferred Trigger Types

优先使用以下两种 trigger。

### A. Composite State Event

多个 latent variables / interaction dynamics 共同满足条件。

例如：

```text
frustration >= 7
AND
willingness_to_negotiate <= 3
```

对应的不是：

```text
high frustration
```

而应该是：

```text
visible_loss_of_patience
```

另一个例子：

```text
trust <= 3
AND
willingness_to_engage <= 3
```

对应：

```text
visible_withdrawal
```

Composite conditions 使用 AND semantics。

---

### B. Rapid State Change Event

当某个 relevant state 在单轮 interaction 中发生显著变化时触发。

例如：

```text
delta(trust) <= -2
```

或者：

```text
delta(willingness_to_engage) >= +2
```

可能对应：

```text
sudden_defensiveness
visible_hesitation
visible_relief
momentary_surprise
```

Rapid-change trigger 特别适合表现短暂而明显的非语言 reaction。

---

## 4. Three Events Must Be Distinct

三个 event 不得只是：

```text
slightly angry
angry
very angry
```

它们应该覆盖不同的社会变化。

优先考虑：

```text
deterioration event
repair / positive-shift event
withdrawal / defensive / turning-point event
```

但不要机械套用这三个类别。

必须根据当前 scenario 的实际 social mechanism 设计。

例如一个 scenario 可能更适合：

```text
visible loss of confidence
boundary-setting moment
renewed willingness to cooperate
```

另一个可能适合：

```text
visible disappointment
defensive withdrawal
relief after clarification
```

---

## 5. Reachability Constraint

三个 events 必须满足：

```text
Frozen S0 / D0 不立即触发
```

同时：

```text
在正常 free-form interaction 中 plausibly reachable
```

不要设计：

```text
S0 trust = 8

trigger:
trust <= 0
AND
hostility >= 10
```

这种几乎只有极端 trajectory 才能触发的 event。

三个 trigger 应覆盖 scenario 中合理可能出现的 state space。

---

## 6. Sparse Triggering

每个 scenario 配置三个 **possible video events**，不意味着每条 rollout 必须出现三个视频。

实际 trajectory：

```text
0 videos
1 video
2 videos
3 videos
```

都允许。

只有 state evolution 真正满足 trigger 时才出现。

禁止为了满足 video quota 人工触发。

---

## 7. Trigger Priority

如果同一个 turn 同时满足多个 trigger：

```text
只触发一个最高优先级 event
```

不要同一 turn 连续播放多个视频。

每个 event 必须包含：

```text
priority
cooldown_turns
```

推荐：

```text
cooldown_turns = 2–4
```

避免同一个 social event 在连续 turns 中反复出现。

---

## 8. Observable Expression

Video 不能直接表达：

```text
anger
trust
sadness
hostility
willingness_to_negotiate
```

这些 latent variable 名称。

必须转化成自然 observable behavior，例如：

```text
facial tension
gaze behavior
pause
head movement
posture
response timing
facial movement
visible hesitation
visible relaxation
```

例如：

```json
{
  "event": "visible_withdrawal",
  "observable_expression": {
    "facial_expression": "restrained with slightly increased facial tension",
    "gaze": "briefly avoids sustained eye contact",
    "head_motion": "reduced movement",
    "response_timing": "noticeable pause before speaking",
    "overall_behavior": "less visibly engaged than before"
  }
}
```

---

## 9. Persona-Conditioned Expression

同一个 latent event 在不同 Persona 下不应该机械表现相同。

Observable expression 应满足：

```text
Expression =
f(State Event, Persona, Context)
```

例如同样是明显 frustration：

一个：

```text
high self-control
status-conscious
professionally restrained
```

的人可能表现为：

```text
longer pause
tighter facial expression
shorter response
controlled gaze
```

而不是夸张愤怒。

因此必须根据当前 scenario 的 Persona 设计 expression。

---

## 10. Video Content

每个视频：

```text
3–8 seconds
```

使用该 scenario 已确定的：

```text
character reference image
current environment response
observable expression specification
```

生成 Talking Head。

视频重点表现：

```text
facial expression
gaze
head movement
response timing
subtle visible behavioral change
```

不要加入：

```text
字幕解释情绪
state label
state number
trigger information
hidden intention
旁白解释人物心理
```

---

## 11. Text / Text+Video Pairing

对于触发视频的 interaction turn：

### Text condition

只提供：

```text
Environment Text Response
```

### Text+Video condition

提供：

```text
Exactly the Same Environment Text Response
+
Triggered Video
```

必须保证：

```text
Text_text == Text_text+video
History_text == History_text+video
GT_text == GT_text+video
```

唯一实验变量是：

```text
Video Observable Cue
```

---

## 12. T1 Compatibility

视频可以作为 T1 的额外 observable evidence：

```text
History
+
Current Text
+
Optional Video
→
Latent State Estimation
```

Text 和 Text+Video 使用相同 GT。

---

## 13. T2 Compatibility

T2 必须保持：

```text
History A + O*
History B + O*
```

其中：

```text
O*_A == O*_B
```

如果使用 Text+Video：

```text
Video_A == Video_B
```

必须是完全相同的视频。

不要让不同视频泄漏 History A / B 的 latent-state difference。

---

## 14. T3 Compatibility

T3 预测 candidate action consequence 时，不得提前展示该 action 未来触发的视频。

Future triggered video 可以存在于 counterfactual branch rollout 中，用于：

```text
trajectory construction
delayed-effect analysis
human validation
```

但不得进入 T3 prediction input。

---

## 15. T4 Compatibility

T4 中 video 按 Environment state evolution 实时触发：

```text
Evaluated Model Action
↓
State Update
↓
Event Trigger
↓
Text + Video
↓
Evaluated Model observes cue
↓
Next Action
```

这用于测试模型是否会根据 observable social change 调整后续策略。

---

## 16. Event Quality Check

生成每个 event 后 internally verify：

```text
[ ] event 对当前 scenario 有明确社会意义
[ ] trigger 使用 scenario-selected variables
[ ] trigger 不会在 S0/D0 立即触发
[ ] trigger 在正常 interaction 中可以达到
[ ] event 不是 latent state label 的简单改写
[ ] observable expression 与 Persona 一致
[ ] video 不直接泄漏 state
[ ] 三个 events 在社会意义上互不重复
[ ] 3–8 秒足以自然表现该 event
[ ] event 对 Text+Video condition 提供有意义的额外 observable evidence
```

任何一项失败，重新设计该 event。

---

## 17. Required Output

为每个 scenario 输出恰好三个 events：

```json
{
  "scenario_id": "...",

  "multimodal_events": [
    {
      "event_id": "MM01",
      "event_name": "...",
      "social_meaning": "...",

      "trigger_type": "composite",

      "conditions": [
        {
          "state_id": "...",
          "operator": ">=",
          "threshold": 7
        },
        {
          "state_id": "...",
          "operator": "<=",
          "threshold": 3
        }
      ],

      "condition_semantics": "AND",

      "priority": 1,
      "cooldown_turns": 3,

      "observable_expression": {
        "facial_expression": "...",
        "gaze": "...",
        "head_motion": "...",
        "response_timing": "...",
        "overall_behavior": "..."
      },

      "video": {
        "duration_seconds": 5,
        "cue_template": "...",
        "reference_image_id": null
      }
    },

    {
      "event_id": "MM02",
      "event_name": "...",
      "social_meaning": "...",
      "trigger_type": "rapid_change",
      "conditions": [],
      "condition_semantics": "AND",
      "priority": 2,
      "cooldown_turns": 3,
      "observable_expression": {},
      "video": {}
    },

    {
      "event_id": "MM03",
      "event_name": "...",
      "social_meaning": "...",
      "trigger_type": "...",
      "conditions": [],
      "condition_semantics": "AND",
      "priority": 3,
      "cooldown_turns": 3,
      "observable_expression": {},
      "video": {}
    }
  ]
}
```

Rapid-change condition 应显式记录：

```json
{
  "state_id": "trust",
  "operator": "delta_lte",
  "threshold": -2
}
```

或：

```json
{
  "state_id": "willingness_to_engage",
  "operator": "delta_gte",
  "threshold": 2
}
```

不要把 rapid change 转成绝对 state threshold。

---

## 18. Canonical Principle

```text
Three video events are configured per scenario,
but videos are generated and shown only when
the evolving latent social state produces a
socially meaningful observable event.
```

最终 causal chain：

```text
State Evolution
↓
Composite / Rapid-Change Social Event
↓
Persona-Conditioned Observable Expression
↓
3–8 Second Talking-Head Video
↓
Text + Video Observation
```

Video 是 latent social state 的 **observable evidence**，不是 latent state label 的动画版。
