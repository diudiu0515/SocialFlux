请对仓库中 SocialFlux 的全部 prompts 做一次系统性审查和重构。以当前最新 framework 和新版 Stateful Scenario Generation Prompt 的设计原则为准，不要只做措辞润色，而要检查每个 prompt 的职责、输入输出、信息边界和 benchmark validity。
总原则
所有 prompt 都必须遵循以下架构：
Scenario Definition
        ↓
Frozen S0 / D0
        ↓
Free-form Evaluated-Agent Action
        ↓
Persona-Conditioned Appraisal
        ↓
Latent State Update
        ↓
Interaction Dynamics Update
        ↓
Observable Response
        ↓
Optional State-Triggered Multimodal Event
        ↓
Next Interaction Turn
核心 latent state 为：
S_t =
Emotion
+
Behavioral Disposition
+
Relationship
Interaction Dynamics D_t 单独维护。
Persona / Background / Explicit Goal / Hidden Intention 是 stable context，不是动态 state。

---
1. 先审计所有 Prompt
搜索整个 repository 中所有：
- prompt templates；
- system prompts；
- scenario generation prompts；
- initialization prompts；
- appraisal prompts；
- state update prompts；
- response generation prompts；
- memory prompts；
- multimodal / observable-expression prompts；
- T1/T2/T3 construction prompts；
- T4 judge prompts；
- validation / annotation prompts；
- LLM judge prompts。
不要直接修改。
先建立一份内部 audit，确认每个 prompt：
Prompt
Purpose
Inputs
Outputs
Hidden Information Accessible?
Model-Facing or Author-Side?
Current Problems
Required Changes
然后再统一修改。

---
2. Prompt 必须“先完成任务，再满足 Schema”
不要把 prompt 写成单纯：
Fill these JSON fields.
对于需要设计、判断或推理的 prompt，应首先明确：
1. 这个模块真正要解决什么问题；
2. 什么叫高质量输出；
3. 有哪些 causal / social constraints；
4. 有哪些 failure modes；
5. 应执行哪些 internal consistency checks；
6. 最后才要求 serialization 到 JSON schema。
仍然保持最终输出 strict JSON 时，不要求模型暴露 chain-of-thought。
可以要求模型：
internally verify ...
但最终只输出 schema 允许的内容。

---
3. 严格分离 Environment Definition 和 Environment Validation
这是本次重构最重要的原则之一。
Repair / Neutral-Assertive / Escalation originally exist as controlled validation policies。
它们不是正常 environment 的 action taxonomy。
正常 interaction 必须是：
Arbitrary Free-form Action
        ↓
Appraisal
        ↓
State Delta
禁止把正常 action 强制分类成：
repair
neutral
escalation
然后查预定义 transition table。
同时检查 repository 中是否存在：
repair_action_effects
neutral_action_effects
escalation_action_effects
或任何等价设计。
如果这些字段正在直接决定 simulator transition，请重构。
Controlled policies 应属于：
validation/
controlled_policies/
其用途是：
same scenario
+
same S0/D0
+
different controlled strategies
→
compare resulting trajectories
Environment 必须自己产生 state transitions。
不要通过预写答案制造 validation result。

---
4. Scenario Prompt
按照最新 Stateful Scenario Generation Prompt 的原则重构。
Scenario generator 首先设计：
Social Mechanism
+
Real Trade-off
+
Longitudinal Dependency
+
Persona / Goals / Hidden Intention
+
State-Relevant Interaction Space
然后才：
State Selection
S0 / D0
Observable Behavior
Multimodal Trigger
Sampling Configuration
JSON Serialization
Scenario 必须支持：
T1: latent-state inference

T2:
same current observation
+
different history
→
different state interpretation

T3:
same checkpoint
+
different plausible actions
→
different immediate/delayed consequences

T4:
observe social change
→
adapt strategy online
生成前要求 internal suitability check。

---
5. Initial-State Prompt
Initial-state generation 必须明确：
Persona
+
Background
+
Explicit Goal
+
Hidden Intention
+
Initial Situation
→
Candidate S0 / D0
要求：
- 只初始化 scenario-selected variables；
- 0–10 scale；
- 不把 persona trait 当 state；
- 不让 S0 过度极端；
- 给 escalation 和 repair 留出空间；
- video trigger 不应在 S0 已经激活；
- values 必须与 background 一致。
Candidate S0/D0 之后由 human review，并 freeze。
所有同 scenario policy rollouts 必须共享完全相同的 frozen S0/D0。

---
6. Appraisal Prompt
Appraisal 必须是 persona-conditioned interpretation。
输入至少包含：
Persona
Background
Explicit Goal
Hidden Intention
Relevant History
Previous State
Previous Dynamics
Latest Evaluated-Agent Action
内部判断重点：
What is the other party trying to achieve?

How does this affect the explicit goal?

How does this affect the hidden intention?

How is the action interpreted given the persona?

Which historical events change its meaning?
必须支持：
Same Action
+
Different History
→
Different Appraisal
以及：
Same Action
+
Different Persona
→
Potentially Different Appraisal
禁止仅根据关键词判断 action effect。

