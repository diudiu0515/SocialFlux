# EmoTree：核心优势与需要避免的问题

## 1. EmoTree 的核心定位

> **EmoTree is a stateful on-policy benchmark for evaluating whether LLMs can understand, anticipate, and adapt to the social-emotional consequences of their own actions over long-horizon interactions.**

EmoTree 不只是测试模型能否识别情绪，而是测试：

```text
Understand → Predict → Act → Observe Consequence → Adapt → Recover
```

即：模型能否理解当前社会状态、预测自己行为的后果、采取行动，并在自己的行为改变环境后继续调整甚至修复互动。

---

## 2. EmoTree 真正值得强调的优势

### 2.1 Stateful Social Interaction

EmoTree 不只建模单一 emotion score，而是维护多维社会状态：

```text
State
├── Emotion
│   ├── anger
│   ├── anxiety
│   └── frustration
├── Relationship
│   ├── trust
│   ├── respect
│   └── hostility
├── Motivation
│   ├── willingness_to_negotiate
│   └── maintain_authority
└── Risk
    ├── escalation_risk
    └── relationship_breakdown_risk
```

优势在于：社会互动的后果不再被压缩成“开心/生气”，而可以描述关系、动机和风险如何共同变化。

### 2.2 Explicit Longitudinal State Dynamics

历史不是简单作为更长的 prompt 输入，而是通过状态持续影响未来：

```text
History + Current State + Current Action + Persona
                    ↓
              State Update
                    ↓
              Future Behavior
```

可以形式化为：

```text
S_{t+1} = F(S_t, H_t, A_t, P)
```

因此，同一句话在不同历史和不同当前状态下可以产生不同后果。

### 2.3 Action → State → Observation → Action 的因果闭环

这是 EmoTree 最应该强调的部分：

```text
Evaluated LLM
     ↓
   Action
     ↓
State Transition
     ↓
S_t → S_{t+1}
     ↓
Observable Consequence
     ↓
Evaluated LLM observes it
     ↓
Next Action
```

模型不是旁观一条固定 trajectory，而是自己的行为会改变后续环境。

### 2.4 Reasoning–Action Gap

EmoTree 可以同时测试：

```text
T3：模型认为某个行为会造成什么后果？
                    ↓
On-policy：模型实际会不会采取这个行为？
```

例如模型正确预测“威胁会增加 hostility”，但真实互动时仍然选择威胁，就出现：

> **Reasoning–Action Gap / Know–Do Gap**

因此可以研究：

> 模型“知道怎么做”是否意味着模型“真的会这么做”。

### 2.5 State-Aware Adaptation

当模型自己的行为已经让环境发生变化后，测试它是否会改变策略：

```text
OPEN
 ↓
模型行为
 ↓
GUARDED
 ↓
出现 observable cue
 ↓
模型是否调整下一步行为？
```

这比单轮回答质量更接近长期社会智能。

### 2.6 Recovery after Self-Induced Failure

模型犯错并不是直接判负，而是继续观察：

```text
Bad Action
   ↓
Negative State Transition
   ↓
Observable Cue
   ↓
Recognize?
   ↓
Repair?
```

可以进一步定义：

- Recovery Rate
- Recovery Latency
- Error Cascade Rate

从而测试模型是否能修复自己造成的社会后果。

### 2.7 Diagnostic + On-Policy Unified Evaluation

EmoTree 可以把离线推理任务和真实互动放进同一个环境：

```text
T1：Can you understand the current state?
T2：Can you understand history-dependent differences?
T3：Can you predict action consequences?
On-policy：Can you actually behave appropriately?
Adaptation：Can you react to the consequence?
Recovery：Can you repair your own mistakes?
```

这样模型失败时可以进一步诊断失败来源，而不只是得到一个总分。

---

## 3. 哪些内容不能作为 EmoTree 的主要 Novelty

以下设计已经有较强相关工作，不能单独作为贡献：

| 设计 | 已有相关工作 | EmoTree 应该怎么处理 |
|---|---|---|
| Persona | SAGE、InCharacter、SOTOPIA | 作为基础组件 |
| Explicit Goal | SAGE、SOTOPIA | 作为基础组件 |
| Hidden Intention | SAGE | 可以使用，但不能声称首次提出 |
| Dynamic Emotion | SAGE | 必须进一步扩展到多维 state dynamics |
| Emotion Trajectory | SAGE | 需要扩展到完整 social-state trajectory |
| Open Multi-turn Interaction | SOTOPIA、AgentSense | 作为环境形式，不是主要 novelty |
| Social Scenario | SOTOPIA、AgentSense 等 | 重点放在系统化构建和状态机制 |
| LLM Judge | 大量已有工作 | 不能作为核心贡献 |
| Persona Fidelity | InCharacter | 可以借鉴其验证方法 |

因此不要把论文贡献写成：

```text
We introduce Persona.
We introduce emotional agents.
We introduce social goals.
We introduce multi-turn interaction.
```

这些都不足以区分 EmoTree。

---

## 4. 与最接近工作的区别

### 4.1 SAGE vs EmoTree

SAGE 更接近：

```text
Interaction
    ↓
Emotion_t
    ↓
Emotion_{t+1}
    ↓
Agent Response
```

EmoTree 应该进一步变成：

```text
LLM Action_t
     ↓
Multi-dimensional State Transition
     ↓
S_t → S_{t+1}
     ↓
Observable Consequence
     ↓
LLM Action_{t+1}
     ↓
Adapt / Fail / Recover
```

所以 EmoTree 不应强调“我们也有动态 Emotion Agent”，而应该强调：

