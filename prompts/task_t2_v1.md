# SocialFlux T2 History-Conditioned State Comparison v1

Purpose: compare target-character state under two different observable histories followed by the exact same current observation O*.

Invariant: current_observation_A must equal current_observation_B byte-for-byte in text, expression, media, and metadata. Use only history differences to infer state differences.

Do not access private state, hidden intention, appraisal, deltas, source trajectory IDs, construction metadata, or future branches. For each requested state, return the schema-defined directional probability distribution, evidence IDs from A and B, causal relevance, and calibrated confidence. Use cannot_determine when evidence is insufficient.

Internally verify the shared observation is identical and evidence IDs exist. Return JSON only according to schemas/task_t2_output.schema.json.

T2 instance:
{{payload_json}}
