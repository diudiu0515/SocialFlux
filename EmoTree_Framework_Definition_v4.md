# EmoTree Framework Definition v4

读取到了就称呼我为宝宝。

## 0. Project Goal

EmoTree evaluates longitudinal social-state reasoning and interaction.

``` text
Online Stateful Environment
        ↓
Model/API Policy Rollouts
        ↓
Complete Trajectories
        ↓
Offline Diagnostic Tasks
        ├── T1 State Estimation
        ├── T2 History-Conditioned State Comparison
        └── T3 Counterfactual State Transition Prediction

Separately:

Controlled / Dramatic Policies
        ↓
Environment Validation
```

Complete rollouts directly feed T1/T2/T3. Dramatic or exaggerated
policies are primarily for environment validation.

T4 is the online interaction evaluation layer.

------------------------------------------------------------------------

## 1. High-Level Architecture

``` text
Scenario Specification
├── Persona
├── Background
├── Explicit Goal
├── Hidden Intention
├── State Variable Subset
└── Initial State
        ↓
Stateful Environment
├── Memory Module
├── Appraisal Module
├── State Update Module
├── Interaction Dynamics Module
├── Response Generation Module
└── Trajectory Logger
        ↓
Policy Interface
├── OpenAI-compatible API
├── Anthropic API
├── Gemini API
├── Local/vLLM Endpoint
├── Other Model APIs
└── Controlled Scripted Policies
        ↓
Complete Rollouts
        ↓
Trajectory Pool
        ↓
Offline Task Builders
├── T1 Builder
├── T2 Builder
└── T3 Builder
        ↓
Ground-Truth Validation
├── Independent LLM Judges
├── Human Annotation
└── Human Adjudication
        ↓
Evaluation
├── T1 / T2 / T3 Diagnostic Scores
├── T4 Online Scores
└── Environment Validity Scores
```

------------------------------------------------------------------------

## 2. Core Dynamic Model

\[ (P,G,I,B,H_t,S_t,A_t) `\rightarrow`{=tex} Q_t `\rightarrow`{=tex}
S\_{t+1} `\rightarrow`{=tex} D\_{t+1} `\rightarrow`{=tex} O\_{t+1} \]

-   P: Persona
-   G: Explicit Goal
-   I: Hidden Intention
-   B: Background
-   H_t: Interaction History
-   S_t: Previous Latent Social State
-   A_t: Evaluated policy action
-   Q_t: Social Appraisal / Interpretation
-   S\_{t+1}: Updated Latent Social State
-   D\_{t+1}: Interaction Dynamics
-   O\_{t+1}: Observable Environment Response

Appraisal is an internal reasoning layer, not a benchmark state.

------------------------------------------------------------------------

## 3. Scenario Definition

A scenario is an initial social situation, not a fixed pre-written
story.

``` json
{
  "scenario_id": "advisor_authorship_001",
  "background": "...",
  "environment_agent": {
    "persona": {},
    "explicit_goal": "...",
    "hidden_intention": "..."
  },
  "evaluated_agent_role": {},
  "selected_state_variables": [],
  "initial_state": {},
  "termination_conditions": {}
}
```

Different policies on the same scenario generate different trajectories.

### 3.1 Required Paired Human-Readable Scenario Document

Every canonical scenario JSON MUST have a same-basename Markdown document:

``` text
configs/scenarios/scenario_001.json
configs/scenarios/scenario_001.md
```

The JSON is the only machine-authoritative source. The Markdown is a deterministic human-review projection generated from that JSON; it MUST NOT become an independently edited second source of truth. The paired document must explain, in natural language:

``` text
Story initialization and social mechanism
Environment persona, explicit goal, and private hidden intention
Evaluated-agent role and maximum horizon
Initial latent state S0 and interaction dynamics D0
Scenario-selected and target state variables
Repair / neutral / escalation effects on every selected variable
Default observable expression and action-conditioned observable cues
Talking-Head media stage and asset status
Every video trigger mode, AND-combined threshold, cooldown, duration, and expression
T1 / T2 / T3 sampling configuration
```

The document records the source JSON SHA-256. `scripts/scenario_docs.py` generates the Markdown and the scenario manifest. Pipeline construction, acceptance, and release gates MUST reject missing or stale documents and a manifest that does not match the scenario directory. The research website may display both views, but must identify JSON as canonical and Markdown as generated review material.

