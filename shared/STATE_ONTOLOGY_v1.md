# SocialFlux State Ontology v1

## Scale and update

Every mutable state and interaction-dynamics value is bounded to 0–10. A value is scenario-relative intensity, not a clinical score or population norm.

The model emits exactly one semantic delta per selected variable:

| Label | Numeric update |
|---|---:|
| strong_decrease | -3 |
| moderate_decrease | -2 |
| mild_decrease | -1 |
| similar | 0 |
| mild_increase | +1 |
| moderate_increase | +2 |
| strong_increase | +3 |

Code clamps the result to 0–10. Persona, role, explicit goal and hidden intention are stable context and are never mutable state.

## State families

- emotion: short-horizon subjective experience, such as anger, anxiety, hope, sadness, fear, guilt, shame, disappointment or relief.
- motivation: current action readiness, such as resolve, avoidance_urge, repair_intent or resistance_intent.
- coping: situation-conditioned orientation, such as assertiveness, strategic_patience, evidence_seeking or endurance.
- relationship: current relational belief/stance, such as trust, hostility, respect, perceived_safety or affiliation.

A scenario selects only variables causally relevant to its social mechanism. Opposing-looking variables are not forced complements.

## Interaction dynamics

D_t is separate from a character’s subjective state. Current canonical examples include:

- goal_failure_risk: the interaction is moving away from the evaluated role’s legitimate goal;
- escalation_risk: the interaction is becoming harder or costlier to continue;
- negotiation_open: meaningful exchange and adaptation remain possible.

Additional dynamics require an operational definition and schema review. Objective risk must not be mislabeled as emotion.

## Naming and evidence

Machine IDs use snake_case and express one construct. Every new variable needs an operational definition, neighboring-concept distinction, and evidence that it is observable/inferable in the scenario. Actions, completed events, moral judgments and personality traits are not state variables.

Formal benchmark ground truth comes from independent human annotation. Simulator values remain private environment variables and diagnostic evidence.
