# SocialFlux Blinded Instance Quality Judge v2

Purpose: assess whether one rollout-derived T1, T2, or T3 candidate is a useful, answerable benchmark item. This is quality-control evidence, not human ground truth and not a task answer.

The packet is blinded: it must not contain source model, provider, trajectory ID, private latent state, appraisal, future branch, or expected answer. Judge only what a benchmark participant would see.

Score exactly these dimensions from 1 (unusable) to 5 (strong):

- history_dependency: the item genuinely requires longitudinal evidence rather than the latest sentence alone;
- evidence_sufficiency: observable evidence is sufficient for calibrated reasoning without forcing certainty;
- social_plausibility: the interaction, motives, and language form a coherent social situation;
- nontriviality: the item is neither obvious nor arbitrary and admits meaningful distinctions;
- answerability: a careful human could make the requested probabilistic judgment.

Task-specific checks:

- T1: target character and state variables are clear; history and current checkpoint are chronologically coherent.
- T2: histories are meaningfully different, the shared O* is natural after both histories, and O* alone does not reveal the comparison.
- T3: candidate actions are plausible, executable, strategically distinct, and comparable from one shared checkpoint/horizon.

Reject an item for leakage, incoherent chronology, copied or near-identical candidates, unnatural shared O*, missing target, insufficient history, or a question that cannot be interpreted. Do not infer model identity from writing style. Give concise concrete reasons; do not solve the benchmark task.

Return JSON only conforming to schemas/instance_quality_judge.schema.json. Use exactly these keys, with no markdown and no additional keys:

{"task_type":"T1_state_tracking|T2_history_sensitive_merge|T3_counterfactual_choice_effect","scores":{"history_dependency":1,"evidence_sufficiency":1,"social_plausibility":1,"nontriviality":1,"answerability":1},"fatal_issues":[],"summary":"concise concrete quality rationale","recommendation":"use|revise|reject"}

Blinded instance packet:
{{payload_json}}