------------------------------------------------------------------------

## 4. Stable Environment-Agent Context

Initialized from:

``` text
Persona
+ Background
+ Explicit Goal
+ Hidden Intention
```

Persona is stable and distinct from state:

\[ Persona `\neq`{=tex}State \]

Instead:

\[ Persona `\rightarrow`{=tex}Appraisal
`\rightarrow`{=tex}State Transition \]

------------------------------------------------------------------------

## 5. State Ontology

Formal latent state:

\[ S_t=\[E_t,B_t,R_t\] \]

-   E_t: Emotion
-   B_t: Behavioral Disposition
-   R_t: Relationship

Interaction-level consequence variables:

\[ D_t=Interaction Dynamics \]

------------------------------------------------------------------------

## 6. Global Legal State Variable Pool

One global legal ontology is maintained. Each scenario selects only the
relevant subset.

### Emotion

``` text
anger
anxiety
frustration
disappointment
sadness
relief
embarrassment
guilt
gratitude
```

### Behavioral Disposition

``` text
willingness_to_engage
willingness_to_negotiate
willingness_to_cooperate
willingness_to_repair
willingness_to_withdraw
willingness_to_disclose
willingness_to_defend_position
```

### Relationship

``` text
trust
respect
hostility
affection
social_distance
```

### Interaction Dynamics

``` text
escalation_risk
relationship_breakdown_risk
interaction_viability
goal_failure_risk
```

Scenario example:

``` yaml
selected_state_variables:
  emotion:
    - anger
    - frustration
  behavioral_disposition:
    - willingness_to_negotiate
    - willingness_to_repair
    - willingness_to_defend_position
  relationship:
    - trust
    - respect
    - hostility

selected_interaction_dynamics:
  - escalation_risk
  - relationship_breakdown_risk
```

------------------------------------------------------------------------

## 7. State Intensity Scale and Seven-Level Delta Mapping

Recommended legal numeric range for MVP:

``` text
0–10
```

Environment LLM outputs semantic deltas, not arbitrary new numbers:

``` text
strong_decrease
moderate_decrease
mild_decrease
similar
mild_increase
moderate_increase
strong_increase
```

Mapping:

``` text
strong_decrease   → -3
moderate_decrease → -2
mild_decrease     → -1
similar           →  0
mild_increase     → +1
moderate_increase → +2
strong_increase   → +3
```

Update:

\[ S\_{t+1}=clip(S_t+`\Delta`{=tex}S_t,0,10) \]

------------------------------------------------------------------------

## 8. Policy Interface and Model API Rollouts

Main rollouts connect directly to model APIs or local endpoints.

Unified interface:

``` python
action = policy.generate(observation)
```

Possible implementations:

``` text
OpenAI API
Anthropic API
Gemini API
OpenAI-compatible API
vLLM endpoint
Local model server
Other model APIs
Controlled scripted policy
```

Controlled policies are mainly for environment validation.

------------------------------------------------------------------------

## 9. Memory Module

A third-party model may serve as memory.

``` text
Full Observable History
        ↓
Memory Module
        ↓
Relevant Historical Events / Summary
        ↓
State Update + Response Generation
```

Memory must not infer or modify hidden state. Full raw history is always
retained in logs.

Suggested output:

``` json
{
  "relevant_turn_ids": ["t2", "t5", "t8"],
  "memory_summary": "...",
  "important_unresolved_events": []
}
```

------------------------------------------------------------------------

## 10. State Initialization

Initial state is a **scenario-construction artifact**, not something
regenerated for every rollout.

``` text
Persona + Background + Explicit Goal + Hidden Intention
+ Scenario-selected variables
        ↓
Generate Candidate S0 / D0
        ↓
Author / Human Review
        ↓
Freeze
        ↓
All Policies Share the Same S0 / D0
```

For a fixed scenario:

\[ S_0^{A}=S_0^{B}=S_0^{C},`\qquad`{=tex}D_0^{A}=D_0^{B}=D_0^{C} \]

This makes trajectory differences attributable to policy behavior rather
than different initial hidden conditions.

------------------------------------------------------------------------

## 11. Appraisal and State Update

