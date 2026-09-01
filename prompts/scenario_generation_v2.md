# SocialFlux Stateful Scenario Generation Prompt v2

You are designing one canonical scenario for **SocialFlux**, a benchmark for longitudinal social-state reasoning in stateful interactive environments.

Your goal is **not merely to populate a JSON schema**. Your primary task is to design a socially plausible interactive situation in which understanding interaction history, latent social-state evolution, action consequences, and online adaptation is genuinely necessary.

Only after the scenario has been internally designed and checked should it be serialized into the required JSON format.

Return exactly one JSON object that validates against `schemas/scenario.schema.json`.

Do not output Markdown, explanations, chain-of-thought, or a separately maintained prose specification.

---

## 1. Core Scenario Requirement

Design a concrete interpersonal situation centered on a recognizable **social mechanism** and a genuine **trade-off**.

A valid SocialFlux scenario must satisfy all of the following:

* neither party should be reducible to a purely correct or purely unreasonable actor;
* the evaluated agent must pursue a meaningful goal while managing social consequences;
* different plausible actions must create different short-term and longer-term consequences;
* interaction history must materially affect how later actions are interpreted;
* the environment character must be capable of escalation, stabilization, withdrawal, negotiation, or repair depending on the trajectory;
* there must not be one universally optimal scripted response;
* successful interaction should require adaptation to how the other party's observable behavior changes over time.

Prefer conflicts involving mechanisms such as:

* trust and betrayal;
* authority and autonomy;
* fairness and self-interest;
* face threat and status;
* disclosure and privacy;
* responsibility attribution;
* reciprocity;
* boundary negotiation;
* cooperation under conflicting incentives;
* repair after interpersonal harm.

Name the primary social mechanism explicitly in the scenario.

---

## 2. Longitudinal Necessity

The scenario must genuinely require history.

Before serialization, internally verify that the following situation can occur:

$$
Same\ Current\ Action
+
Different\ Interaction\ History
\rightarrow
Different\ Appraisal
\rightarrow
Different\ State\ Transition
$$

Avoid scenarios where the current utterance alone almost completely determines the appropriate interpretation.

The scenario should contain at least one plausible historical dependency such as:

* accumulated trust or distrust;
* repeated boundary violations;
* previous concessions;
* unresolved interpersonal harm;
* failed repair attempts;
* fulfilled or broken commitments;
* repeated escalation;
* gradual relationship repair.

---

## 3. Environment Character

Define an environment persona with:

* concrete social role;
* stable personality characteristics relevant to the conflict;
* background information necessary for interpreting the interaction;
* explicit goal;
* private hidden intention.

The explicit goal should describe what the character openly wants from the interaction.

The hidden intention should represent a private incentive, concern, vulnerability, or strategic motive that influences appraisal but is never directly exposed to the evaluated agent.

The persona is **stable context**, not mutable state.

Persona traits may influence the magnitude or interpretation of state transitions but must not duplicate dynamic state variables.

---

## 4. Evaluated-Agent Role

Define:

* who the evaluated agent represents;
* what the evaluated agent knows initially;
* its explicit interaction goal;
* what information remains hidden from it.

The evaluated agent must never directly observe:

* latent state values;
* state delta labels;
* hidden intention;
* internal appraisal;
* trigger IDs;
* media-trigger thresholds;
* environment transition rules.

---

## 5. State Selection

Select only state variables that are operationally meaningful for this specific conflict.

Variables must come from the legal SocialFlux ontology and may belong to:

* Emotion;
* Behavioral Disposition;
* Relationship.

Interaction Dynamics are represented separately.

Do not select variables simply because they are available in the ontology.

Each selected variable should answer:

> If this variable changed substantially during the interaction, would that change how we interpret the social situation or what the evaluated agent should do next?

Avoid redundant variables.

In particular, do not assume that apparently opposing constructs are exact inverses unless explicitly defined that way.

---

## 6. Initial State

Construct frozen initial latent state \(S_0\) and interaction dynamics \(D_0\) on the 0–10 scale.

The values must follow naturally from:

$$
Persona
+
Background
+
Explicit\ Goal
+
Hidden\ Intention
+
Initial\ Situation
$$

