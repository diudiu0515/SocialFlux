# SocialFlux Rollout Strategy

## 1. Core Principle

SocialFlux 的 offline T1/T2/T3 数据必须来自 **同一个 online stateful environment 中自由演化得到的完整 trajectories**。

不使用预设 Repair / Neutral / Escalation 策略生成数据。

统一流程：

```text
Scenario
↓
Frozen S0 / D0
↓
Stateful Environment
↓
Free-form Model Rollout
↓
Trajectory Pool
↓
Rollout Quality Gate
↓
T1 / T2 / T3
```

---

## 2. Rollout Model Strategy

为降低 API 成本，正式 rollout 采用：

```text
Open-source / locally deployed models
作为主要 trajectory generators

+

少量强 API models
作为补充 trajectory generators
```

目标不是让最强模型生成“最好看的对话”，而是获得：

```text
Quality
+
Behavioral Diversity
+
Model-family Diversity
```

---

## 3. Recommended Rollout Pool

### Main Local Rollout Models

优先选择当前能力较强、适合多轮 instruction-following 的开源模型，例如：

```text
Qwen 20–30B class instruct model
GLM open-weight model where compute permits
DeepSeek open-weight instruct model where compute permits
other strong 20–40B open models
```

在现有 4 × 48GB GPU 条件下，优先使用能够稳定部署的 20–30B 级模型。

不强求所有模型都使用最大规模版本。

---

## 4. API Models as Supplementary Rollout Sources

API 不作为主要数据来源。

只选择少量不同 family 的强模型，例如：

```text
Qwen flagship API
GLM flagship API
Kimi flagship API
DeepSeek flagship API
```

用途：

```text
增加 trajectory diversity
验证 local model trajectory distribution 是否过窄
补充复杂 social interaction cases
```

建议 API trajectory 只占最终 trajectory pool 的：

```text
20%–30%
```

其余主要由开源模型生成。

---

## 5. Rollout Sampling

每个 scenario 首先生成多个自由 rollout：

```text
Local Model A × multiple seeds
Local Model B × multiple seeds
Local Model C × multiple seeds

+
optional API Model × 1–2 runs
```

不要每个 scenario 只生成一条 trajectory。

也不要简单保留最高分 trajectory。

最终选择目标：

```text
High Quality
+
Non-duplicate
+
Behaviorally Diverse
```

---

## 6. Quality + Diversity Selection

所有 raw trajectories 先通过 Rollout Quality Gate。

评分维度：

```text
Dialogue Coherence
History Dependence
Character Consistency
State–Response Consistency
Interaction Progression
Naturalness
```

Hard reject：

```text
hidden-state leakage
malformed output
repetitive loop
severe character contradiction
meaningless premature ending
nonsensical state oscillation
implementation-induced state saturation
```

通过后，再做 diversity filtering。

不要：

```text
12 trajectories
→ 只留下最高分 1 条
```

而应该：

```text
12 trajectories
→ Quality Gate
→ 去重
→ 保留 4–6 条质量高但演化不同的 trajectories
```

---

## 7. Diversity Criteria

希望保留自然出现的不同互动结果，例如：

```text
successful negotiation
gradual deterioration
stalemate
failed repair
successful repair
goal success with relationship damage
relationship preservation with partial goal failure
strategy change during interaction
withdrawal
```

这些是 rollout 后观察到的 trajectory patterns，不是预定义策略。

---

## 8. History Dependence Check

Rollout model 本身不需要被证明为完美的 longitudinal reasoner。

但进入正式 trajectory pool 的 trajectory 必须体现 history dependence。

对抽样 trajectory 做：

```text
Full History
vs.
Recent-k History
```

以及：

```text
Full History
vs.
Critical Event Removed
```

如果关键历史被移除后，agent 行为和 environment interpretation 几乎完全不受影响，则该 trajectory 不适合作为 history-sensitive benchmark source。

---

## 9. Development vs Final Rollout

当前已有 Qwen development rollouts 可以继续用于：

```text
pipeline debugging
builder testing
schema testing
quality-gate development
```

但最终 benchmark 应重新生成 heterogeneous trajectory pool。

Development rollout 不自动进入 final benchmark。

---

## 10. Environment and Rollout Model Separation

Environment backbone 与 rollout agent 尽量不要长期固定为同一个模型。

例如：

```text
Rollout Model A
↕
Environment Model B
```

并在 environment validation 中抽样进行 simulator-backbone sensitivity test。

这样减少：

```text
self-play bias
same-model preference
same-family language-style bias
```

---

## 11. Judge Strategy

不要用昂贵 frontier model 参与大规模 normal rollout。

强模型主要用于：

```text
Rollout Quality Judge
T2 Compatibility Judge
Task Quality Pre-filter
T4 Automatic Judge
```

例如：

```text
GPT-5.6 Sol
Claude Fable 5.x
```

使用方式：

```text
Primary Judge
+
Second Judge on stratified subset / disagreement cases
```

无需所有 trajectory 双 judge。

---

## 12. Formal Ground Truth

Automatic judge 只用于：

```text
filtering
quality control
compatibility checking
```

Formal T1/T2/T3 GT 仍然采用：

```text
Human Annotation
↓
Agreement
↓
Adjudication
↓
Formal GT
```

---

## 13. Recommended Cost-Controlled Production Plan

第一阶段：

```text
20 scenarios
×
2–3 local rollout models
×
3 seeds
```

检查：

```text
quality pass rate
trajectory diversity
history dependence
rollout length
state stability
```

确认 pipeline 后再扩到完整 scenario pool。

正式阶段：

```text
Majority:
local open-source rollout

Minority:
strong API rollout
```

最终保留：

```text
quality-filtered
+
diversity-filtered
+
history-dependent
```

trajectory pool。

---

## 14. Key Principle

```text
The strongest model is not necessarily the best data generator.

SocialFlux needs a diverse set of coherent,
history-dependent social trajectories,
not a collection of uniformly optimal conversations.
```

因此 rollout generation 的目标是：

$$
\boxed{
Plausibility
+
History\ Dependence
+
Diversity
+
Reproducibility
}
$$

而不是：

$$
\boxed{
Maximum\ Model\ Capability
}
$$