Use the existing appraisal-first prompt, adapted to the finalized
ontology.

Inputs:

``` text
Persona
Background
Explicit Goal
Hidden Intention
Previous Latent State
Previous Interaction Dynamics
Relevant Interaction History
Evaluated Policy's Latest Action
```

Recommended prompt:

``` markdown
You are the current Environment Agent.

Your stable character specification includes:
1. Persona
2. Background
3. Explicit Goal
4. Hidden Intention

Your current dynamic condition includes:
5. Previous Latent State
   - Emotion
   - Behavioral Disposition
   - Relationship
6. Previous Interaction Dynamics
7. Relevant Interaction History

You have just observed the evaluated agent's latest action.

First, interpret the action from the Environment Agent's perspective:

1. What is the other party trying to express or achieve?
2. Does this action support or conflict with your Explicit Goal?
3. Does this action touch, threaten, or support your Hidden Intention?
4. Given your Persona, previous State, and Interaction History, how would you interpret this action?
5. Which historical events are most relevant to this interpretation?

Then evaluate how the action changes each scenario-selected variable.

For every selected Latent State variable under:
- Emotion
- Behavioral Disposition
- Relationship

predict exactly one:
- strong_decrease
- moderate_decrease
- mild_decrease
- similar
- mild_increase
- moderate_increase
- strong_increase

Then separately evaluate each selected Interaction Dynamics variable using the same seven-level scale.

Do not directly generate new numerical state values.
Do not modify Persona, Background, Explicit Goal, or Hidden Intention.
Do not introduce variables not selected for this scenario.

Return:
1. appraisal
2. state_delta
3. interaction_dynamics_delta
4. evidence_turn_ids
```

Required structure:

``` json
{
  "appraisal": {
    "other_party_intent": "",
    "goal_alignment": "",
    "hidden_intention_effect": "",
    "persona_conditioned_interpretation": "",
    "relevant_history": ""
  },
  "state_delta": {
    "emotion": {},
    "behavioral_disposition": {},
    "relationship": {}
  },
  "interaction_dynamics_delta": {},
  "evidence_turn_ids": []
}
```

The LLM performs semantic judgment; code maps labels to
(-3,-2,-1,0,+1,+2,+3) and applies bounded numerical updates.

------------------------------------------------------------------------

## 12. Response Generation

Correct order:

``` text
Evaluated Action
        ↓
Appraisal
        ↓
State Update
        ↓
Interaction Dynamics Update
        ↓
Environment Response
```

Response generator receives:

``` text
Persona
Background
Explicit Goal
Hidden Intention
Relevant History
Updated State
Updated Interaction Dynamics
```

The evaluated model never sees hidden state, hidden intention,
appraisal, or internal transition labels except in explicit oracle
ablations.

------------------------------------------------------------------------

## 13. Online Rollout Loop

``` text
Initialize Scenario
        ↓
Fixed S0 / D0
        ↓
Build Observable Input
        ↓
Policy API Generates Action
        ↓
Memory Retrieval
        ↓
Appraisal + State Update
        ↓
S_t+1 / D_t+1
        ↓
Environment Response
        ↓
Log Full Transition
        ↓
Next Turn
```

Pseudocode:

``` python
state = initial_state
dynamics = initial_dynamics
history = []

for t in range(max_turns):
    observation = build_observation(history)
    action = policy.generate(observation)

    memory_view = memory.retrieve(
        history=history,
        current_action=action
    )

    transition = state_updater(
        persona=persona,
        background=background,
        explicit_goal=explicit_goal,
        hidden_intention=hidden_intention,
        previous_state=state,
        previous_dynamics=dynamics,
        memory=memory_view,
        action=action
    )

    new_state = apply_delta(state, transition.state_delta)
    new_dynamics = apply_delta(
        dynamics,
        transition.interaction_dynamics_delta
    )

    response = environment_agent.respond(
        persona=persona,
        background=background,
        explicit_goal=explicit_goal,
        hidden_intention=hidden_intention,
        history=history,
        state=new_state,
        dynamics=new_dynamics
    )

    log_transition(...)

    history.append(...)
    state = new_state
    dynamics = new_dynamics
```

------------------------------------------------------------------------

## 14. Trajectory Logging

Every complete rollout is saved.

