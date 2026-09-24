# SocialFlux Structured Appraisal v11

This is environment LLM call 1. Interpret only the evaluated participant's
latest utterance. Do not write the other person's reply and do not choose numeric
state updates. Python will deterministically calibrate and update state/dynamics
before a separate Response Generation call.

Use the supplied private persona/state plus the complete public history, timeline,
and ledger. The latest utterance is always authored by `evaluated_agent`.

The `evaluated_agent` object contains that participant’s public role, explicit goal, and stable persona. Use it to interpret their likely communication and boundaries together with observed behavior; persona is not evidence that an act occurred. Their hidden intention and private state are not supplied and must never be claimed as ground truth.

Return all ten `event_features` as integers from -2 to 2:
`goal_alignment`, `cooperation_signal`, `repair_signal`, `pressure`,
`face_threat`, `commitment_signal`, `uncertainty_reduction`,
`boundary_violation`, `respect_signal`, `withdrawal_signal`.

`state_impacts` and `dynamics_impacts` are sparse candidates using only supplied
variable paths. Each item has `variable`, `direction` (`increase`/`decrease`),
`evidence_strength` (1/2), `directness` (`direct`/`indirect`), and
`new_evidence` (boolean). Repeating the same information or reason alone is not
new evidence; a newly occurring act is new behavioral evidence even when it
repeats an earlier act (for example, another demand, boundary violation, or act
of pressure). A promise is not performance, and elapsed time is not performance.
Use at most four exact supplied evidence IDs.

## Semantic event candidates

Every `ledger_events` item has exactly `event_type`, `owner`, `action_owner`,
`evidence_span`, `status`, and `assertion_mode`. The span must be a non-empty
verbatim substring of the latest utterance and `owner` is `evaluated_agent`.

Allowed event types/statuses are: proposal `open|tentative`; commitment
`firm|conditional`; payment `reported_complete`; request `open`; pause `explicit`;
claim `reported`. `action_owner` is `evaluated_agent`, `environment_agent`,
`collective`, or `unspecified`.

`assertion_mode` is one of:

- `asserted`: the speaker currently performs the speech act or reports the fact;
- `negated`: the clause explicitly denies that act/fact;
- `hypothetical`: the speaker only imagines, supposes, or asks about making the
  speech act; an `if` condition on a commitment made now does not make it
  hypothetical;
- `quoted`: it reports another person's wording or attributed position;
- `definitional`: it defines or classifies something rather than undertaking an action.

Include an event-like clause with its non-asserted mode when confusing it with an
actual commitment/request/payment would change the ledger. Python records only
`asserted` events. A commitment requires the speaker's current undertaking to
perform a future action. "If you send the material tonight, I will review it by
tomorrow morning" is an asserted `commitment` with `status: "conditional"`;
"If I promised to review it tomorrow, what would happen?" is hypothetical.
Future-looking words inside denial, quotation, a merely imagined commitment, or
a definition are not commitments. A payment is always a reported claim until a
public event verifies it.

`ledger_resolutions` handles dispositions of existing `active_proposals`; it is
not a list of new events. Each item has exactly `target_id`, `resolution`
(`accepted`, `rejected`, or `countered`), and `evidence_span`. `target_id` must be
the exact ID of the affected active proposal, and the span must be a non-empty
verbatim substring of the latest utterance. Output `[]` when there is no explicit
disposition. Accepting or rejecting another person's proposal belongs here and
is not a new commitment. A counteroffer both resolves the referenced proposal as
`countered` here and creates a new proposal in `ledger_events`. If the speaker
also separately undertakes their own future action, record that undertaking as a
commitment event.

## Dialogue diagnostics

`substantive_novelty.label` is one of `new_explanation`, `new_position`,
`new_tradeoff`, `new_evidence`, `new_decision`, `necessary_confirmation`, `none`.
A bare acknowledgment, repeated deadline, repeated contact promise, farewell, or
paraphrase of either speaker’s last two moves is `none`. A newly surfaced timing,
resource, authority, dependency, verification, or contingency constraint counts
only when it materially changes the trade-off or next decision and is framed as the
speaker’s concern, uncertainty, or proposal rather than an established external fact.

For each consequential assertion that could alter responsibility, rights, action
feasibility, or a task answer, return an exact span and classify grounding as
`observable_fact`, `speaker_report`, `proposal_or_hypothetical`,
`unsupported_assertion`, or `uncertain`. Use `speaker_report` for the speaker's
new first-person report of a past action or completed result that has not been
independently verified (for example, "I sent the file yesterday"). Keep it
separate from facts already established by public history, timeline, ledger, or
direct observation. A character may reveal feelings or make proposals, but a new
concrete past action, completed result, authority, or responsibility allocation
is not an observable fact merely because it sounds plausible.

`continuation.status` is `must_answer`, `continue`, or `can_close`. Also state what
would remain `after_direct_response`. Live questions are optional design space,
not a checklist. Prefer `continue` only when a distinct grounded facet, material
constraint, or unresolved decision remains after the direct answer. Prefer
`can_close` once only acknowledgments or reformulations remain. Do not manufacture
a live question to fill turns; the separate response horizon may still ask the
environment character to surface one scenario-grounded constraint before the
minimum effective depth.

Return exactly one compact valid JSON object. Escape any quotation marks copied
inside string values:

{"appraisal":{"speaker_intent":"...","social_act":"request","event_features":{"goal_alignment":0,"cooperation_signal":0,"repair_signal":0,"pressure":0,"face_threat":0,"commitment_signal":0,"uncertainty_reduction":0,"boundary_violation":0,"respect_signal":0,"withdrawal_signal":0},"state_impacts":[],"dynamics_impacts":[],"ledger_events":[{"event_type":"request","owner":"evaluated_agent","action_owner":"environment_agent","evidence_span":"exact substring","status":"open","assertion_mode":"asserted"}],"ledger_resolutions":[],"dialogue_diagnostics":{"substantive_novelty":{"label":"new_position","evidence_span":"exact substring"},"consequential_claims":[],"continuation":{"status":"must_answer","evidence_span":"exact substring","after_direct_response":{"status":"can_close","evidence_span":"exact substring","resolved_live_questions":[],"remaining_live_questions":[]}}}},"evidence_turn_ids":[]}

Private appraisal request:
{{payload_json}}

Exact latest action:
{{latest_action_text}}
