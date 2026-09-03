# SocialFlux Local Intervention Validation v1

Purpose: construct or review a causal environment test at one real checkpoint from a naturally evolved free-form trajectory.

Hold scenario, environment character, full history, S_t, and D_t fixed. Introduce several locally plausible natural-language actions, independently run the same environment transition for each, and compare resulting state/dynamics.

Do not use global strategy labels, multi-turn scripted policies, scenario-authored expected deltas, or pre-written numeric answers. A hypothesis may describe why actions could differ, but the environment must infer each transition independently. Human review remains required for qualitative social plausibility.

Return JSON only conforming to schemas/local_intervention_review.schema.json.

Author-side experiment packet:
{{payload_json}}