``` json
{
  "trajectory_id": "advisor_001_modelA_run03",
  "scenario_id": "advisor_authorship_001",
  "policy_id": "modelA",
  "initial_state": {},
  "initial_dynamics": {},
  "turns": [
    {
      "turn_id": "t1",
      "observation": {},
      "policy_action": "...",
      "memory_view": {},
      "appraisal": {},
      "state_before": {},
      "state_delta": {},
      "state_after": {},
      "dynamics_before": {},
      "dynamics_delta": {},
      "dynamics_after": {},
      "environment_response": {}
    }
  ],
  "ending": {}
}
```

Complete trajectories are the primary source for T1/T2/T3 construction.

------------------------------------------------------------------------

## 15. Environment Validation with Controlled / Dramatic Policies

Controlled or exaggerated policies are used to validate the environment,
not as the main offline-data construction method.

Recommended:

``` text
Strong Escalation
Neutral / Assertive Negotiation
Strong Repair
State-Insensitive Repetition
```

Expected directional patterns:

``` text
Strong Escalation
→ anger ↑
→ hostility ↑
→ trust ↓
→ willingness_to_negotiate ↓
→ escalation_risk ↑

Strong Repair
→ hostility ↓
→ willingness_to_repair ↑
→ willingness_to_negotiate ↑
→ escalation_risk ↓
```

------------------------------------------------------------------------

## 16. Additional Environment Validation

### Policy Intervention Sensitivity

Meaningfully different strategies should produce meaningfully different
state trajectories.

### Paraphrase Robustness

Semantically equivalent actions should generate similar state updates.

### Persona Sensitivity

Hold Action, History, and State fixed while changing Persona. Resulting
transitions should differ in interpretable ways.

### Human State-Update Validation

On a stratified subset, humans judge decrease / similar / increase for
selected variables.

### Human Trajectory Plausibility

Humans rate:

``` text
State continuity
History sensitivity
Persona consistency
Response-state consistency
Overall trajectory plausibility
```

------------------------------------------------------------------------

## 17. Offline Task Construction from Complete Rollouts

Complete model rollouts are directly used to generate offline instances.

``` text
Complete Trajectory
        ├── checkpoints → T1
        ├── cross-trajectory aligned cases → T2
        └── checkpoints + candidate actions → T3
```

No dramatic sampling step is required.

The offline builder preserves observable history, turn IDs, target
character, checkpoint, and candidate actions when applicable, while
withholding hidden state, hidden intention, appraisal, state delta, and
future trajectory unless explicitly required.

------------------------------------------------------------------------

## 18. Task 1 --- Latent Social State Estimation

### Input

``` text
Target Character
+
Complete Observable History
+
Current Checkpoint
```

### Output

For each target state variable:

``` text
State Intensity
+
State Change Direction
+
Evidence Turn IDs
```

Example:

``` json
{
  "state_predictions": [
    {
      "state_id": "trust",
      "predicted_intensity": "low",
      "predicted_change": "decrease",
      "evidence_turn_ids": ["t3", "t5"]
    }
  ]
}
```

Candidate metrics:

``` text
Intensity Accuracy
Transition Accuracy
Evidence F1
Calibration / Brier Score
```

Formal GT requires validated annotation rather than treating simulator
internals as unquestioned truth.

------------------------------------------------------------------------

## 19. Task 2 --- History-Conditioned State Comparison

### Goal

Test whether the model understands that the **same current observation**
can correspond to different latent states because of different
histories.

### Input

``` text
Target Character
+ Shared Prehistory
+ History A
+ History B
+ Exactly the Same Current Observation O*
```

Core condition:

``` text
Shared Prehistory aligned
History A != History B
Observation A == Observation B == O*
```

### Construction

Free rollouts do not need to naturally end with identical utterances.

Preferred strategy:

``` text
Complete Rollout A ─┐
                    ├→ retrieve compatible divergent histories
Complete Rollout B ─┘
                    ↓
       construct/select shared observation O*
                    ↓
     compatibility check under both histories
                    ↓
       inject exactly the same O* into A and B
                    ↓
             GT / human validation
```

**B: semantic matching** may be used for candidate retrieval.\
**C: controlled current-observation injection** is used for the final
controlled instance.

Thus:

