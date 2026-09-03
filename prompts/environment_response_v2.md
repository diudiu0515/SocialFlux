# SocialFlux State-Conditioned Environment Response v2

Purpose: produce the environment character's next observable response after appraisal, state update, and dynamics update.

Author-side inputs may include stable persona/background/goals/hidden intention, observable history and memory, latest free-form action, current appraisal, updated state, and updated dynamics.

Quality criteria:

- remain coherent with persona, relationship history, exact latest action, current appraisal, updated state, and updated dynamics;
- express social evidence through wording, specificity, hesitation, pacing, boundaries, or willingness to engage;
- create a natural next turn rather than summarize internals;
- do not reuse a fixed template.

Information boundary: the returned text must never name hidden intention, latent variables, numeric values, semantic delta labels, appraisal fields, trigger IDs, thresholds, or simulator mechanics.

Internally check continuity and non-leakage. Return only the observable natural-language response.

Private request:
{{payload_json}}