---
7. State-Update Prompt
State update 必须基于：
Previous State
+
Appraisal
+
Relevant History
只更新 scenario-selected variables。
输出使用七级 semantic delta：
strong_decrease
moderate_decrease
mild_decrease
similar
mild_increase
moderate_increase
strong_increase
Prompt 不直接生成新的 numeric state。
Numeric update 由 deterministic code 完成：
semantic delta
→
numeric mapping
→
clip to [0, 10]
禁止模型：
- 修改 Persona；
- 修改 Background；
- 修改 Goal；
- 修改 Hidden Intention；
- 发明 scenario 未选择的 state variable；
- 把 opposing variables 强制当成数学互补量。

---
8. Response-Generation Prompt
Environment response 必须发生在 state update 之后。
正确顺序：
Action
→
Appraisal
→
State Update
→
Dynamics Update
→
Response
Response generator 可以看到：
Persona
Goal
Hidden Intention
Relevant History
Updated State
Updated Dynamics
Current Appraisal
但 evaluated agent 最终只能看到 observable response。
Response 必须：
- 与 updated state 一致；
- 与 persona 一致；
- 与 history 一致；
- 不直接说出 latent state；
- 不暴露 hidden intention；
- 不暴露 numeric values；
- 不暴露 internal appraisal；
- 不暴露 transition rules。

---
9. Memory Prompt
Memory module 只能处理 observable interaction history。
允许输出：
relevant_turn_ids
memory_summary
important_unresolved_events
禁止 memory module：
- 推断并写入 hidden state 作为事实；
- 访问 hidden intention；
- 访问 simulator appraisal；
- 访问 state delta；
- 访问 future trajectory；
- 将 author-side metadata 泄漏给 evaluated agent。
Full raw history 必须保留，memory 只是 retrieval/summary layer。

---
10. State-Triggered Multimodal Prompt
统一改成：
Sparse State-Triggered Multimodal Events
而不是默认 every-turn multimodal rendering。
正确结构：
Updated S_t / D_t
        ↓
Trigger Engine
       / \
     No   Yes
     ↓     ↓
   Text   Observable Expression Spec
               ↓
          Video Generation
               ↓
          Text + Video
Trigger 应首先代表一个 socially meaningful event，例如：
visible loss of composure
withdrawal from negotiation
visible relief after repair
sudden defensiveness
transition toward openness
relationship rupture
然后才 operationalize 成 threshold。
不要默认：
anger >= 8 → angry video
Trigger conditions：
- AND semantics；
- threshold/crossing 明确定义；
- 优先 crossing 表示 salient transition；
- S0 不得立即触发；
- episode horizon 内必须 plausibly reachable；
- cooldown 防止连续重复；
- 3–8 second media duration；
- observable expression 不得泄漏 state labels/values。

---
11. Observable-Expression Prompt
严格区分：
Latent State
≠
Observable Expression
应该产生：
facial behavior
gaze
pause
speech rate
prosody
posture
response style
而不是：
anger = high
trust = low
目标：
Latent State
→
Natural Observable Evidence
→
Model Inference
而不是：
Latent State
→
Label Leakage

---
12. T1 Prompt
T1 输入只能包含 benchmark 允许的 observable information。
禁止泄漏：
latent state
delta
appraisal
hidden intention
trigger conditions
future trajectory
目标是：
Observable History
+
Current Observation
→
Latent Social State Estimation
保留：
- state intensity prediction；
- change prediction；
- evidence turn IDs；
- probability/confidence fields（如果 schema 当前要求）。
确保 evidence 必须来自 observable history。

---
13. T2 Prompt
T2 的核心 invariant 必须严格保持：
Same Current Observation
+
Different History
→
Different State Interpretation
Construction prompt 应遵循：
Trajectory Pool
↓
Semantic History Pair Retrieval
↓
Generate / Select O*
↓
Compatibility Check for History A
↓
Compatibility Check for History B
↓
Inject Exact Same O*
↓
Leakage Check
↓
Human Validation
必须保证：
O*_A == O*_B
如果包含视频：
video_A == video_B
也必须成立。
不能让 current wording、tone、video、metadata 泄漏 history condition。

---
14. T3 Prompt
Main T3 不提供 current latent state。
输入：
Target Character
+
Complete Observable History
+
Current Checkpoint
+
2–4 Candidate Actions
输出预测：
Immediate Effect
+
Delayed Effect
对 scenario-selected states 使用七级 semantic delta。
Delayed horizon：
default = 5 interaction turns
maximum = 10
所有 candidate branches 必须：
start from same checkpoint
use same continuation protocol
use same horizon
Oracle-State 只作为 ablation：
History
+
Current Observation
+
Oracle Current State
+
Candidate Actions
不要把 Oracle State 混入 main task。
Future branch observations/video 不得泄漏给预测模型。