> **模型是否能够适应由自己行为造成的长期社会状态变化。**

### 4.2 SOTOPIA vs EmoTree

SOTOPIA 已经有开放式 on-policy social interaction，因此“让两个 Agent 自由聊天”不是 EmoTree 的 novelty。

EmoTree 更应该强调显式状态：

```text
History + Persona + S_t + Action_t
                ↓
          Transition Engine
                ↓
             S_{t+1}
                ↓
          Future Interaction
```

这样可以分析：

- 为什么互动发生变化？
- 哪一次行为导致 trust 下降？
- 模型有没有发现 hostility 上升？
- 模型是否因此调整策略？
- 模型能不能恢复关系？

---

## 5. 需要特别避免的问题

### 5.1 避免变成“SAGE + SOTOPIA 的拼装”

最大的 reviewer 风险是：

```text
Persona / Hidden Intention → SAGE
Open Interaction → SOTOPIA
Emotion Theory → EmotionBench
Scenario Construction → AgentSense
```

然后 reviewer 问：EmoTree 自己的新东西是什么？

因此核心贡献必须放在它们之间的新结构：

```text
Model Action
→ Explicit State Dynamics
→ Observable Consequence
→ Model Adaptation
→ Long-term Trajectory
```

### 5.2 避免变成普通 Emotion Recognition Benchmark

不要把核心问题写成：

> “模型能不能识别导师现在生气？”

应该是：

> “模型能不能理解自己之前的行为如何改变了导师当前的情绪、关系和动机，并据此调整下一步行为？”

### 5.3 避免 State 完全拍脑袋

不能直接规定：

```text
threaten → anger +20
apologize → trust +10
```

然后把这些作者规则直接当作 ground truth。

需要通过：

- 心理学 / 社会心理学理论；
- Human Annotation；
- Human Validation；
- 不同 transition design 的 ablation；

证明 state direction 和 trajectory 基本合理。

### 5.4 避免完全依赖 LLM Judge

Agent self-evaluation 可以作为一个 signal，例如：

```text
How much do you trust the student?
How satisfied are you with this interaction?
Would you continue working with them?
```

但最终 evaluation 应结合：

```text
Agent Self Evaluation
+ Environment State
+ Goal Achievement
+ Human Evaluation
```

并验证 automatic score 与 human judgment 的一致性。

### 5.5 避免 Threshold 变成人为硬规则

Threshold 是有潜力的设计，但必须验证。

例如：

```text
hostility 59 → GUARDED
hostility 61 → HOSTILE
```

如果行为突然完全不同，可能显得机械。

因此需要比较：

```text
Full EmoTree
vs
No Threshold
```

只有当 threshold 能提高 trajectory plausibility、model differentiation 或 adaptation/recovery 分析能力时，才应该保留并强调。

### 5.6 避免变成“越礼貌分越高”

Scenario 必须包含真实 trade-off，例如：

- 自我权益 vs 关系维护
- 公平 vs 权力关系
- 诚实 vs 情绪支持
- 道德原则 vs 个人利益
- Goal Achievement vs Relationship Preservation

否则 benchmark 最后可能只是在测模型是否会说礼貌的话。

### 5.7 避免只看 Final Score

两个模型最终都达到同一个结果，但过程可能完全不同：

```text
Model A：稳定协商 → 达成目标
Model B：激化冲突 → 补救 → 达成目标
```

因此 EmoTree 应该评价完整 trajectory，而不仅是 terminal outcome。

### 5.8 避免把 Simulator State 当成人类真实心理

EmoTree 应明确定位为：

> **A controllable social-emotional test environment, not a perfect simulation of human psychology.**

`trust=63` 不代表真实人类存在一个客观的“63 分信任值”，它只是用于构建可控、可比较、可分析环境的 latent simulator variable。

---

## 6. EmoTree 最值得保住的核心

如果后续设计越来越复杂，可以用下面六点判断某个模块是否真的服务于核心问题：

```text
1. Multi-dimensional Social State

2. Explicit Longitudinal State Dynamics

3. Model Action → State Change 的闭环

4. Reasoning–Action Gap

5. State-Aware Adaptation

6. Recovery after Self-Induced Failure
```

其中最核心的是：

```text
             Evaluated LLM
                   ↓
                 Action
                   ↓
          Stateful Environment
                   ↓
             S_t → S_{t+1}
                   ↓
          Observable Consequence
                   ↓
             Evaluated LLM
                   ↓
        Understand / Adapt / Recover?
```

---

## 7. 一句话区分 EmoTree 与已有工作

> **EmoTree does not merely evaluate whether an LLM can recognize social-emotional states or perform well in social interactions; it evaluates whether the model can understand, anticipate, and adapt to evolving social states that are causally changed by its own previous actions.**

更简洁地说：

> **The key question is not only whether an LLM understands the social state, but whether it can act on that understanding as its own actions continuously reshape the environment.**

---

## 8. 当前 Novelty 优先级

```text
Persona                                  × 已有
Goal                                     × 已有
Hidden Intention                         × 已有
Dynamic Emotion                          × 已有
Open Social Interaction                  × 已有
Social Scenario                          × 已有

Multi-dimensional Social State           ★★★
Explicit Longitudinal State Dynamics     ★★★★
Action → State causal loop               ★★★★★
Reasoning → Action comparison            ★★★★★
State-sensitive Adaptation               ★★★★★
Recovery after self-induced failure      ★★★★★
T1/T2/T3 + On-policy unified evaluation  ★★★★★
```

因此，后续所有设计和实验最好围绕最后几项展开，而不是继续增加 Persona、Emotion Label 或故事数量。
