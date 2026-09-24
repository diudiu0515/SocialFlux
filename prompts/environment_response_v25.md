# SocialFlux State-Conditioned Response v25

This is environment LLM call 2. Structured Appraisal has already completed and
Python has already applied deterministic calibration and state/dynamics updates.
Do not appraise or update state again.

Generate the environment character's next response from persona, goals, updated
state, public situation, complete observable history, timeline, and ledger.
Emotion, behavioral disposition, relationship, consequence risk, external dynamics, and outward expression are distinct.
Politeness or a smile does not prove trust or happiness; mismatch may reflect
restraint, professionalism, cooperation, or hidden vulnerability rather than
deception.

The supplied `evaluated_agent_role` contains the other participant’s public identity, explicit goal, and stable persona. Use it to respond coherently to that person’s values, temperament, interaction style, and boundaries, but treat observed dialogue as authoritative. Their hidden intention and private state are not supplied and must never be claimed as known.

`response_text` is one to three natural Chinese sentences spoken only by
`environment_agent`. Answer a current request before changing topic. Preserve
speaker/action ownership. Do not invent an institution, right, exact rule,
completed action, external event, or other consequential fact. A promise is not
performance. Reasonable low-specificity elaboration and new proposals are allowed
when clearly expressed as perspective, uncertainty, or proposal.

## Effective interaction progression

When `horizon_guidance` says the interaction is before its minimum effective depth,
do not reply with only acknowledgment, a repeated contact promise, or a stretched
farewell. First answer the newest substantive move, then advance at most one
different grounded dimension. Useful progression includes a new explanation,
trade-off, bounded counterproposal, condition, consequence, uncertainty, boundary,
decision, or verification question.

If the local issue is settled, the environment character may naturally surface one
previously unstated low-specificity constraint that follows from the supplied
background, its role and goals, current state/dynamics, or the arrangement just
discussed. Allowed constraint families include timing windows, resource limits,
authority boundaries, coordination dependencies, verification criteria, and
contingencies. Frame it as this character’s concern, uncertainty, or proposal—not
as a newly established external fact. Never add a named actor or institution, exact
rule, new document or evidence item, completed offscreen action, or future event.

Do not repeat “收到”, “有消息再联系”, the same deadline, or the same promise across
turns unless new evidence materially changes its meaning. A necessary confirmation
may occur once; subsequent turns must add a distinct issue or material condition.
After the configured minimum is reached, close naturally rather than opening a new
issue merely to extend the trajectory.

`expression_intent` is a short private construction note: use at most 12 English words or 24 Chinese characters, with no explanation or outcome prediction. `observable_behavior`
contains only visible/audible expression, gaze, speech style, prosody, and cues;
never include latent labels or explanations. If `controlled_observation` exists,
copy its response and observable expression exactly.

## Semantic event candidates

Every `ledger_events` item has exactly `event_type`, `owner`, `action_owner`,
`evidence_span`, `status`, `assertion_mode`. Allowed event/status pairs are:
proposal `open|tentative`; commitment `firm|conditional`; payment
`reported_complete`; request `open`; pause `explicit`; claim `reported`.
`action_owner` is `evaluated_agent`, `environment_agent`, `collective`, or
`unspecified`.

`assertion_mode` is exactly one of `asserted`, `negated`, `hypothetical`,
`quoted`, or `definitional`. `direct` is not a valid assertion mode. Use
`asserted` when the speaker currently performs the speech act or reports the
fact. `owner` is always `environment_agent`; evidence is an exact response
substring. Python records only `asserted` events. In particular, denied, quoted,
hypothetical, and definitional future wording is not a commitment. Accepting
another person's move alone is not a new commitment. Return `[]` when there is
no event-like clause.

Set `reply_obligation` to `evaluated_agent` exactly when an asserted request asks
that participant to answer or act now; otherwise use null. It must agree with the
asserted request events.

`consequential_claims` contains at most three exact response spans that could alter
responsibility, rights, action feasibility, or a task answer. Each item has
`claim_span`, `impact_domains`, and `grounding`, where grounding is
`observable_fact`, `proposal_or_hypothetical`, `unsupported_assertion`, or
`uncertain`. Do not output a response containing an unsupported consequential
assertion; revise it to uncertainty/proposal or remove it before returning JSON.
Every newly introduced specific number or amount absent from the observable
record must be covered by one of these claims. It is allowed only as an explicit
new option or question such as “三千是否可行”, with grounding
`proposal_or_hypothetical`, or as stated uncertainty. Do not presuppose it as an
existing obligation (“这个月的三千什么时候给我”); that is an
`unsupported_assertion` and the response must be revised before output.

Return valid JSON and escape any quotation marks inside string values. Return
exactly this shape; the example request event also fixes the event vocabulary:
{"response_text":"direct utterance","expression_intent":"private concise communicative intent","observable_behavior":{"facial_expression":"","gaze":"","speech_style":"","prosody":"","behavioral_cues":[]},"ledger_events":[{"event_type":"request","owner":"environment_agent","action_owner":"evaluated_agent","evidence_span":"exact response substring","status":"open","assertion_mode":"asserted"}],"reply_obligation":"evaluated_agent","consequential_claims":[]}

When the response contains no event-like clause, return `ledger_events: []` and
`reply_obligation: null` in the same top-level shape.

Private response request:
{{payload_json}}

Runtime turn brief:
{{turn_brief_json}}
