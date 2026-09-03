# SocialFlux Scenario and Rollout Architecture — Important Revision

Please revise the previous SocialFlux construction refactor according to the following two decisions.

These decisions override any conflicting design in the previous instructions or existing repository.

---

# 1. Do Not Use Predefined Strategies to Generate Offline Data

SocialFlux should NOT generate its offline benchmark data from predefined:

* repair policies;
* neutral/assertive policies;
* escalation policies;
* scripted strategy classes;
* predefined action trajectories.

Remove these concepts from the normal data-generation pipeline.

The central design should instead be:

```text
Scenario
        ↓
State Configuration
        ↓
Stateful Interactive Environment
        ↓
Free-form Model Interaction
        ↓
Naturally Evolved Trajectories
        ↓
Trajectory Pool
       /      |      \
     T1      T2      T3
```

The offline benchmark must therefore be derived from trajectories that arise from the **same open-ended online interaction framework** used by SocialFlux.

This is a core design principle:

> **Offline SocialFlux evaluates diagnostic slices of naturally evolved online interactions rather than trajectories generated from predefined behavioral strategies.**

---

# 2. Offline and Online Must Share the Same Environment

Do not implement one environment for offline data generation and another for T4.

There should be one canonical stateful environment:

```text
                    SocialFlux Environment
                           │
              ┌────────────┴────────────┐
              │                         │
      Rollout Generation          Online Evaluation
              │                         │
              ▼                         ▼
       Trajectory Pool                  T4
        /      |      \
      T1      T2      T3
```

For offline construction:

```text
Model Policy
↕
Stateful Environment
```

interacts freely and generates complete trajectories.

For online T4:

```text
Evaluated Model
↕
The Same Stateful Environment
```

interacts freely.

The difference is what happens **after interaction**, not how the world itself operates.

---

# 3. Free-Form Rollout Generation

Rollout agents should use normal model APIs and generate arbitrary natural-language actions.

The environment must accept:

```text
arbitrary free-form action
```

rather than:

```text
repair
neutral
escalation
```

or any other predefined action category.

The transition remains:

```text
Free-form Action
        ↓
Persona-Conditioned Appraisal
        ↓
Latent State Delta
        ↓
State Update
        ↓
Interaction Dynamics Update
        ↓
Observable Environment Response
        ↓
Next Free-form Action
```

No action taxonomy should determine state transitions.

---

# 4. Generate Behavioral Diversity Through Models and Sampling, Not Strategy Labels

The trajectory pool still needs diversity.

Achieve this through factors such as:

```text
different model families
different model capabilities
different temperatures
different random seeds
different interaction histories
different naturally emerging decisions
```

rather than predefined strategy labels.

For example:

```text
Scenario S01
Frozen S0 / D0

├── Model A, seed 1 → trajectory τ1
├── Model A, seed 2 → trajectory τ2
├── Model B, seed 1 → trajectory τ3
├── Model C, seed 1 → trajectory τ4
├── Model D, seed 3 → trajectory τ5
└── ...
```

These trajectories may naturally contain:

* repair attempts;
* escalation;
* compromise;
* avoidance;
* disclosure;
* boundary setting;
* strategic concession;
* failed repair;
* repeated confrontation;
* withdrawal.

But these behaviors should **emerge from interaction** rather than being prescribed before rollout.

---

# 5. Validation Should Also Prefer Natural Trajectory Interventions

Remove the assumption that Environment Validation fundamentally requires three fixed controlled policies.

Environment validation should instead use a combination of:

### Natural trajectory analysis

Compare naturally generated trajectories that diverge behaviorally.

### Local controlled interventions

When causal validation is needed, intervene at a specific shared checkpoint:

```text
Same Scenario
+
Same History
+
Same S_t / D_t
+
Different Controlled Action
```

and compare the resulting transition.

This is a **local intervention experiment**, not a predefined multi-turn strategy.

For example:

```text
Shared checkpoint
        │
        ├── Action A
        ├── Action B
        └── Action C
             ↓
Compare ΔS / ΔD
```

The actions may be selected to differ in socially meaningful ways, but the environment must independently infer their effects.