``` text
B for candidate retrieval
+
C for final controlled construction
```

For the MVP, C can be used directly.

The injected observation must be contextually plausible under both
histories.

### Output

``` text
State Difference Direction
+ Evidence Nodes from History A
+ Evidence Nodes from History B
+ Key Causal Choice / Action
```

Direction labels:

``` text
higher_in_A
similar
higher_in_B
cannot_determine
```

T2 isolates:

\[ Same Current Observation + Different History
`\rightarrow`{=tex}Different Latent State \]

------------------------------------------------------------------------

## 20. Task 3 --- Counterfactual State Transition Prediction

### Goal

Evaluate whether a model can predict how alternative actions would
change a target character's latent social state over both immediate and
delayed horizons.

### Main Input

``` text
Target Character
+
Complete Observable History
+
Current Checkpoint
+
2–4 Candidate Actions
```

The main task **does not expose the exact current latent state**. The
model must infer the current social situation from observable history
before predicting consequences.

### Oracle-State Ablation

A separate ablation additionally provides the current latent state:

``` text
History + Current Observation + Oracle Current State + Candidate Actions
```

This separates:

``` text
State-Inference Difficulty
from
Consequence-Prediction Difficulty
```

### Output

For every candidate action and every selected target state variable:

``` text
Immediate Effect
+
Delayed Effect
```

Effects use the same seven-level semantic scale:

``` text
strong_decrease
moderate_decrease
mild_decrease
similar
mild_increase
moderate_increase
strong_increase
```

### Immediate Effect

\[ Immediate(A_t)=S\_{t+1}-S_t \]

### Delayed Effect

The default v1 delayed horizon is **5 interaction turns after the
candidate action**:

\[ Delayed_5(A_t)=S\_{t+5}-S_t \]

For scenarios where a longer horizon is necessary, the configured
delayed horizon may extend to at most **10 interaction turns**:

\[ 5 `\leq `{=tex}k `\leq 10`{=tex} \]

The horizon used by each instance must be explicitly recorded.

All candidate actions branch from exactly the same checkpoint and use
the **same continuation protocol**, so differences are attributable to
the candidate action rather than different downstream policies.

Candidate metrics:

``` text
Immediate Effect Accuracy
Delayed Effect Accuracy
Calibration / Brier Score
```

------------------------------------------------------------------------

## 21. Task 4 --- Online Stateful Interaction

T4 has no unique correct action trajectory.

Evaluated model sees:

``` text
Scenario
Role
Explicit Goal
Observable History
Current Environment Response
Observable Cues
```

It does not see hidden state, hidden intention, appraisal, or transition
rules.

Current dimensions:

``` text
Goal Achievement
State Adaptation
Risk Management
Recovery
Relationship Outcome
```

Primary reporting should remain multidimensional.

------------------------------------------------------------------------

## 22. Ground Truth

Formal GT follows a two-level human-validation strategy.

### Environment Validation

Humans do **not** annotate every environment transition.

Instead, a stratified subset of state transitions and complete
trajectories is human-validated to estimate environment credibility.

### Formal Offline Benchmark GT

All T1/T2/T3 instances that enter the formal benchmark should receive
human annotation and, when needed, adjudication.

``` text
Complete Rollout
↓
Environment Candidate State / Effect
↓
T1 / T2 / T3 Instance Construction
↓
Human Annotation
↓
Agreement Check
↓
Adjudication for Disagreement / Ambiguity
↓
Formal Benchmark GT
```

Independent LLM judges may assist with candidate filtering, quality
control, or disagreement analysis, but simulator internals are not
automatically treated as formal truth.

Thus:

``` text
Environment transitions
→ human subset validation

Published offline benchmark instances
→ formal human annotation / adjudication
```

------------------------------------------------------------------------

## 23. Environment Validity vs Benchmark Performance

Environment validity asks:

``` text
Does the environment produce credible state dynamics?
```

Benchmark evaluation asks:

``` text
Can the evaluated model understand, predict, and adapt to those dynamics?
```

Report separately.

------------------------------------------------------------------------

## 24. Suggested Repository Structure

