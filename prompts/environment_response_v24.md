# SocialFlux State-Conditioned Response v24 — Speech, Expression Intent, and Observable Behavior

This is LLM call 2 of exactly two environment stages. Structured appraisal has
already finished, and Python has already applied deterministic calibration and
state/dynamics updates. Do not appraise again.

Generate one response by combining the current state, the character's goal and
persona, the public situation, and observable history. Emotion, motivation,
relationship state, and outward expression are distinct. A smile does not prove
happiness; agreement does not prove restored trust. A character may restrain
irritation to preserve cooperation, speak politely because of a professional
role, or hide vulnerability without deceiving anyone. Expression may also match
state, and uncertainty is allowed.

`response_text` is only the environment character's direct speech: one to three
natural Chinese sentences. Preserve speaker and action ownership. Do not invent
institutions, rights, exact rules, completed actions, or external events. A
promise is not performance. Do not expose private state, numeric values, hidden
intention, appraisal, calibration, or simulator language.

`expression_intent` is a short private construction note explaining what the
character is trying to communicate or regulate through the response. It is
stored only in the backend and is never shown to the evaluated agent or task
model. Do not treat every mismatch as deception.

`observable_behavior` contains only what a listener/viewer could perceive:
facial expression, gaze, speech style, prosody, and brief behavioral cues. Do
not write latent labels such as “high anger” or private explanations there.

If `controlled_observation` is present, this is an explicitly marked T2
controlled ending. Copy its `current_response` byte-for-byte into
`response_text`, and copy its `observable_expression` exactly into
`observable_behavior`. Infer only the private `expression_intent` from this
branch's updated state and history. This constraint applies only to that ending,
not to ordinary online dialogue.

`ledger_events` includes only quote-grounded proposal, commitment, payment,
request, pause, or reported claim events explicitly present in
`response_text`. Each event has exactly `event_type`, `owner`,
`action_owner`, `evidence_span`, and `status`. `owner` is
`environment_agent`; `action_owner` is the actual performer/addressee.
Use only these existing ledger status values: proposal `open` or `tentative`;
commitment `firm` or `conditional`; payment `reported_complete`; request
`open`; pause `explicit`; claim `reported`. Never use `pending`,
`accepted`, or an invented status. Accepting another person's move alone is
Any direct question, imperative, or sentence that asks the evaluated participant
to answer or act must include a quote-grounded `request` event with status
`open`; do not omit it merely because the same response also contains a proposal.
not a new commitment. Return [] when no event is present.

Return exactly:
{"response_text":"direct utterance","expression_intent":"private concise communicative intent","observable_behavior":{"facial_expression":"","gaze":"","speech_style":"","prosody":"","behavioral_cues":[]},"ledger_events":[]}

Private response request:
{{payload_json}}

Runtime turn brief:
{{turn_brief_json}}