Do not pre-write expected numeric state transitions into the simulator.

This preserves causal validation without turning SocialFlux into a three-policy state machine.

---

# 6. Revised Environment Validation

Environment validation should include:

```text
State-Update Human Agreement
Persona Sensitivity
Paraphrase Robustness
History Intervention
Local Action Intervention
Neutral-State Stability
Response-State Consistency
Full-Trajectory Plausibility
Seed Robustness
```

For Local Action Intervention:

1. select a real checkpoint from a free-form trajectory;
2. keep history, state, dynamics, and environment character fixed;
3. introduce several plausible alternative actions;
4. independently run the environment transition for each;
5. compare resulting state/dynamics;
6. validate qualitative differences with humans where needed.

This intervention is an experiment performed **on top of the free-form environment**, not part of scenario definition or normal rollout generation.

---

# 7. Hybrid Scenario Sources

SocialFlux scenarios should come from at least two complementary sources:

```text
A. Narrative-Derived Scenarios
B. Synthetic Script-Generated Scenarios
```

Both sources must ultimately be normalized into the same canonical SocialFlux scenario representation.

---

# 8. Source A — Narrative-Derived Scenarios

Some scenarios may be inspired by social interactions found in:

```text
films
television series
plays
novels
other narrative works
```

The purpose is to obtain richer interpersonal structures containing:

```text
long interaction history
relationship development
conflicting goals
information asymmetry
power asymmetry
failed repair
betrayal
reciprocity
status dynamics
subtle interpersonal tension
```

Do NOT simply copy dialogue or copyrighted scenes into the released benchmark.

The source material should be used as a **scenario-structure source**.

The construction pipeline should extract an abstract social structure such as:

```text
relationship structure
social mechanism
relevant historical events
goal conflict
private incentives
information asymmetry
decision structure
possible social turning points
```

and then transform it into an original SocialFlux scenario.

The released scenario should use newly written:

```text
characters
setting
background description
dialogue
surface details
```

unless the source is explicitly licensed for redistribution.

Maintain provenance metadata internally when appropriate.

---

# 9. Source B — Synthetic Script-Generated Scenarios

Other scenarios should be created through a dedicated script-generation process.

Do NOT ask the model directly:

> Generate one benchmark scenario JSON.

Instead use:

```text
Social Mechanism
+
Relationship Structure
+
Power Structure
+
Goal Conflict
+
Information Asymmetry
+
Desired History Dependency
        ↓
Generate Narrative Script
```

The generated script should first resemble a coherent social narrative rather than a benchmark configuration file.

It should establish:

```text
who the characters are
how they know each other
what happened previously
what each person wants
what each person knows
what remains private
why the current conflict exists
what unresolved history matters
what meaningful choices may arise
```

Only after the script passes a quality gate should it be normalized into the canonical SocialFlux scenario schema.

---

# 10. Separate Script Generation from Scenario Normalization

For synthetic scenarios, use:

```text
Coverage Requirement
        ↓
Script Generation
        ↓
Narrative Quality Check
        ↓
SocialFlux Scenario Extraction / Normalization
        ↓
Scenario Quality Gate
```

Do not force the script-generation model to think simultaneously about:

```text
JSON schema
state variables
S0
D0
video thresholds
T1 sampling
T2 construction
T3 horizons
```

The script-generation stage should focus on social and narrative quality.

A later normalization stage converts the approved narrative into structured SocialFlux fields.

---

# 11. Unified Scenario Normalization

Regardless of source:

```text
Film / TV / Narrative Structure
             ↓
      Scenario Extraction
             │
             ▼
      Canonical Scenario

Synthetic Generated Script
             ↓
      Scenario Extraction
             │
             ▼
      Canonical Scenario
```

After normalization, downstream components should not need to know whether the scenario originated from a narrative work or synthetic generation.

Both sources must pass the same quality gate.

---

# 12. Scenario Quality Gate

Every candidate scenario must be checked for:

```text
Social Plausibility
Real Trade-off
Longitudinal Necessity
Nontrivial Strategy Space
Character Motivation Coherence
Information Asymmetry
T1 Suitability
T2 Suitability
T3 Suitability
T4 Adaptation Opportunity
No Single Universally Optimal Scripted Response
```