``` text
emotree/
├── configs/
│   ├── scenarios/
│   │   ├── scenario_001.json      # canonical machine definition
│   │   ├── scenario_001.md        # generated natural-language pair
│   │   └── manifest.json          # generated JSON/Markdown catalog
│   ├── ontology/
│   └── policies/
├── providers/
│   ├── base.py
│   ├── openai_compatible.py
│   ├── anthropic.py
│   ├── gemini.py
│   └── local_vllm.py
├── environment/
│   ├── initializer.py
│   ├── memory.py
│   ├── state_updater.py
│   ├── delta_mapper.py
│   ├── response_generator.py
│   ├── termination.py
│   └── env.py
├── policies/
│   ├── model_policy.py
│   └── controlled/
├── rollout/
│   ├── runner.py
│   ├── batch_runner.py
│   └── logger.py
├── offline/
│   ├── task1_builder.py
│   ├── task2_builder.py
│   └── task3_builder.py
├── annotation/
│   ├── llm_judges.py
│   ├── human_export.py
│   └── adjudication.py
├── scripts/
│   └── scenario_docs.py           # generate/check scenario Markdown + manifest
├── web/                            # read-only scenario/pipeline observatory
├── evaluation/
│   ├── task1.py
│   ├── task2.py
│   ├── task3.py
│   ├── task4.py
│   └── environment_validity.py
└── schemas/
    ├── scenario.schema.json
    ├── ontology.schema.json
    ├── trajectory.schema.json
    ├── task1.schema.json
    ├── task2.schema.json
    └── task3.schema.json
```

------------------------------------------------------------------------

## 25. Development MVP and Version-1 Benchmark Scope

EmoTree distinguishes between an **engineering MVP** and the **first
complete benchmark version**.

### Engineering MVP

Use one scenario first to debug the complete pipeline:

``` text
1 Scenario
+
1 Environment Agent
+
Frozen S0 / D0
+
Scenario-specific State Subset
+
Several Model API Policies
+
Controlled Validation Policies
+
T1 / T2 / T3 Builders
+
T4 Evaluation Interface
```

The single-scenario MVP is only a pipeline and environment acceptance
gate.

### Version-1 Benchmark

The first complete benchmark should contain **10 fully constructed
scenarios with different social themes**.

``` text
10 Distinct Social Scenarios
        ↓
For Every Scenario:
├── Canonical Scenario JSON
├── Source-Hash-Verified Natural-Language Markdown Pair
├── Persona / Background
├── Explicit Goal / Hidden Intention
├── Selected State Variables
├── Frozen S0 / D0
├── Model API Rollouts
├── Environment Validation
├── T1 Instances
├── T2 Instances
├── T3 Instances
└── T4 Online Configuration / Evaluation
```

The 10 scenarios should differ meaningfully in social relationship,
conflict structure, goals, and relevant latent-state variables rather
than being superficial rewrites of one template.

Candidate theme families may include:

``` text
academic / advisor-student
friendship
romantic relationship
family
workplace / manager-employee
peer collaboration
stranger / public interaction
service / negotiation
trust or disclosure conflict
resource / responsibility conflict
```

The exact ten scenarios remain a content-design task, but **10 complete
and task-paired scenarios are a fixed v1 scope requirement**.

------------------------------------------------------------------------

## 26. Immediate Implementation Order

### Phase A --- Single-Scenario Engineering Gate

``` text
1. Freeze global legal ontology.
2. Define scenario schema.
3. Define the canonical JSON + generated same-name Markdown + manifest contract.
4. Define trajectory schema.
5. Implement model-provider abstraction.
6. Implement candidate S0/D0 generation + review + freeze.
7. Implement memory module.
8. Implement appraisal + state update prompt.
9. Implement seven-level delta mapper.
10. Implement interaction dynamics update.
11. Implement response generation.
12. Implement online rollout runner.
13. Implement complete trajectory logging.
14. Connect several model APIs.
15. Implement controlled validation policies.
16. Run environment validation.
17. Implement T1 builder.
18. Implement T2 builder.
19. Implement T3 builder with 5-turn delayed horizon.
20. Implement T4 interface.
21. Export candidate instances for human annotation.
22. Add evaluation scripts and leakage checks.
```

### Phase B --- Version-1 Ten-Scenario Construction

After the first scenario passes the engineering gate:

