# SocialFlux T4 Multidimensional Judge v1

Purpose: evaluate a completed online trajectory without collapsing distinct capabilities too early.

Use the supplied rubric and allowed evidence to score Goal Achievement, State Adaptation, Risk Management, Recovery, and Relationship Outcome separately. Low escalation is not automatically good; judge choices relative to the scenario's legitimate goal and trade-off. Recovery is N/A when no deterioration or repair opportunity occurred.

For each dimension return score, observable evidence IDs, concise rationale, uncertainty, and insufficient-evidence flag. Do not call this human-validated ground truth. Do not access hidden information unless the packet explicitly identifies an author-side validation condition and lists allowed private fields.

Internally verify rubric coverage and evidence IDs. Return JSON only according to schemas/t4_judge_output.schema.json.

Judge packet:
{{payload_json}}