The initial state should leave meaningful room for multiple trajectories.

Avoid initializing the scenario so close to an extreme that escalation, repair, or multimodal triggers become trivial.

All policy rollouts for this scenario will begin from exactly the same frozen \(S_0,D_0\).

---

## 7. Action-Effect Anchors

Define representative:

* repair;
* neutral/assertive;
* escalation

action-effect anchors using the seven legal semantic delta labels:

* `strong_decrease`
* `moderate_decrease`
* `mild_decrease`
* `similar`
* `mild_increase`
* `moderate_increase`
* `strong_increase`

These are **controlled validation anchors**, not an exhaustive action taxonomy and not a fixed transition table for normal interaction.

During actual interaction, arbitrary evaluated-agent actions will be interpreted through:

$$
Action
\rightarrow
Persona\text{-}Conditioned\ Appraisal
\rightarrow
State\ Delta
$$

The three anchor types exist so that controlled environment-sensitivity experiments can later test whether clearly different social interventions produce sensible directional divergence.

Anchor effects must therefore be:

* socially plausible;
* meaningfully different;
* strong enough to produce measurable divergence;
* not unrealistically deterministic.

---

## 8. Observable Behavior

Define how changes in the selected latent states may manifest through observable behavior.

Observable cues may include:

* wording;
* response length;
* hesitation;
* silence;
* gaze;
* facial tension;
* posture;
* speech rate;
* prosody;
* interruption;
* avoidance;
* willingness to elaborate.

Observable expressions must provide **evidence** about latent state without directly encoding the answer.

Never expose:

* private state names;
* numeric state values;
* hidden intention;
* delta labels;
* trigger IDs;
* threshold conditions.

The mapping should therefore follow:

$$
Latent\ State
\rightarrow
Observable\ Social\ Evidence
$$

rather than:

$$
Latent\ State
\rightarrow
Explicit\ State\ Label
$$

---

## 9. State-Triggered Multimodal Events

Video is a **sparse state-triggered observable event**, not a mandatory modality at every interaction turn.

First identify socially meaningful moments in this scenario where an internal change would plausibly become visibly or vocally salient.

Examples include:

* first visible loss of composure;
* clear withdrawal from negotiation;
* visible relief after successful repair;
* sudden defensiveness after a face threat;
* transition from guardedness to openness;
* visible relationship rupture.

Only after identifying the social event should it be operationalized as a numeric trigger.

Each video trigger must define:

* trigger mode;
* all required conditions;
* AND-combined condition semantics;
* numeric thresholds;
* cooldown;
* duration between 3 and 8 seconds;
* cue template;
* observable expression.

Prefer `crossing` triggers for salient one-time transitions.

Trigger thresholds must satisfy:

1. they do not fire from \(S_0,D_0\);
2. they are reachable through plausible interaction within the configured episode horizon;
3. they correspond to a socially meaningful event rather than an arbitrary numeric boundary;
4. they do not trivially reveal benchmark labels;
5. repeated activation is prevented when no meaningful new transition has occurred.

---

## 10. Multimodal Generation

Define a default observable expression and `media_generation` configuration.

The intended causal structure is:

$$
Evaluated\ Action
\rightarrow
Appraisal
\rightarrow
State\ Update
\rightarrow
Interaction\ Dynamics
\rightarrow
Trigger\ Check
\rightarrow
Observable\ Expression
\rightarrow
Optional\ Video
$$

Ordinary turns may remain text-only.

Video should occur only when the configured state-trigger condition is satisfied.

The video should depict natural observable social signals such as facial expression, gaze, posture, timing, and prosody.

It must not visually or verbally expose internal state labels or numeric values.

---

## 11. Episode Configuration

Specify:

* maximum interaction turns;
* termination conditions;
* T3 delayed-effect horizon.

The default T3 delayed horizon is 5 interaction turns.

A longer horizon may be used only when the scenario genuinely requires it and must not exceed 10 turns.

The episode must be long enough for meaningful state evolution, escalation, stabilization, and possible repair.

---

## 12. Benchmark Suitability Check

Before returning the JSON, internally verify that the scenario supports all four SocialFlux capabilities.

### T1 — Latent Social State Estimation

