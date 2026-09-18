# SocialFlux Candidate State Values v1

Propose only the numeric S0/D0 core for this normalized scenario. The proposal
remains pending human Gate 1 and must leave room for several plausible paths.

Return JSON only with exactly these seven top-level keys:

```text
initial_state, initial_dynamics, max_turns, t3_delayed_horizon,
sampling_plan, rationale, status
```

Contracts:

- `initial_state` must use exactly the families and variable IDs in
  `selected_state_variables`, with every value numeric in [0, 10];
- `initial_dynamics` contains 2–5 scenario-specific numeric variables in
  [0, 10]; do not duplicate stable persona traits;
- derive values from the background, goals, hidden intention, and history;
- set `max_turns` to 20 and `t3_delayed_horizon` to an integer from 5 to 10;
- `sampling_plan` must be an object, never text. Use exactly the keys
  `selection_strategy`, `seed`, `t1_max`, `t2_max`, and `t3_max`; set
  `selection_strategy` to `natural_trajectory_checkpoint_sampling` and use
  integer values for the other four keys. This is sampling metadata, not a
  model action taxonomy or expected outcome;
- `rationale` must be an object, never text. Map every state family and each
  dynamics variable to one concise explanatory sentence;
- set `status` to `candidate_pending_human_freeze`;
- keep the entire JSON under 700 words and emit no other keys.

Candidate blueprint:
{{payload_json}}
