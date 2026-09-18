# SocialFlux Candidate Expression and Trigger Design v1

Using the normalized blueprint and frozen candidate state values, propose only
the observable-expression defaults and sparse video triggers. This remains
pending human Gate 1.

Return JSON only with exactly these four top-level keys:

```text
observable_expression, media_generation, video_triggers, trigger_reachability
```

Contracts:

- `observable_expression` has a non-empty `default` object containing only
  public behavior; a single concise `cue` string is sufficient;
- `media_generation` identifies `structured_expression` as the stage and must
  not claim that an asset already exists. Prefer exactly
  `{\"stage\":\"structured_expression\",\"asset_status\":\"pending\"}`;
- define exactly three distinct `video_triggers`, each with a unique positive
  integer priority, cooldown from 2 to 4, a unique `trigger_id`, `cue_template`,
  and non-empty public `observable_expression`;
- emit only the validator-required trigger keys: `trigger_id`, `trigger_mode`,
  `conditions`, optional `change_conditions`, `priority`, `cooldown_turns`,
  `cue_template`, and `observable_expression`; omit asset IDs, spoken lines,
  durations, providers, and generated-asset claims;
- each trigger's `observable_expression` may be exactly one concise public
  `cue` string;
- each trigger mode is `threshold`, `crossing`, or `state_change`; conditions
  use only numeric paths present in the supplied `initial_state` or
  `initial_dynamics` and operators `>=`, `>`, `<=`, `<`, or `==`;
- every condition value has exactly the keys `operator` and `threshold`, for
  example `{"coordination.evidence_sharing":{"operator":">=","threshold":6}}`.
  Never use the operator as a key and never use `value` instead of `threshold`;
- threshold/crossing conditions must not already be active at S0/D0;
- a state-change trigger uses non-empty `change_conditions` and may keep
  `conditions` empty;
- `trigger_reachability` is three short strings, one per trigger;
- do not expose private state names or thresholds inside observable expression;
- keep the entire JSON under 300 words and emit no other keys.

Candidate payload:
{{payload_json}}
