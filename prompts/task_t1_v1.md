# SocialFlux T1 Latent Social State Estimation v1

Purpose: estimate the target character's current latent social state from observable longitudinal evidence.

Use only allowed role information, complete observable history, current environment text, and allowed expression/media. Never use hidden intention, private state, delta, appraisal, trigger conditions, future trajectory, or author metadata.

For each requested state, output the schema-defined intensity probability distribution, change prediction if requested, observable evidence turn IDs, and calibrated confidence. Do not convert ambiguous cues into certainty. Internally verify all evidence IDs appear in the input.

Return JSON only according to schemas/task_t1_output.schema.json.

T1 instance:
{{payload_json}}
