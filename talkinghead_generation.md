# Multimodal Observation Generation and State-Triggered Media

## 1. Motivation

In the multimodal version of the environment, video should not be attached to interaction nodes arbitrarily.

Instead, multimodal observations should be generated as an observable consequence of the evolving latent social state.

The core principle is:

```text
Latent Social State
        ↓
State Transition
        ↓
Observable Expression
        ↓
Text / Facial Expression / Voice / Video
        ↓
Evaluated Agent
```

Therefore, multimodal content is treated as part of the environment's **observation-generation mechanism**, rather than as an independent annotation attached to a dialogue turn.

Formally:

$$
O_t = g(S_t, D_t, C_t, M_t)
$$

where:

* \(S_t\): current Latent Social State;
* \(D_t\): current Interaction Dynamics;
* \(C_t\): current dialogue and interaction context;
* \(M_t\): modality-generation rules;
* \(O_t\): observable multimodal output presented to the evaluated agent.

The evaluated agent never directly observes \(S_t\) or \(D_t\). It only observes their externally expressed consequences.

---

## 2. Position in the Environment Pipeline

The multimodal observation module is executed **after state and interaction-dynamics updates**.

```text
Evaluated Agent Action
        ↓
Appraisal
        ↓
Latent State Update
        ↓
Interaction Dynamics Update
        ↓
State-Triggered Modality Check
        ↓
Environment Response Generation
        ↓
Observable Expression Generation
        ↓
Text Observation
        +
Optional Video / Audio / Facial Cues
        ↓
Evaluated Agent
```

This preserves the causal direction:

$$
Action
\rightarrow
Appraisal
\rightarrow
State
\rightarrow
Observable\ Expression
$$

rather than:

$$
Video
\rightarrow
Artificially Assigned State
$$

---

## 3. Observable Expression Layer

A separate **Observable Expression Layer** maps latent internal states to externally observable behavioral signals.

The distinction is:

```text
Latent State
≠
Observable Expression
```

For example:

```text
Latent:
anger = high
hostility = high

Possible Observable Expressions:
- furrowed brows
- sharper tone of voice
- faster speech
- shorter responses
- reduced eye contact
- tense facial expression
```

Similarly:

```text
Latent:
sadness = high
willingness_to_withdraw = high

Possible Observable Expressions:
- lowered gaze
- longer pauses
- quieter voice
- reduced facial movement
- hesitant response
```

The observable expression is therefore a **noisy and partial projection** of the latent state:

$$
X_t \sim p(X_t\mid S_t,D_t,Persona,Context)
$$

where \(X_t\) represents observable facial, vocal, and behavioral cues.

This distinction is important because the benchmark should require models to **infer** social states from observable evidence rather than directly exposing state labels.

---

## 4. State-Triggered Media

Multimodal observations are activated by predefined **state-trigger rules**.

Each scenario may define a set of trigger conditions over its selected state variables.

Example:

```yaml
video_triggers:

  - trigger_id: anger_escalation

    conditions:
      anger:
        operator: ">="
        threshold: 8

      hostility:
        operator: ">="
        threshold: 7

    trigger_mode: crossing

    media_type: video

    cue_template: angry_confrontational
```

The corresponding rule is:

$$
anger_t \geq 8
\land
hostility_t \geq 7
\Rightarrow
Trigger_{anger}(t)=1
$$

When activated, the environment produces an observation containing multimodal cues consistent with the triggered state.

---

## 5. Trigger Types

The framework supports several trigger mechanisms.

### 5.1 Threshold Trigger

A media event is triggered whenever a state variable reaches a specified region.

Example:

$$
anger_t \geq 8
$$

```yaml
trigger_mode: threshold
```

This is useful when a particular expression should remain available while the state remains intense.

---

### 5.2 Threshold-Crossing Trigger

A media event is triggered only when the state crosses a threshold.

$$
anger_{t-1}<8
\quad\land\quad
anger_t\geq8
$$

```yaml
trigger_mode: crossing
```

This should be the preferred mechanism for salient video events.

It prevents repeated triggering when a state remains above the threshold for several consecutive turns.

---

### 5.3 Multi-State Trigger

Triggers may depend on combinations of variables.

For example:

$$
anger_t\geq8
\land
hostility_t\geq7
\land
escalation\_risk_t\geq8
$$

may trigger an explicit confrontation cue.

Another example:

$$
sadness_t\geq7
\land
willingness\_to\_withdraw_t\geq8
$$

may trigger an avoidant or emotionally withdrawn expression.

---

### 5.4 State-Change Trigger

