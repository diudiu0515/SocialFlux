# Environment Persona Intervention v1

Create one controlled counterfactual persona for a Gate 2 experiment.

Change only the environment agent's interaction style while preserving identity
and situation. Keep `name`, `role`, `core_values`, and `boundaries`
exactly unchanged. Replace `temperament`, `communication_style`,
`decision_style`, and `conflict_style` with a coherent but meaningfully
contrasting profile. The alternative must remain socially plausible and must
not mention the experiment, state variables, scores, thresholds, or benchmark
answers.

Do not change the explicit goal, hidden intention, history, current state,
current dynamics, action, or observation. Return exactly:

```json
{"persona":{"name":"...","role":"...","core_values":["..."],"temperament":["..."],"communication_style":"...","decision_style":"...","conflict_style":"...","boundaries":["..."]}}
```

Controlled experiment payload:

{{payload_json}}