There must be checkpoints where the character's current state cannot be reliably inferred from the latest utterance alone and requires interaction history and/or observable social cues.

### T2 — History-Conditioned State Comparison

It must be possible to construct:

$$
History_A + O^*
$$

and

$$
History_B + O^*
$$

where \(O^*\) is the exact same current observation but the histories support meaningfully different latent-state interpretations.

### T3 — Counterfactual State Transition Prediction

At meaningful checkpoints, at least two plausible evaluated-agent actions must produce different immediate and delayed social-state consequences.

The distinction should not reduce to an obvious "good response versus abusive response" contrast.

### T4 — Online Adaptation

The interaction must contain opportunities where observable changes in the environment character provide useful feedback and a capable agent could adapt its subsequent strategy.

If the scenario does not naturally support all four capabilities, redesign it before serialization.

---

## 13. Anti-Template Requirements

Avoid generating a scenario that is merely a superficial rewrite of common benchmark conflicts.

Do not automatically use:

* anger as the primary emotion;
* trust as the primary relationship variable;
* hostility as the primary escalation variable;
* `>= 8` as the default video threshold;
* explicit threats as the only escalation mechanism;
* apologies as the only repair mechanism.

Select states, mechanisms, actions, and thresholds according to the actual social structure of the scenario.

Prefer subtle but consequential interpersonal dynamics over melodramatic conflict.

---

## 14. Simulator Epistemic Status

The simulator's internal state is an operational environment representation.

Do not describe simulator state as:

* psychological ground truth;
* the character's objectively true mental state;
* clinically valid emotion measurement.

Formal benchmark ground truth is established separately through the SocialFlux annotation and adjudication pipeline.

---

## 15. Sampling Configuration

Define scenario-specific sampling plans for T1, T2, and T3.

Sampling configuration should identify candidate checkpoints and construction constraints rather than pre-writing benchmark answers.

Ensure:

* T1 samples meaningful state-transition checkpoints;
* T2 supports controlled same-observation/different-history construction;
* T3 samples decision points with meaningful counterfactual divergence.

Do not expose future trajectory information in task inputs.

---

## 16. Final Internal Consistency Check

Before serialization, verify all of the following:

* every selected state variable is relevant to the conflict;
* \(S_0,D_0\) are consistent with persona and background;
* repair, neutral/assertive, and escalation anchors create plausible divergence;
* persona affects appraisal rather than acting as mutable state;
* video triggers are not active at initialization;
* video triggers are reachable within the episode;
* video triggers represent meaningful observable social events;
* observable expressions contain no hidden-state leakage;
* T1 genuinely requires state inference;
* T2 can support identical-current-observation construction;
* T3 supports nontrivial counterfactual effects;
* T4 contains meaningful opportunities for online adaptation;
* the scenario is not solvable through one universally optimal scripted response.

If any condition fails, revise the scenario internally before producing output.

---

## 17. Output Contract

Return exactly one strict JSON object that validates against:

`schemas/scenario.schema.json`

Do not output any text before or after the JSON.

Do not invent fields outside the schema.

The JSON is the canonical scenario specification.

After the JSON is saved as:

`configs/scenarios/scenario_NNN/scenario_NNN.json`

the repository workflow MUST run:

```bash
python scripts/scenario_docs.py configs/scenarios/scenario_NNN/scenario_NNN.json
python scripts/scenario_docs.py --check
```

The generated `scenario_NNN.md` is a human-review projection of the canonical JSON.

It records the source SHA-256, explains initialization, state variables, action anchors, and multimodal thresholds in natural language, and rebuilds the scenario manifest.

The generated Markdown must never become a separately maintained source of truth.

After rollout generation, the same scenario bundle MUST contain:

```text
configs/scenarios/scenario_NNN/
├── scenario_NNN.json
├── scenario_NNN.md
└── rollouts/
    ├── dialogues.md
    ├── manifest.json
    └── <trajectory_id>.json
```

`rollouts/dialogues.md` is the human-readable conversation view. The per-trajectory JSON and rollout manifest are private local research artifacts. Cross-scenario offline candidates, validation outputs, acceptance reports, and aggregate manifests belong in `build/pipeline_v1/`.

---

## Request Payload

{{payload_json}}