Reject or revise scenarios that fail these requirements.

---

# 13. Scenario Diversity Should Be Designed Before Story Generation

Before generating the 10 formal scenarios, create a coverage matrix across dimensions such as:

```text
Relationship Type
Social Mechanism
Power Asymmetry
Goal Conflict
Information Asymmetry
Temporal History Pattern
Relevant State Families
Repair Possibility
Failure Mode
Scenario Source
```

The `Scenario Source` dimension should distinguish at least:

```text
narrative-derived
synthetic-script
```

Do not make all 10 scenarios synthetic.

Do not make all 10 scenarios adaptations of existing narratives.

The two sources should complement each other.

---

# 14. Offline Dataset Construction Must Be Rollout-Derived

After a scenario is normalized and configured:

```text
Scenario
↓
State Configuration
↓
Freeze S0 / D0
↓
Stateful Environment
↓
Multiple Free-form Model Rollouts
↓
Trajectory Pool
```

Only then construct offline tasks.

---

# 15. T1 Must Be Trajectory-Derived

Find real checkpoints in naturally evolved trajectories where:

```text
history matters
+
state is nontrivial
+
observable evidence exists
+
current utterance does not trivially reveal the answer
```

Use these as candidate T1 instances.

Do not pre-script T1 checkpoints during scenario generation.

---

# 16. T2 Must Be Constructed from Naturally Divergent Histories

Use naturally generated trajectory histories as the primary source.

Pipeline:

```text
Free-form Trajectory Pool
        ↓
Find Semantically Compatible Divergent Histories
        ↓
Select Candidate History A / History B
        ↓
Construct Exact Shared Current Observation O*
        ↓
Compatibility Check
        ↓
Inject O* into Both Histories
        ↓
Human Validation
        ↓
T2 Instance
```

The histories should therefore originate from free interaction even though the final identical observation is a controlled benchmark construction.

---

# 17. T3 Should Branch from Real Free-Form Checkpoints

Select meaningful checkpoints from naturally generated trajectories.

Then:

```text
Real Trajectory Checkpoint
        ↓
Generate / Select Plausible Alternative Actions
        ↓
Counterfactual Branch Rollouts
        ↓
Immediate Effect
+
Delayed Effect
```

The initial checkpoint is naturally evolved.

The counterfactual alternatives are local interventions used to measure consequence reasoning.

They are not predefined global strategies.

---

# 18. T4 Remains Fully Online

T4 directly evaluates:

```text
Evaluated Model
↕
Same Stateful SocialFlux Environment
```

The model receives only observable information and freely chooses each next action.

No predefined strategy class is used.

---

# 19. Revised Unified Pipeline

The repository should ultimately represent:

```text
              Scenario Source Pool
              /                 \
     Narrative Works       Synthetic Scripts
             │                   │
      Structure Extraction       │
             │                   │
             └─────────┬─────────┘
                       ▼
              Scenario Normalization
                       ↓
               Scenario Quality Gate
                       ↓
                   Human Review
                       ↓
               State Configuration
                       ↓
             Candidate S0 / D0
                       ↓
              Human Review + Freeze
                       ↓
              Stateful Environment
                       ↓
              Free-form Rollouts
                       ↓
                 Trajectory Pool
               /        |        \
             T1        T2        T3

                       +

              Evaluated Model
                     ↕
              Same Environment
                     ↓
                    T4
```

Validation runs alongside this pipeline through sampled human validation and local controlled interventions.

---

# 20. Updated Conceptual Invariants

Use these as architecture-level invariants:

> **A scenario defines the social world; it does not define a strategy for navigating it.**

> **A trajectory should emerge from free interaction rather than from a predefined repair/escalation policy.**

> **Offline benchmark instances should be diagnostic slices or controlled local branches of trajectories produced by the same stateful environment used for online evaluation.**

> **Narrative-derived and synthetic-script scenarios should share one normalized downstream representation and one evaluation pipeline.**

> **Controlled intervention is an experimental tool, not a rollout policy.**

Please update any previous implementation or documentation that conflicts with these principles.
