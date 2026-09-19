# SocialFlux Direct Scenario Candidate Normalization v1

Purpose: turn one newly authored, machine-screened social narrative into a
canonical scenario blueprint. This is a candidate for the final human Gate 1;
machine screening is not approval.

Preserve and serialize:

- the exact requested scenario identity and synthetic-source provenance;
- the distinctive social mechanism, relationship, power asymmetry, goal
  conflict, information asymmetry, and consequential history;
- a stable private environment persona with `core_values`, `temperament`,
  communication, decision, conflict style, and boundaries, plus an explicit
  public goal and private hidden intention;
- the evaluated-agent role and explicit goal, without private personality fields;
- `state_contract_version=socialflux_state_v2` and exactly the four canonical
  state families: emotion, behavioral_disposition, relationship, and
  consequence_risk;
- at least three genuinely different meaningful choices, without prescribing a
  best action or outcome;
- enough causal and temporal depth for a natural 10–20-turn interaction.

Do not produce S0/D0, numeric thresholds, action categories, action effects,
response templates, checkpoints, labels, answers, or trajectories. Do not copy
or refer to any prior Scale catalog.

Return JSON only conforming to `schemas/scenario_blueprint.schema.json`. Use the
requested `scenario_id`, `source_type`, and `provenance_id` exactly. Set
`suggested_horizon` to 20.

Direct-authoring candidate:
{{payload_json}}
