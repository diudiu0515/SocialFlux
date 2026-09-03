# SocialFlux Observable Expression Specification v1

Purpose: translate an author-side updated social state and current response context into natural observable evidence.

Produce facial behavior, gaze, pauses, speech rate, prosody, posture, and response style. Do not output state names, values, labels, hidden intention, appraisal, trigger ID, or threshold logic. Avoid stereotyped one-to-one mappings such as high anger equals an exaggerated angry face. The evidence should be inferable but ambiguous and persona/history consistent.

Internally check naturalness, non-leakage, and temporal continuity. Return JSON only conforming to schemas/observable_expression.schema.json.

Private author-side input:
{{payload_json}}
