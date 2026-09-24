# SocialFlux Candidate State Values v2

Propose only the numeric initial-state and runtime-dynamics core for this v2 scenario. The proposal remains pending human Gate 1 and must leave room for several plausible paths.

Return JSON only with exactly these seven top-level keys:

```text
initial_state, initial_dynamics, max_turns, t3_delayed_horizon,
sampling_plan, rationale, status
```

Contracts:

- require `state_contract_version` in the blueprint to equal `socialflux_state_v2`;
- `initial_state` uses exactly the four selected families and their selected IDs: `emotion`, `behavioral_disposition`, `relationship`, and `consequence_risk`;
- preserve the two-level `family -> variable -> value` nesting and use numeric values in [0, 10]; never flatten a state path;
- Persona is stable private context. Do not copy persona traits, explicit goals, hidden intentions, deadlines, leverage, or external conditions into state;
- `behavioral_disposition` describes immediate action readiness; `consequence_risk` describes the character's current assessment of downstream harm;
- `initial_dynamics` is a flat object selecting 2–5 variables only from `deadline_pressure`, `resource_scarcity`, `information_asymmetry`, `public_exposure`, `negotiation_openness`, `coordination_stability`, and `institutional_constraint`;
- dynamics describe external interaction conditions. Do not duplicate consequence risk in the dynamics seed;
- derive all values from the stable persona, background, goals, hidden intention, history, and opening situation, while avoiding unjustified extremes;
- set `max_turns` to 20 and `t3_delayed_horizon` to an integer from 5 to 10;
- `sampling_plan` has exactly `selection_strategy`, `seed`, `t1_max`, `t2_max`, and `t3_max`; set `selection_strategy` to `natural_trajectory_checkpoint_sampling` and use integers for the remaining fields;
- `rationale` maps every state family and dynamics variable to a concise explanation without exposing a preferred policy or answer;
- set `status` to `candidate_pending_human_freeze`;
- emit no other keys.

Candidate blueprint:
{{payload_json}}
