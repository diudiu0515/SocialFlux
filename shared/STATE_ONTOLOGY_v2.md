# SocialFlux Persona and State Ontology v2

## Stable private persona

The environment character has a stable private persona `P`. It conditions appraisal, deterministic state calibration, response generation, and author-side answer proposals, but it is never included in the observation or task instance shown to the evaluated model.

The canonical persona contains identity plus stable `core_values`, `temperament`, `communication_style`, `decision_style`, `conflict_style`, and `boundaries`. Public and private goals are stored separately as `explicit_goal` and `hidden_intention`.

Current emotion, trust, willingness, pressure, information possession, leverage, and risk are not persona traits. Persona, role, goals, and hidden intention do not change during a trajectory.

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

## Four mutable state families

Every v2 scenario uses exactly these four top-level families:

- `emotion`: short-horizon subjective experience, such as anger, anxiety, hope, sadness, fear, guilt, shame, disappointment, frustration, or relief.
- `behavioral_disposition`: current situation-conditioned action readiness, such as resolve, avoidance urge, repair intent, resistance intent, disclosure willingness, cooperation readiness, evidence seeking, or boundary assertion. This is not stable personality and not the explicit goal.
- `relationship`: current stance toward the other participant, such as trust, hostility, respect, perceived safety, affiliation, or perceived fairness.
- `consequence_risk`: the character's current assessment of downstream harm, such as goal failure, relationship rupture, reputational harm, material loss, safety harm, institutional harm, commitment breach, or exclusion.

Every family is present and contributes at least one variable. A scenario selects 4–8 variables in total from the approved vocabulary. Arbitrary new families or variables require an ontology revision before authoring. Opposing variables are not forced complements.

## Interaction dynamics

`D_t` is separate from character state and contains only external interaction conditions: `deadline_pressure`, `resource_scarcity`, `information_asymmetry`, `public_exposure`, `negotiation_openness`, `coordination_stability`, and `institutional_constraint`.

For example, `deadline_pressure` is dynamics; the environment character's resulting `goal_failure_risk` is state. A v2 scenario selects 2–5 dynamics. Additional dynamics require an operational definition and schema revision.

## Naming, visibility, and evidence

Machine IDs use snake_case and express one construct. Every new variable needs an operational definition, neighboring-concept distinction, and evidence that it is observable or inferable in the scenario. Actions, completed events, moral judgments, and personality traits are not state variables.

The environment-generation and author-side answer LLMs may read private persona. The evaluated policy/model may read only public identity, role, explicit goal, scenario facts, observable history, and observable expressions. It never reads persona traits, hidden intention, state, dynamics, appraisal, or deltas.

Formal benchmark ground truth comes from independent human annotation. Simulator values and private persona remain author-side diagnostic evidence.