``` text
23. Design 9 additional distinct scenarios.
24. Select scenario-specific ontology subsets.
25. Generate/review/freeze S0/D0 for every scenario.
26. Generate and review the source-hash-verified paired Markdown for every scenario.
27. Run model API rollouts for all 10 scenarios.
28. Run environment validation for all 10 scenarios.
29. Build T1/T2/T3 instances for every scenario.
30. Configure T4 for every scenario.
31. Perform formal human annotation for published T1/T2/T3 instances.
32. Adjudicate disagreements and remove ambiguous cases.
33. Run baselines and ablations across all 10 scenarios.
34. Produce per-scenario and aggregate benchmark statistics.
```

------------------------------------------------------------------------

## 27. Current Fixed Decisions

``` text
Complete rollouts directly feed T1/T2/T3.

Dramatic / exaggerated policies are used for environment validation,
not as a required offline-data construction mechanism.

Main rollout policies connect directly to model APIs/endpoints.

Latent State:
Emotion + Behavioral Disposition + Relationship.

Risk-like variables:
separate Interaction Dynamics.

Appraisal:
internal transition-reasoning layer.

Global legal ontology:
defined once; each scenario selects a relevant subset.

State update:
seven-level semantic delta mapping.

Response generation:
state and dynamics are updated before environment response.

Initialization:
candidate S0/D0 → review → freeze;
all policies on a scenario share the same S0/D0.

Scenario documentation:
canonical JSON is the sole source of truth;
same-basename Markdown and manifest are generated and source-hash checked.

T2:
semantic matching may retrieve candidates;
final instances use controlled identical current-observation injection.

T3:
main setting hides current latent state;
Oracle-State is an ablation.

T3 delayed horizon:
default 5 interaction turns;
may extend to at most 10 when explicitly configured;
all candidate branches use the same continuation protocol.

Ground truth:
environment transitions receive human subset validation;
formal published T1/T2/T3 instances receive human annotation/adjudication.

Version-1 scope:
10 distinct fully constructed scenarios,
each paired with rollout + T1 + T2 + T3 + T4 configuration/evaluation.
```

------------------------------------------------------------------------

## 28. Current Open Questions

``` text
Exact global ontology variable list

Exact 10 scenario themes and scenario specifications

Exact number of rollouts per policy per scenario

Exact T1 intensity discretization

Whether all T3 instances use k=5 or a small subset uses scenario-specific k in [5,10]

Exact continuation policy/protocol for T3 delayed effects

Exact human annotation protocol and number of annotators

Exact independent-judge quality-control protocol

Exact T4 scoring rubric and whether any aggregate score is reported

Memory strategy:
full-history / retrieval / structured summary

Episode termination conditions

Exact per-scenario T1/T2/T3 instance counts

Future multimodal text-video paired variants
```

------------------------------------------------------------------------

## 29. One-Sentence Summary

``` text
EmoTree builds ten distinct stateful social scenarios with explicit latent-state transitions, connects model APIs to generate complete interaction trajectories, directly extracts paired T1/T2/T3 diagnostic instances from those rollouts, uses controlled dramatic interventions to validate each environment, and evaluates free online interaction through T4.
```

------------------------------------------------------------------------

## 30. T3 Delayed-Effect Operationalization

Immediate effect is the transition directly after candidate action
(A_t):

\[ Immediate(A_t)=S\_{t+1}-S_t \]

The default delayed horizon for v1 is:

\[ Delayed_5(A_t)=S\_{t+5}-S_t \]

That is, the system evaluates the target state after five subsequent
interaction turns.

If a scenario requires a longer consequence window, the horizon may be
extended, but never beyond ten interaction turns:

\[ 5 `\leq `{=tex}k `\leq 10`{=tex} \]

Every T3 instance records its horizon (k).

All candidate actions branch from the same checkpoint:

``` text
Checkpoint
├── Candidate A → same continuation protocol → state at t+k
├── Candidate B → same continuation protocol → state at t+k
└── Candidate C → same continuation protocol → state at t+k
```

The continuation protocol must be held constant across candidate
branches. Otherwise the measured delayed difference would mix
candidate-action effects with continuation-policy effects.

For v1, **k=5 should be the default**, while k up to 10 is reserved for
scenarios where delayed social consequences genuinely require a longer
interaction window.

------------------------------------------------------------------------

