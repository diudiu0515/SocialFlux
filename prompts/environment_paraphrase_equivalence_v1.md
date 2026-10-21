# Independent pragmatic equivalence check

Judge whether original_action and paraphrase express the same action in the
same language and context. Ignore surface word choice. Check speaker, facts,
requests, commitments, negation, conditions, urgency, politeness, pressure,
and intensity. Added or dropped propositions, changed certainty, or changed
social force are not equivalent. Do not rewrite either action. No environment
outcomes are provided; never infer equivalence from matching state changes.

Return exactly {"equivalent":true,"reason":"short specific explanation"},
using false when there is a material difference or the evidence is unclear.

{{payload_json}}
