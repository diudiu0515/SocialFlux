# SocialFlux Source Narrative Quality Gate v1

Purpose: review one narrative-derived abstraction or synthetic social script before any benchmark normalization. Judge social and narrative quality first; do not design state values or benchmark answers.

Assess exactly these dimensions:

- social_plausibility;
- real_tradeoff;
- longitudinal_necessity;
- nontrivial_strategy_space;
- character_motivation_coherence;
- information_asymmetry;
- t1_suitability;
- t2_suitability;
- t3_suitability;
- t4_adaptation_opportunity;
- no_universal_script.

Constraints:

- use only supplied source material and provenance;
- identify concrete weaknesses instead of inventing missing facts;
- do not create S0/D0, state deltas, action categories, response templates, checkpoints, trajectories, labels, or ground truth;
- an LLM recommendation is quality-control evidence, never human approval;
- set review_status to pending_human_review. Only a real reviewer may later change it to approved or rejected.

Return JSON only conforming to schemas/scenario_quality_report.schema.json. Set each check to pass, revise, or fail; recommendation to pass, revise, or reject; include a concise summary.

Source review request:
{{payload_json}}
