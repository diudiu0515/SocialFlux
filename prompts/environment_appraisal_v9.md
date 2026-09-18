# SocialFlux Structured Appraisal v9 — Quote-Grounded Ledger

This is LLM call 1 of exactly two environment stages. Interpret only the
evaluated participant's latest action. Do not generate the environment reply and
do not output state/dynamics delta labels or numeric updates. Deterministic code
will calibrate and apply numeric changes after this JSON is returned and before
the separate response call.

Use the supplied persona, public background/history/timeline, current fragment,
interaction ledger, previous state/dynamics, and exact latest action. Existing
conflict is context, not automatically new harm. `speaker_intent` and every
`ledger_event.owner` refer to `evaluated_agent`, never the environment character.

Choose one `social_act` from:
`inform`, `question`, `request`, `proposal`, `conditional_offer`,
`tentative_plan`, `commitment`, `delivery`, `concession`, `clarification`,
`challenge`, `accusation`, `threat`, `boundary`, `refusal`, `deferral`,
`repair`, `withdrawal`, `pause`, `other`.

Return all ten event features as JSON integers from -2 to 2:
`goal_alignment`, `cooperation_signal`, `repair_signal`, `pressure`,
`face_threat`, `commitment_signal`, `uncertainty_reduction`,
`boundary_violation`, `respect_signal`, `withdrawal_signal`.
Zero means absent, neutral, repeated, or too weak. A promise is not performance.

`state_impacts` and `dynamics_impacts` are sparse semantic candidates, not final
updates. Use only exact supplied variable paths. Each entry has exactly:
`variable`, `direction` (`increase`/`decrease`), `evidence_strength` (1/2),
`directness` (`direct`/`indirect`), `new_evidence` (boolean). Repeated evidence
uses `new_evidence=false`. Use 0–4 exact IDs from `memory.relevant_turn_ids`.

## Quote-grounded ledger events

Return `ledger_events` for observable action types in the exact latest action.
Each event has exactly `event_type`, `owner`, `action_owner`, `evidence_span`,
`status`. `owner` is always `evaluated_agent`, meaning who uttered the event.
`action_owner` is `evaluated_agent`, `environment_agent`, `collective`, or
`unspecified`, meaning who is responsible for the action rather than who said
the words. For a commitment or payment it is the performer; a first-person
future action or payment report therefore belongs to `evaluated_agent`, even
when it conflicts with the scenario role. For a request it is the party asked
to answer or act, normally `environment_agent` here. For a proposal it is the
proposed actor, using `collective` only when both would act. For a pause it
equals the speaker. A declarative sentence about what the speaker will, can, or
intends to do is not a request unless it actually asks the other participant to
answer or act. `evidence_span` must be one non-empty, contiguous, verbatim
substring of the latest action. Return `[]` when none.

Accepting or agreeing with the other participant's proposal is a disposition,
not a new proposal or owned commitment. If the speaker only accepts and restates
that proposal, emit no ledger event for the restatement. Emit an event only for
a separate counter-term, request, explicit pause, or genuinely owned future
action.

- proposal: status `open` or `tentative`;
- commitment: `firm` only for an unconditional definite owned future action,
  `conditional` for a definite owned action that occurs if an explicit condition
  is met. An intention, estimate, attempt, or move awaiting acceptance is a
  `proposal/tentative`, not a commitment. A statement that an existing responsibility, debt,
  boundary, fact, or position remains unchanged is not a commitment because it
  does not undertake a new future action;
- payment: status `reported_complete` only when this speaker reports payment;
  this is a claim, not proof of actual performance;
- request: status `open` when an answer/action is currently requested;
- pause: status `explicit` when this speaker explicitly pauses/ends the current
  interaction without claiming the whole relationship is solved.
- claim: status `reported` for a factual assertion by this speaker. It remains
  a speaker report, not an established public record and not proof of payment.

Separate multiple events when one utterance contains them. Do not infer a
payment, promise, request, or pause from earlier history. Amounts and deadlines
remain inside the quote; deterministic code will parse and record them.
If a `firm` or `conditional` commitment event is present, `commitment_signal`
must be positive; otherwise the JSON is internally inconsistent.

## Dialogue diagnostics

Return `dialogue_diagnostics` with:

- `substantive_novelty`: label is `new_explanation`, `new_position`,
  `new_tradeoff`, `new_evidence`, `new_decision`, `necessary_confirmation`, or
  `none`; evidence is an exact latest-action span (empty only for `none`).
- `consequential_claims`: at most three exact claim spans, each with
  `impact_domains` drawn from `responsibility`, `rights`, `action_feasibility`,
  `task_answer`, and `grounding` drawn from `observable_fact`,
  `proposal_or_hypothetical`, `unsupported_assertion`, `uncertain`.
- `continuation`: `must_answer` for a current request, `continue` for a genuine
  new reason, or `can_close` when no reason remains. Do not continue merely to
  fill turns. Include `after_direct_response`, partitioning every exact supplied
  live question once into `resolved_live_questions` or
  `remaining_live_questions`; it is `can_close` only when none remain.

Return one compact JSON object only, with this shape:

{"appraisal":{"speaker_intent":"...","social_act":"request","event_features":{"goal_alignment":0,"cooperation_signal":0,"repair_signal":0,"pressure":0,"face_threat":0,"commitment_signal":0,"uncertainty_reduction":0,"boundary_violation":0,"respect_signal":0,"withdrawal_signal":0},"state_impacts":[],"dynamics_impacts":[],"ledger_events":[{"event_type":"request","owner":"evaluated_agent","action_owner":"environment_agent","evidence_span":"exact substring","status":"open"}],"dialogue_diagnostics":{"substantive_novelty":{"label":"new_position","evidence_span":"exact substring"},"consequential_claims":[],"continuation":{"status":"must_answer","evidence_span":"exact substring","after_direct_response":{"status":"can_close","evidence_span":"exact substring","resolved_live_questions":[],"remaining_live_questions":[]}}}},"evidence_turn_ids":[]}

Private appraisal request:
{{payload_json}}

Exact latest action (all event/evidence spans must be copied from this text):
{{latest_action_text}}