Some expressions may be caused by rapid state change rather than absolute intensity.

For example:

$$
\Delta anger_t \geq 2
$$

may trigger a visible moment of surprise or irritation even when the absolute anger level remains moderate.

This allows the environment to represent sudden emotional reactions.

---

## 6. Cooldown and Repeated Trigger Control

A state may remain above a threshold for several turns.

Therefore, every salient media trigger should support a cooldown mechanism.

Example:

```yaml
trigger_id: anger_escalation
trigger_mode: crossing
cooldown_turns: 3
```

After activation at turn \(t\), the same trigger cannot activate again until:

$$
t' \geq t+3
$$

This prevents trajectories such as:

```text
Turn 5 → angry video
Turn 6 → angry video
Turn 7 → angry video
Turn 8 → angry video
```

when the underlying state has not meaningfully changed.

Repeated activation should correspond to a meaningful new state transition rather than persistent high intensity alone.

---

## 7. Scenario-Specific Trigger Configuration

The global state ontology is shared across the benchmark, but multimodal triggers are **scenario-specific**.

Each scenario defines:

```text
Selected State Variables
+
Relevant Observable Expressions
+
Trigger Conditions
+
Available Media Templates
```

For example, an advisor–student authorship conflict may emphasize:

```text
anger
trust
respect
hostility
willingness_to_negotiate
escalation_risk
```

while a friendship-disclosure scenario may emphasize:

```text
sadness
disappointment
trust
affection
willingness_to_disclose
willingness_to_withdraw
```

Therefore:

$$
Global\ State\ Ontology
\rightarrow
Scenario\ State\ Subset
\rightarrow
Scenario\ Trigger\ Rules
$$

### 7.1 Human-Readable Trigger Documentation

Every scenario trigger configuration must also appear in the generated same-name scenario Markdown. For each trigger, the document states the trigger mode, the fact that `conditions` are AND-combined, every variable/operator/threshold, cooldown, media duration, cue template, and resulting observable expression. This is a review surface only: JSON remains canonical, and the Markdown records the source JSON SHA-256 so stale threshold descriptions are rejected before rollout or acceptance.

---

## 8. Media Event Schema

Each triggered multimodal event should be explicitly recorded.

Example:

```json
{
  "media_event_id": "media_t07_001",
  "turn_id": "t07",
  "trigger_id": "anger_escalation",
  "trigger_mode": "crossing",

  "trigger_variables": {
    "anger": 8,
    "hostility": 7,
    "escalation_risk": 8
  },

  "observable_expression": {
    "facial_expression": "tense and visibly irritated",
    "gaze": "reduced eye contact",
    "speech_style": "short and sharp",
    "prosody": "raised intensity"
  },

  "media_type": "video",
  "cue_template": "angry_confrontational",

  "media_asset_id": null
}
```

The `media_asset_id` may remain empty during the text-only development stage and later point to a generated or curated video asset.

---

## 9. Separation Between Trigger State and Benchmark Input

Trigger variables are **author-side environment information**.

For example:

```text
anger = 8
hostility = 7
```

may cause a video to be generated, but these values must not be exposed to the evaluated model.

The evaluated model receives only:

```text
Dialogue
+
Visible Facial Expression
+
Voice / Prosody
+
Other Observable Behavioral Cues
```

Therefore:

```text
Author Side:

S_t
↓
Trigger
↓
Expression
↓
Video
```

while:

```text
Model Side:

Dialogue
+
Video
↓
Infer S_t
```

This prevents hidden-state leakage.

---

## 10. Text and Text-Video Paired Variants

Where possible, benchmark instances should support paired variants:

```text
Text Variant
vs.
Text + Video Variant
```

Both variants should correspond to the same underlying:

```text
Scenario
History
Action
Latent State
State Transition
Target Label
```

The difference is only the observable modality.

Formally:

$$
GT_{text}=GT_{text+video}
$$

while:

$$
Observation_{text}
\neq
Observation_{text+video}
$$

This enables controlled evaluation of whether multimodal social cues improve state inference and downstream reasoning.

---

## 11. Multimodal Information Should Be Complementary

Video should not merely repeat the textual content.

A useful multimodal observation may contain information such as:

```text
Text:
“好，我知道了。”

Video:
- prolonged silence before responding
- lowered gaze
- tense facial expression
- flat prosody
```

The text itself may appear neutral, while the multimodal cues provide evidence about the underlying social state.

This makes multimodal evaluation meaningful:

$$
Textual\ Semantics
+
Nonverbal\ Social\ Signals
\rightarrow
Latent\ State\ Inference
$$

rather than:

