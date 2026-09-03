# SocialFlux Independent Human Annotation v2

Purpose: independently validate environment behavior or establish formal T1/T2/T3 labels. Human annotators validate evidence; they do not reproduce the simulator.

Use only the displayed annotation packet. Treat simulator candidates as hypotheses, never psychological ground truth.

For environment validation, rate requested transition direction/plausibility, persona consistency, history sensitivity, response-state consistency, or full-trajectory plausibility.

For formal benchmark GT, annotate observable T1/T2/T3 instances independently, record evidence turn IDs, confidence, uncertainty, and quality flags. If evidence is insufficient, use the schema's uncertainty option. Do not infer hidden intention, author effects, private state, appraisal, trigger conditions, or future branches unless the packet explicitly defines an author-side validation task.

Internally verify evidence IDs are observable and output conforms to the supplied annotation schema. Return JSON only.

Annotation packet:
{{payload_json}}
