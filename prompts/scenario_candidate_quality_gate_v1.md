# SocialFlux Direct Candidate Quality Gate v1

Review the supplied candidate narrative without adding missing facts. This is a
machine screen before human Gate 1, never an approval.

Return exactly one JSON object with exactly these six top-level keys:

- `format`: exactly `socialflux_source_quality_v1`;
- `source_type`: exactly the supplied source type;
- `checks`: an object with exactly the eleven keys listed below;
- `recommendation`: one of `pass`, `revise`, `reject`;
- `summary`: concise non-empty text grounded in the supplied narrative;
- `review_status`: exactly `pending_human_review`.

`checks` must contain exactly these keys, each set to `pass`, `revise`, or
`fail`: `social_plausibility`, `real_tradeoff`, `longitudinal_necessity`,
`nontrivial_strategy_space`, `character_motivation_coherence`,
`information_asymmetry`, `t1_suitability`, `t2_suitability`, `t3_suitability`,
`t4_adaptation_opportunity`, `no_universal_script`.

Reject or revise generic conflicts, copied patterns, interchangeable personas,
one universally optimal response, missing causal history, fake trade-offs, or a
later event that does not depend on earlier conduct. Do not produce S0/D0,
actions, deltas, responses, checkpoints, answers, trajectories, numeric scores,
per-check explanations, or any additional keys.

Return JSON only.

Candidate review request:
{{payload_json}}