$$
Text
+
Redundant\ Visual\ Decoration
$$

---

## 12. Interaction with T1–T4

### T1 — Latent Social State Estimation

Video provides additional observable evidence for inferring:

```text
Emotion
Behavioral Disposition
Relationship State
```

This directly supports controlled comparison:

```text
T1-Text
vs.
T1-TextVideo
```

---

### T2 — History-Conditioned State Comparison

Multimodal cues must be handled carefully because T2 requires:

$$
Same\ Current\ Observation
+
Different\ History
$$

Therefore, paired T2 histories must receive the **same current multimodal observation**, including the same video where applicable.

Otherwise the current video itself may leak the target state difference.

For T2:

```text
History A + O*
History B + O*
```

must satisfy:

$$
O_A^*=O_B^*
$$

across both text and media.

---

### T3 — Counterfactual State Transition Prediction

Candidate actions may trigger different future observable expressions because they produce different state trajectories.

For example:

```text
Candidate A
↓
hostility crosses threshold
↓
confrontational video event

Candidate B
↓
hostility remains moderate
↓
no video event
```

These media events belong to the **counterfactual continuation trajectory** and may be used for delayed-effect construction and analysis.

They must not be exposed when they would reveal the answer before the model makes its T3 prediction.

---

### T4 — Online Stateful Interaction

T4 is the most natural setting for state-triggered multimodal observations.

During online interaction:

```text
Model Action
↓
Environment State Update
↓
Trigger Evaluation
↓
Text / Multimodal Response
↓
Model observes response
↓
Next Action
```

The evaluated agent must adapt not only to what the Environment Agent says, but also to observable changes in facial expression, voice, and other behavioral signals.

This extends online adaptation from:

$$
Text\rightarrow Action
$$

to:

$$
Multimodal\ Social\ Observation
\rightarrow Action
$$

---

## 13. Trajectory Logging Extension

The master trajectory should record multimodal information without exposing trigger internals in public model input.

Example:

```json
{
  "turn_id": "t07",

  "state_before": {},
  "state_delta": {},
  "state_after": {},

  "dynamics_before": {},
  "dynamics_delta": {},
  "dynamics_after": {},

  "trigger_events": [
    {
      "trigger_id": "anger_escalation",
      "trigger_mode": "crossing"
    }
  ],

  "observable_expression": {
    "facial_expression": "...",
    "prosody": "...",
    "behavioral_cues": []
  },

  "environment_text_response": "...",
  "media_asset_id": "video_007"
}
```

The master trajectory preserves both:

```text
Hidden causal variables
+
Observable multimodal realization
```

Offline task builders determine which fields are exposed for each task.

---

## 14. Multimodal Generation Pipeline

The eventual video-generation pipeline can be separated from the core environment:

```text
Updated Latent State
        ↓
Trigger Engine
        ↓
Observable Expression Specification
        ↓
Text Response
        +
Expression / Prosody Specification
        ↓
Talking-Head / Video Generation
        ↓
Media Asset
        ↓
Trajectory Attachment
```

This separation is important because the environment should remain executable even before video generation is implemented.

Therefore, development can proceed in stages:

```text
Stage 1
State → Text Response

Stage 2
State → Structured Observable Expression

Stage 3
State → Structured Expression → Generated Video

Stage 4
Paired Text / Text-Video Benchmark
```

The stateful environment should therefore be implemented independently from any particular talking-head model.

---

## 15. Validation of State-Triggered Media

Multimodal generation requires its own validation.

At minimum, evaluate:

### Trigger Validity

Does the media event occur when the intended state condition is reached?

### Expression-State Consistency

Are generated facial/vocal cues compatible with the underlying state?

### Persona Consistency

Does the same latent state manifest differently for different personas where appropriate?

### Temporal Continuity

Do expressions evolve smoothly across adjacent turns rather than changing arbitrarily?

### Non-Leakage

Does the media provide natural social evidence without trivially encoding the benchmark label?

### Human Plausibility

Do human raters judge the resulting multimodal trajectory as a plausible manifestation of the character's evolving internal state?

---

## 16. Core Design Principle

The multimodal extension should preserve the following causal structure:

$$
\boxed{
Interaction
\rightarrow
Appraisal
\rightarrow
Latent\ Social\ State
\rightarrow
Observable\ Expression
\rightarrow
Multimodal\ Observation
}
$$

Video is therefore **not an independent decoration layer**.

It is an observable manifestation of the stateful environment.

The key distinction is:

> **The latent state determines when and how multimodal social signals emerge; the evaluated model must infer the underlying state from those signals rather than being given the state directly.**
