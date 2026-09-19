# SocialFlux Scenario Core Normalization v1

Convert the screened narrative into only the stable social core of one new
scenario. This is a machine candidate for human Gate 1, not an approval.

Return one JSON object with exactly these six top-level keys:

```text
scenario_id, title, mechanism, source, narrative_design, background
```

Contracts:

- copy the requested `scenario_id`, source `type`, and `provenance_id` exactly;
- `source` contains exactly `type`, `provenance_id`, `surface_text_policy`, and
  `redistribution_status`; set `surface_text_policy` to
  `original_surface_text`;
- `narrative_design` contains exactly `relationship_structure`,
  `power_structure`, `goal_conflict`, `information_asymmetry`,
  `relevant_history`, and `meaningful_choice_space`;
- the first four narrative fields are non-empty strings; `relevant_history`
  is a JSON array of 1–5 non-empty strings and `meaningful_choice_space` is a
  JSON array of 3–6 non-empty strings—never serialize either array as prose;
- `relevant_history` contains only public facts that have already happened or
  currently hold. It may name a publicly known scheduled procedure, but never
  disclose that procedure's future result, hidden content, predicted branch,
  or author-only interpretation;
- provide at least three genuinely different meaningful choices, without a
  best action, predicted outcome, task answer, or action taxonomy;
- preserve the narrative's causal and temporal depth for 10–20 natural turns;
- keep each scalar text field to one concise sentence, each history/choice item
  to one sentence, and the entire JSON under 750 words;
- do not output characters, state variables, S0/D0, thresholds, triggers,
  labels, checkpoints, trajectories, or any other top-level key.

Return JSON only.

Candidate payload:
{{payload_json}}