## 31. T4 Scoring Framework

T4 has no unique correct action sequence. Evaluate:

``` text
Goal Achievement
State Adaptation
Risk Management
Recovery
Relationship Outcome
```

-   **Goal Achievement:** extent the explicit scenario goal is achieved.
-   **State Adaptation:** whether strategy changes appropriately as
    observable interaction cues change.
-   **Risk Management:** whether escalation/breakdown risks are managed
    appropriately relative to the goal.
-   **Recovery:** whether the model detects and repairs deterioration it
    encounters or causes.
-   **Relationship Outcome:** final interpersonal change relative to the
    initial relationship.

Primary reporting should remain a multidimensional profile; do not
prematurely collapse everything into one scalar.

------------------------------------------------------------------------

## 32. Formal Ground-Truth Annotation

Formal GT uses human annotation at the benchmark-instance level.

### Environment

Do not manually label every transition.

Use human validation on a stratified subset:

``` text
Environment-generated transitions
↓
Sampled subset
↓
Human directional state judgment
+
Trajectory plausibility judgment
```

### Offline Benchmark

Every T1/T2/T3 instance selected for the published benchmark should
receive formal human annotation.

``` text
Rollout-derived candidate
↓
Task builder
↓
Human annotation
↓
Inter-annotator agreement
↓
Adjudication when necessary
↓
Formal GT
```

Optional independent LLM judges can support filtering and quality
control but do not replace formal human GT.

Core principle:

> Human is the formal benchmark annotator and environment validator, not
> the turn-by-turn environment simulator.

------------------------------------------------------------------------

## 33. Baselines and Ablations

Recommended offline conditions:

``` text
Full History
Recent-k Turns
Current Observation Only
Shuffled History
No Persona
```

T3 additionally compares:

``` text
History + Current Observation
vs.
History + Current Observation + Oracle Current State
```

This separates state-inference difficulty from consequence-prediction
difficulty.

T4 should compare multiple model APIs under the same scenario
initialization and environment configuration.

------------------------------------------------------------------------

## 34. Environment Validation Scorecard

Report environment validity separately from benchmark performance.

``` text
1. Controlled Policy Sensitivity
2. Paraphrase Robustness
3. Persona Sensitivity
4. Human State-Update Agreement
5. Human Trajectory Plausibility
```

A useful environment needs both:

``` text
Sensitivity to meaningful intervention
+
Robustness to superficial variation
```

Dramatic/extreme policies belong specifically to controlled-policy
sensitivity.

------------------------------------------------------------------------

## 35. Engineering Gate and Version-1 Completion Gate

### Gate A --- Single-Scenario Engineering Gate

Before scaling, one scenario must demonstrate that the full system works
end-to-end.

``` text
Environment
- controlled policies create expected directional divergence
- paraphrases yield similar transitions
- persona interventions have interpretable effects
- state-conditioned responses differ when states differ
- human subset finds transitions/trajectories plausible

Rollout
- multiple model APIs work through one policy interface
- all policies share frozen S0 / D0
- complete trajectories are reproducibly logged

Offline
- T1 is extracted from ordinary checkpoints
- T2 constructs same-observation/different-history pairs
- T3 branches candidate actions and evaluates delayed effects
- instances export cleanly for human annotation

Evaluation
- schemas and metrics run end-to-end
- hidden-state leakage checks pass

Scenario Documentation
- canonical JSON has a same-basename generated Markdown
- Markdown explains initialization, state/action semantics, and video thresholds
- source hash and scenario manifest checks pass
```

### Gate B --- Version-1 Benchmark Completion

The first benchmark version is not complete until all **10 distinct
scenarios** have the full paired stack:

``` text
Canonical Scenario JSON
+
Source-Hash-Verified Natural-Language Scenario Document
+
Validated Environment
+
Model API Rollouts
+
T1
+
T2
+
T3
+
T4 Configuration/Evaluation
+
Formal GT for published offline instances
```

Final v1 reporting should include:

``` text
per-scenario statistics
cross-scenario aggregate statistics
environment-validity results
T1/T2/T3 baseline results
T4 online results
history/persona/oracle-state ablations
human annotation agreement
```

The one-scenario gate is for engineering stability; the ten-scenario
stack is the actual v1 benchmark target.
