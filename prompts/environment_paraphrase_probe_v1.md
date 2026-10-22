# Environment Paraphrase Probe v1

Rewrite the latest evaluated-agent action in natural Chinese while preserving
its speaker, social intent, commitments, requests, factual content, politeness,
and intensity. Change only wording and syntax. Do not add, remove, strengthen,
or weaken any claim. Do not include a speaker label, quotation marks, analysis,
or stage directions.

Rewrite only `latest_action`; context explains meaning but is not content to add.
Do not answer the action, continue the interaction, or import a proposal from
recent history. The payload's `strict_surface_constraints` is mandatory:

- preserve every item in `semantic_numbers_exact` exactly;
- for every `required_marker_groups` category, retain at least one listed marker;
- do not introduce markers from any `forbidden_marker_groups` category;
- preserve `question_force`, including whether the output is a question.

The output must be genuinely reworded: change syntax or substitute meaningful
wording while preserving all of those pragmatic constraints. Do not return the
source sentence unchanged.

Return exactly one JSON object:

```json
{"paraphrase":"one concise single-speaker turn"}
```

Experiment context:

{{payload_json}}