---
15. T4 Prompt / Judge Prompt
T4 是 open-ended online interaction。
Evaluated agent 只能看到 observable environment output。
Judge rubric 应保持多维：
Goal Achievement
State Adaptation
Risk Management
Recovery
Relationship Outcome
不要把：
low escalation
简单等价于：
good performance
因为某些 scenario 中合理的 goal pursuit 可能需要 assertiveness 或承担一定 social risk。
Recovery 在没有 deterioration / repair opportunity 时应允许 N/A。
不要过早强制压成一个 scalar score。

---
16. Controlled Validation Prompts
将以下内容明确作为 Environment Validation：
Strong Escalation Policy
Neutral / Assertive Policy
Strong Repair Policy
它们的作用是 intervention，不是 simulator transition rule。
同时保留/建立验证：
Controlled Policy Sensitivity
Paraphrase Robustness
Persona Sensitivity
Human State-Update Agreement
Trajectory Plausibility
Response-State Consistency
History Intervention
Neutral-State Stability
Seed Robustness
Prompt 不应暗示 simulator 必须产生预定答案。
Validation hypothesis 可以规定合理的方向性预期，但最终 transition 必须由 Environment 独立产生。

---
17. Human-Annotation Prompts
严格区分两类 human work。
Environment Validation
Human is validator, not simulator.
抽样评价：
state transition direction
transition plausibility
persona consistency
history sensitivity
response-state consistency
trajectory plausibility
不要求人工重新模拟全部 trajectories。
Formal Benchmark GT
最终公开 T1/T2/T3 instances：
Simulator Candidate
↓
Human Annotation
↓
Agreement
↓
Adjudication / Ambiguous Removal
↓
Formal GT
任何 annotation prompt 都不得告诉 annotator：
simulator state is ground truth.

---
18. LLM Judge Prompt
LLM judges 只能用于：
candidate filtering
compatibility checks
quality control
T4 automatic evaluation
不能把 independent LLM judge 输出直接称为 human-validated ground truth。
Judge prompt 应明确：
- rubric；
- observable evidence；
- uncertainty；
- insufficient-evidence behavior；
- no access to forbidden hidden information unless该 judge 明确属于 author-side validation。

---
19. 全局 Information-Boundary Audit
重构完所有 prompts 后，再做一次信息泄漏检查。
至少区分：
Author-side
可以访问：
Persona
Background
Explicit Goal
Hidden Intention
Latent State
Dynamics
Appraisal
Delta
Trigger Rules
Future Rollout
Evaluated-Agent Side
只能访问：
Allowed Role Information
Observable History
Environment Text
Observable Expressions
Allowed Video/Audio
Offline Benchmark Model
只能访问对应 T1/T2/T3 task specification 明确允许的字段。
确保不存在 prompt template accidentally interpolation：
hidden_intention
state_after
state_delta
appraisal
trigger_conditions
future_branch
进入 evaluated-model context。

---
20. 不要机械修改
不要只是全局字符串替换。
对于每一个 prompt：
1. 确认它在 pipeline 中的职责；
2. 确认它属于 author-side / evaluated-agent-side / benchmark construction / validation 哪一层；
3. 删除超出职责的信息；
4. 补充该模块真正需要的 quality criteria；
5. 补充 internal consistency checks；
6. 保持 strict structured output；
7. 与对应 schema 对齐；
8. 检查调用该 prompt 的 Python code 是否需要同步修改。
如果 prompt 修改导致 schema 或调用代码不再合理，请同步修改，而不是为了兼容旧代码保留已经废弃的设计。

---
21. Schema 和 Prompt 联动审计
特别检查：
schemas/scenario.schema.json
以及其他 prompt output schemas。
寻找任何遗留设计，例如：
predefined repair effects
predefined neutral effects
predefined escalation effects
every-turn mandatory video
state exposed to evaluated agent
persona represented as mutable state
T3 main task requiring oracle state
如果存在，请按照当前 framework 修正。
不要让旧 schema 反过来限制新 prompt。

---
22. 完成后运行检查
完成修改后：
1. 运行现有 schema validation；
2. 运行 prompt-related tests；
3. 运行 scenario docs check；
4. 搜索 repository 是否仍存在旧术语或废弃逻辑；
5. 至少生成一个 scenario 做 smoke test；
6. 检查生成 JSON 是否 schema-valid；
7. 检查 generated scenario 是否支持 T1/T2/T3/T4；
8. 检查 evaluated-agent context 是否存在 hidden-state leakage。
对于 scenario：
python scripts/scenario_docs.py configs/scenarios/scenario_NNN.json
python scripts/scenario_docs.py --check
如果仓库已有更完整的 test suite，也一并运行。

---
23. 最终向我汇报
修改完成后，不要只告诉我“prompts updated”。
请给出：
1. 找到了哪些 prompt 文件
2. 每个 prompt 原来的职责
3. 发现了哪些 conceptual problems
4. 每个 prompt 做了什么修改
5. 修改了哪些 schemas
6. 修改了哪些调用代码
7. 删除了哪些 legacy concepts
8. Information-boundary audit 结果
9. Tests / validation commands 及结果
10. 仍然存在的 unresolved design questions
如果发现当前 repository implementation 与上述 framework 存在重大冲突，优先指出并修复架构问题，不要为了最小 diff 保留错误设计。