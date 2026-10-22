# SocialFlux：面向多维社会状态理解与目标驱动互动的多模态benchmark

# **Motivation and key insights**

我们希望评测：模型能否根据历史和多模态线索理解人物状态，预测行动后果，并在实际互动中完成指定任务。

- 社会状态具有多个维度。情绪缓和不代表信任恢复，愿意合作也不代表没有不满。建模state：Emotion、Behavioral Disposition、Relationship、Interaction Risk。 同时对state进行追踪

- 外在表达需要结合历史解释。例如，老师仍然生气，但为了维持合作而微笑；相同表达在不同前史下可能对应不同状态。 

- 行动的即时与延迟影响可能不同。暂时缓和矛盾的回应，也可能损害后续合作。 

- 理解与行动能力可能脱节。模型能识别状态、预测后果，不一定能在实际互动中采取合适行动。 

# **Most relevant work and differences**

# **Current progress and structure**

```Plain Text
Scenario candidates
        ↓
      Gate 1
        ↓
Environment initialization (S0)
        ↓
      Gate 2
        ↓
   Free rollout
        ↓
      Gate 3
        ↓
 T1–T4 construction
        ↓
      Gate 4
        ↓
Human verification / annotation
        ↓
 Benchmark freeze
```

## Environment

appraise：intermediate reasoning layer that interprets an observed action relative to the character's persona, goals, intention, relationship history, and current state before updating the latent state\.

state transition: emotion \+ behavior\_disposition \+ relationship \+ interaction risk  S\_t和S\_t\+1 

- Emotion :当前情绪状态，typically fast \- changing

- Behavioral Disposition ：当前行动倾向，context\-dependent, often medium \- changing 

- Relationship ：对另一角色的关系状态，typically slow \- changing 

- Interaction Risk : 当前互动失控／冲突／任务失败风险，may change rapidly or accumulate over history

response：llm\-based，接入claude

## Scenario

initialize：Persona \+ Background \+ Explicit Goal \+ Hidden Intention（不变）

llm \- visible context : role \+ observable scenario context \+ explicit task goal \+ interaction history \+ current multimodal observation

Environment \- private context : full persona \+ background \+ explicit / hidden intention \+ latent social state \+ appraisal / state \- transition variables

rollout：自由

S0:四维初始化

## Task

offline\+online online框架采offline数据

现在怎么样→怎样的过去造成现在→未来该如何做→if you were him

task1:输入完整历史 \+ 当前 checkpoint，预测目标角色状态强度、变化方向、证据，输出state\+evidence 答案来自environment的llm（存在私有端）

task2：输入共享前史\+ History A 分歧历史\+改编历史B \+ 相同identical current observation / matched endpoint observation，输出：目标角色的状态差异方向\+ A/B 各自的证据节点\+ 造成差异的关键选择  答案llm生成

task3：输入目标角色、完整可观察历史、当前 checkpoint 和若干 candidate actions；模型预测每个行动对目标角色社会状态的 immediate / delayed effects。主任务不提供 latent state；额外设置 Oracle\-State condition，分析显式 state information 对 consequence prediction 的影响。 主要依赖人工annotation

task4：没有正确答案，基于ending和trajectory测评Goal Achievement、State Adaptation、Risk Management、Recovery、Relationship Outcome llm和人同时打分，提取evaluation prompt

## Gate

Gate 1 — Scenario Quality：筛故事本身能不能用。检查社会合理性、人物动机、真实 trade\-off、history necessity、场景多样性，以及是否天然支持 T1–T4。 llm\+人工

Gate 2 — Environment Validity：筛这个世界会不会合理演化  实验

**Transition validity**：  $S_t\rightarrow S_{t+1}$ 是否符合人类判断 人工

**Timescale validity**：不同 state dimensions 是否表现出合理、context\-dependent 的变化速度 

**History sensitivity**：改变 history/persona 是否产生合理的 state 差异 

**Trajectory plausibility**：完整长期演化是否自然、一致 人工

**Multimodal consistency：**检查生成的 facial expression、prosody、gesture 是否与 intended observable cues 一致，同时避免泄露完整 latent state。

Gate 3 — Rollout Quality：筛模型在这个世界里跑出来的这条完整对话能不能用，自由 rollout 后，检查 Coherence、History Dependence、Character Consistency、State–Response Consistency、Interaction Progression、Naturalness。 llm主筛，人工抽取 

Gate 4 — Task Quality：筛从好 trajectory 里切出来的题是不是好题。分别检查 T1 是否真的需要历史、T2 是否做到 different history \+ identical current observation、T3 是否有非平凡的 plausible actions 和可靠的 immediate/delayed effects。 llm初筛\+给答案，人工抽子集

目前主要完成了框架和开发流程，正式人工标注与完整模型评测尚未完成。

## Multimodal

api：seedance/minimax

Offline：evidence\-driven sampling。 优先给以下 checkpoint 制作多模态：state 明显变化、语言与 latent state 不完全一致、相同/相似文本在不同 history 下应被不同解释、T1/T2 中视觉/语音线索能够提供增量信息。不要单纯追求覆盖率。

Online：event\-triggered generation。 当 state transition 较大、risk 上升/恢复、emotion 与 outward response 存在 tension、关键 negotiation/recovery turn 出现时触发 multimodal response；可以适当提高触发率，但不要每几轮固定来一个视频。

# **Expected results**

1\.经验证的多维社会状态交互环境。 

2\.覆盖 T1–T4 的多模态基准：先核验20个开发场景，再扩展至约300个。 

3\.人工审核／标注答案、经人工校准的 T4 评分协议，以及模型评测结果。 



