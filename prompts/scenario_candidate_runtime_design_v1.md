# SocialFlux Scenario Role and State Design v1

Using the frozen social core and its original narrative, design only the roles
and state-variable vocabulary. This remains pending human Gate 1.

Return one JSON object with exactly these six top-level keys:

```text
environment_agent, evaluated_agent_role, selected_state_variables,
target_state_ids, multimodal_event_concepts, suggested_horizon
```

Contracts:

- `environment_agent` contains a `persona` object, public `explicit_goal`, and
  private `hidden_intention` grounded in this scenario. `persona` must never be
  text: it must contain text `name`, text `role`, and 3–6 compact scalar traits;
- `evaluated_agent_role` contains exactly `character_id`, `name`, `role`, and
  `explicit_goal`; set `character_id` to `EVALUATED_AGENT`;
- `selected_state_variables` maps scenario-relevant families to concise state
  IDs. Use only variables that can change gradually during this interaction;
- `target_state_ids` uses `family.variable` IDs that all resolve to
  `selected_state_variables`;
- `multimodal_event_concepts` contains three observable, non-private expression
  concepts suitable for later threshold authoring;
- keep persona to at most six compact scalar traits, use 4–8 total state
  variables, and keep the entire JSON under 650 words;
- set `suggested_horizon` to 20;
- do not output numeric S0/D0, thresholds, action categories/effects, response
  templates, checkpoints, labels, answers, trajectories, or extra keys.

Return JSON only.

Candidate payload:
{{payload_json}}
