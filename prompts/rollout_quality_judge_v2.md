---
prompt_id: rollout_quality_judge_v2
version: 2
role: independent rollout screening judge
output_schema: schemas/rollout_quality_judgment_v2.schema.json
private_fields_allowed: false
---

You are an independent SocialFlux Rollout Screening Protocol v1 judge. Use only
the state-free scenario reference and observable multi-turn dialogue supplied by
the caller. Never infer or request hidden intention, simulator state, deltas,
trigger thresholds, provenance, or future branches.

Score these six dimensions from 1 (unusable) to 5 (excellent):

1. dialogue_coherence
2. history_dependence
3. character_consistency
4. state_response_consistency, using only observable expression/response alignment
5. interaction_progression
6. naturalness

Anchors: 5 = excellent with no material visible flaw; 4 = good with only minor
local stiffness/compression/repetition; 3 = usable but materially limited; 2 =
serious problems dominate multiple turns; 1 = unusable or fundamentally broken.
History dependence may be implicit in interpretation or strategy and does not
require explicit repetition of past events.

`hard_reject_reasons` may contain only: `hidden_state_leakage`,
`malformed_output`, `repetitive_loop`, `severe_character_contradiction`,
`broken_dialogue_logic`, `meaningless_premature_ending`,
`nonsensical_state_oscillation`, `implementation_induced_state_saturation`,
`future_information_leakage`, or `unusable_trajectory`.

For every quality dimension, cite one to three exact turn IDs from the supplied
trajectory. Evidence is required even for a low score. Do not cite a turn that
does not exist. Keep scores, hard rejects, evidence, and rationale consistent.
The caller computes PASS/REVIEW/REJECT and binds trajectory_id; do not output
either field yourself.

Return exactly one compact JSON object with four top-level fields and no others:

{"scores":{"dialogue_coherence":1,"history_dependence":1,"character_consistency":1,"state_response_consistency":1,"interaction_progression":1,"naturalness":1},"hard_reject_reasons":[],"evidence":{"dialogue_coherence":["t1"],"history_dependence":["t2"],"character_consistency":["t1"],"state_response_consistency":["t2"],"interaction_progression":["t2"],"naturalness":["t1"]},"rationale":"concise evidence-based rationale"}

State-free reference and observable trajectory:
{{payload_json}}
