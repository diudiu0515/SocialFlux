# SocialFlux Evaluated Persona Backfill v1

Using the frozen scenario, author only the evaluated participant’s stable public persona. Do not revise any scenario, state, goal, role, relationship, or runtime field.

Return one JSON object with exactly these eight keys: `name`, `role`, `core_values`, `temperament`, `communication_style`, `decision_style`, `conflict_style`, and `boundaries`.

- Copy `name` and `role` exactly from `evaluated_agent_role`.
- `core_values` and `temperament` each contain 2–5 unique compact strings; `boundaries` contains 1–5.
- The three style fields are concise non-empty strings.
- Describe a stable self-profile that makes this evaluated participant coherent with the frozen relationship and a plausible counterpart to the supplied environment persona. Do not make the personas mirror copies.
- The environment persona is author-only pairing context. Do not copy, expose, or paraphrase private counterpart traits as facts known by the evaluated participant.
- Never include either participant’s hidden intention, current emotion/state, appraisal, private knowledge, trigger logic, future event, answer, or outcome.
- Persona is not evidence that any action occurred and must not predetermine an optimal strategy.

Return JSON only.

Frozen persona-backfill packet:
{{payload_json}}
