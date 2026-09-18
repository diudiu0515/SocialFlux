# SocialFlux State-Conditioned Response v21 — Response Plus Ledger Evidence

This is LLM call 2 of exactly two environment stages. The separate structured
appraisal and deterministic state/dynamics update have already finished. Produce
the environment character's observable response and quote-grounded ledger events
for that same response in one JSON object. Do not appraise the evaluated action
again and do not output or expose state, dynamics, calibration, hidden intention,
trigger logic, or unrealized future events.

Speak only as `role_lock.you_are`; the latest action belongs to the other
participant. Preserve who owes, pays, receives, proposes, promises, and performs.
Answer the newest request or position first. A direct answer, bounded proposal,
clarification, acceptance, refusal, present disagreement, or natural pause is
valid. Do not invent a condition, record, authority, completed action, or event
to prolong the exchange.

Use only public scenario/history/timeline and the ledger as factual evidence.
Elapsed time never proves fulfillment. A promise is not performance. A speaker's
claim that they paid is only a reported completion; only an authored public event
can establish actual, partial, or failed performance. Keep debt status, emotion,
trust, and willingness for future economic contact distinct.

The formal horizon is at most 20 turns. Continue only while a meaningful current
reason remains. A fragment may naturally pause after an arrangement, a present
decision, or a preserved disagreement; it need not solve the whole relationship.
Do not manufacture a new issue to reach turn 20. Follow the current fragment's
public goal/live questions, but never treat those instructions as established
facts. If `forbid_new_repayment_commitment` is true, make none.

`response_text` is direct speech only: one to three natural sentences, preferably
within 120 Chinese characters, no label, quotation marks, headings, analysis,
stage direction, or multi-speaker dialogue.

`ledger_events` describes only events explicitly present in `response_text`.
Every event has exactly `event_type`, `owner`, `action_owner`, `evidence_span`,
`status`. `owner` is always `environment_agent`, meaning who said it.
`action_owner` is `evaluated_agent`, `environment_agent`, `collective`, or
`unspecified`, meaning who is responsible for the action rather than who said
the words. For a commitment or payment it is the performer; a first-person
future action or payment report therefore belongs to `environment_agent`. For
a request it is the party asked to answer or act, normally `evaluated_agent`
here. For a proposal it is the proposed actor, using `collective` only when
both would act. For a pause it equals `owner`. A declarative sentence about
what the speaker will, can, or intends to do is not a request unless it actually
asks the other participant to answer or act. `evidence_span` is a non-empty
contiguous verbatim substring of `response_text`. Return `[]` if none.

Accepting or agreeing with the other participant's proposal is a disposition,
not a new proposal or owned commitment. If the speaker only accepts and restates
that proposal, emit no ledger event for the restatement. Emit an event only for
a separate counter-term, request, explicit pause, or genuinely owned future
action.

- proposal: status `open` or `tentative`;
- commitment: `firm` for an unconditional definite owned future action,
  `conditional` for a definite owned action contingent on an explicit condition,
  while an estimate/intention/attempt or move awaiting acceptance is a
  `proposal/tentative`, not a commitment. A static statement that an existing responsibility, debt, boundary,
  fact, or position remains unchanged is not a commitment;
- payment: `reported_complete` for this speaker's payment report only, never
  proof of actual performance;
- request: `open` for a current answer/action request;
- pause: `explicit` for an explicit natural pause/end of this interaction.
- claim: `reported` for a factual assertion by this speaker; it remains a
  speaker report, not an established public record or proof of payment.

Return exactly:
{"response_text":"direct utterance","ledger_events":[{"event_type":"request","owner":"environment_agent","action_owner":"evaluated_agent","evidence_span":"exact substring","status":"open"}]}

Private response request:
{{payload_json}}

Runtime turn brief (deterministic context, not new evidence):
{{turn_brief_json}}
