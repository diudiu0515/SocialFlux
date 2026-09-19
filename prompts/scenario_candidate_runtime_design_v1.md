# SocialFlux Scenario Role and State Design v2

Using the frozen social core and its original narrative, design only the roles, stable private environment persona, and canonical state-variable vocabulary. This remains pending human Gate 1.

Return one JSON object with exactly these seven top-level keys:

```text
state_contract_version, environment_agent, evaluated_agent_role,
selected_state_variables, target_state_ids, multimodal_event_concepts,
suggested_horizon
```

Contracts:

- set `state_contract_version` exactly to `socialflux_state_v2`;
- `environment_agent` contains exactly `persona`, `explicit_goal`, and `hidden_intention`;
- `persona` contains exactly `name`, `role`, `core_values`, `temperament`, `communication_style`, `decision_style`, `conflict_style`, and `boundaries`;
- `core_values` and `temperament` contain 2–5 unique compact strings; `boundaries` contains 1–5; the three style fields are concise non-empty strings;
- persona fields are stable across the whole trajectory. Never put current emotion, trust, willingness, pressure, information possession, leverage, deadlines, or risk in persona;
- `evaluated_agent_role` contains exactly `character_id`, `name`, `role`, and `explicit_goal`; set `character_id` to `EVALUATED_AGENT` and do not add private personality fields;
- `selected_state_variables` has exactly four families, all present and non-empty: `emotion`, `behavioral_disposition`, `relationship`, and `consequence_risk`;
- select only from this approved vocabulary:
  - emotion: `anger`, `anxiety`, `hope`, `sadness`, `fear`, `guilt`, `shame`, `disappointment`, `frustration`, `relief`;
  - behavioral_disposition: `resolve`, `avoidance_urge`, `repair_intent`, `resistance_intent`, `disclosure_willingness`, `cooperation_readiness`, `evidence_seeking`, `boundary_assertion`;
  - relationship: `trust`, `hostility`, `respect`, `perceived_safety`, `affiliation`, `perceived_fairness`;
  - consequence_risk: `goal_failure_risk`, `relationship_rupture_risk`, `reputational_harm_risk`, `material_loss_risk`, `safety_harm_risk`, `institutional_harm_risk`, `commitment_breach_risk`, `exclusion_risk`;
- select 4–8 variable IDs total across the four families. Every family contributes at least one variable. Use arrays of strings, never descriptions or scalar values;
- `behavioral_disposition` means current situation-conditioned action readiness, not stable personality and not the explicit goal;
- `consequence_risk` means the environment character's current assessment of downstream harm, not an external pressure variable;
- `target_state_ids` is a non-empty unique subset of the selected `family.variable` paths;
- `multimodal_event_concepts` contains three observable, non-private expression concepts suitable for later threshold authoring;
- set `suggested_horizon` to 20;
- do not output numeric S0/D0, action effects, response templates, checkpoints, labels, answers, trajectories, or extra keys.

Return JSON only.

Candidate payload:
{{payload_json}}
