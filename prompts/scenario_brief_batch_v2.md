# SocialFlux Claude Brief Batch v1

Design the requested batch of independent SocialFlux scenario construction
briefs. These briefs will be expanded by a separate fixed scenario-authoring
prompt and reviewed by humans later.

Return one JSON object with exactly one top-level key, `briefs`. Its value is
an array with exactly the requested records, in the requested order. Every
record must contain exactly:

```text
scenario_id
source_type
provenance_id
mechanism
relationship_structure
power_structure
goal_conflict
information_asymmetry
history_dependency
coverage_requirements
```

Rules for every brief:

- copy the requested `scenario_id`, `source_type`, and `provenance_id`
  exactly; copy requested `setting_family` exactly into
  `coverage_requirements.setting_family`;
- make the two principal characters, organization, present conflict, practical
  stakes, deadline, past events, and later verification node original;
- require at least three materially different plausible action directions;
- create genuine trade-offs: no universally correct script, obvious villain,
  trivial refusal, or predetermined ending;
- make later interpretation depend on earlier conduct so that a natural
  10–20-turn interaction can support T1, T2, T3, and T4;
- obey the requested setting family and make its concrete domain socially plausible;
- diversify domains, relationship types, power structures, stakes, temporal
  patterns, and information asymmetries across the batch and against the
  supplied prior signatures; do not turn non-work setting families into disguised
  employers, committees, compliance processes, or professional institutions;
- never read, imitate, revise, summarize, or continue any old scenario catalog,
  Qwen output, rollout, task, character, event sequence, or wording.

For `narrative-derived` records:

- `coverage_requirements.source_work` must be an object with exactly
  `title` and `medium`, where medium is `film` or `television`;
- use only a high-level social mechanism abstracted from that work;
- `coverage_requirements.adaptation_policy` must be
  `structural_abstraction_only_original_surface_text`;
- explicitly require different characters, setting, facts, stakes, event
  sequence, and dialogue; do not reproduce recognizable scenes or quotations.

For `synthetic-script` records:

- do not name or allude to a film, television work, franchise, celebrity, or
  pre-existing fictional character;
- `coverage_requirements.origin_policy` must be
  `fully_original_synthetic_scenario`.

`history_dependency` must contain 2–5 concrete non-empty strings.
`coverage_requirements` must also specify a domain, opening condition,
choice-space requirement, longitudinal need, and originality boundary.

Keep scalar fields concise. Return JSON only, without Markdown fences.

Batch request:
{{payload_json}}
