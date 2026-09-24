# SocialFlux Rollout Strategy

## 1. Core Principle

SocialFlux 的 offline T1/T2/T3 数据必须来自 **同一个 online stateful environment 中自由演化得到的完整 trajectories**。

不使用预设 Repair / Neutral / Escalation 策略生成数据。

统一流程：

```text
Scenario
↓
Frozen initial state and machine-validated runtime dynamics seed
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

当前正式主线由 `claude-fable-5` 承担场景、policy、environment 与任务构建，
但每个语义 role 都是独立请求。GPT-50 只用于在 scale 前做端到端设计审计；
它不自动并入 Claude 主数据。

---

## 3. Model provenance

模型名称、route hash、sampling、seed、请求次数和失败状态都必须记录，
但不得用 model family quota 或多个 seed 搜索更好看的轨迹。

---

## 4. Cross-model audit

其他强模型可作为独立 judge、漏洞复核或消融实验，但不通过补抽扩大每场景的
rollout 数量。跨模型结果必须与主数据隔离并标明用途。

---

## 5. Rollout Sampling

每个 Gate-1-approved scenario 只生成一条自由 rollout：

```text
one frozen scenario × one policy slot × one seed
```

技术重试可以处理 transport 或 schema 故障，但不能生成可供择优的替代轨迹。
唯一轨迹失败时，该场景在当前批次失败，并计入原始分母。

---

## 6. Quality admission

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
broken dialogue logic
meaningless premature ending
nonsensical state oscillation
implementation-induced state saturation
future-information leakage
unusable trajectory
```

Gate 3 对唯一轨迹做 pass/fail：全部质量与证据条件通过才 materialize 为
canonical trajectory；不进行去重排名、seed 比较或 winner selection。T1/T2/T3
只从通过的唯一轨迹构建。T2 的 B history 和 T3 的局部分支是任务内受控干预，
不算额外 natural rollout。

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

旧 development rollouts 已移出活跃目录并单独归档。它们只能用于可追溯的历史方法审计，不得被 pipeline 自动发现，也不得进入当前或 final benchmark。

新的 development batch 必须使用独立 manifest/output root；development rollout 不自动进入 final benchmark。

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

Automatic/model output 用于：

```text
filtering
quality control
compatibility checking
machine label proposal
```

Formal T1/T2/T3 label release 采用：

```text
Machine Proposal
↓
Two Humans Review the Same Deterministic 10% Sample
↓
Agreement / Disagreement-only Adjudication
↓
Formal GT
```

两名 reviewer 必须独立且检查完全相同的样本；一致 reject 触发修复，只有
分歧时使用不同的第三名 reviewer。Machine proposal 不得伪装成人工标签。

---

## 13. Scale plan

第一阶段：

```text
50 GPT-authored scenarios
×
1 rollout
×
all T1/T2/T3/T4 stages and multi-model audit
```

检查：

```text
quality pass rate
scenario coverage and trajectory yield
history dependence
rollout length
state stability
task yield, leakage and judge disagreement
```

人工复核漏洞报告并冻结设计后，再启动最多 200 个 Claude 主场景；每场景仍只
生成一条 rollout。旧 Scale300 已归档，不作为 compatibility baseline。

正式阶段：

```text
Primary:
Claude-authored scenarios and Claude single rollouts

Audit:
GPT design-probe artifacts kept separate
```

最终保留：

```text
quality-admitted
+
history-dependent
+
fully provenance-bound
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
