# SocialFlux Structured Appraisal v3

This is the first and only model call before deterministic state calibration.
Interpret the evaluated participant's latest action in context. Do not generate
a response and do not output state/dynamics delta labels or numeric updates.

Use the environment character's persona, background, explicit goal, hidden
intention, retrieved observable history, previous state/dynamics, and exact
latest action. Judge the newest action's incremental social evidence. Existing
conflict may alter meaning but is not new harm on every turn.

`speaker_intent` must describe what the evaluated participant is trying to do
with the exact latest action. Never use the environment character's name, role,
or private goal as the actor of that intent; the environment character is the
observer/appraiser, not the speaker of the action.

Choose exactly one `social_act` from:

`inform`, `question`, `request`, `proposal`, `conditional_offer`,
`tentative_plan`, `commitment`, `delivery`, `concession`, `clarification`,
`challenge`, `accusation`, `threat`, `boundary`, `refusal`, `deferral`,
`repair`, `withdrawal`, `other`.

Return every fixed event feature as a JSON integer from -2 through 2. Write
positive values as `1` or `2`; JSON forbids `+1` and `+2`.

- `goal_alignment`: -2 clearly obstructs the explicit goal; 2 clearly advances it.
- `cooperation_signal`: -2 active obstruction; 2 concrete cooperation.
- `repair_signal`: -2 fresh relational damage/evasion; 2 concrete repair or ownership.
- `pressure`: -2 clearly relieves pressure/preserves choice; 2 adds coercive pressure.
- `face_threat`: -2 restores dignity; 2 humiliates or attacks standing.
- `commitment_signal`: -2 breaks/withdraws a commitment; 2 delivers or makes a concrete commitment.
- `uncertainty_reduction`: -2 creates material ambiguity; 2 provides verified clarity.
- `boundary_violation`: -2 respects/protects a boundary; 2 violates one.
- `respect_signal`: -2 clear disrespect; 2 clear respect/recognition.
- `withdrawal_signal`: -2 concrete re-engagement; 2 disengagement or abandonment.

Zero means absent, neutral, or too weak to count. Ordinary polite wording alone
is not a signal. A promise is not delivery. Respectful firmness is not a threat.

Reserve an all-zero feature vector for a genuinely phatic, neutral, repeated,
or socially ineffective turn. A concrete delivery, commitment, concession,
repair, refusal, boundary, threat, or substantive proposal/request normally has
at least one non-zero feature. Evaluate what the action actually does, not just
its polite surface wording. Examples: sending requested evidence is usually a
cooperation/commitment/uncertainty-reduction signal; explicitly owning a broken
promise and naming a repair action is a repair signal; adding an ultimatum or
sanction is pressure even when phrased politely.

`state_impacts` and `dynamics_impacts` are sparse candidate lists, not final
deltas. Use variable paths copied exactly from `previous_state` and
`previous_dynamics`; the payload also supplies the exact flattened allowlists
`state_variable_paths` and `dynamics_variable_paths`. Event feature names are
never state/dynamics variables. Include all ten event-feature keys even when
their value is zero. Usually identify 0–2 state impacts and 0–1 dynamics impact;
include more only when the newest action is an unambiguous consequential event.
Omit unaffected variables. Interpret impacts against the complete event-feature
vector; do not add evidence IDs or explanatory fields inside impact objects.
When the feature vector contains a clear non-zero social signal, include at
least one candidate impact if any supplied state/dynamics variable can
plausibly register it. Empty impact lists mean the action provides no meaningful
new evidence for any supplied variable; do not use them merely to be cautious.

Choose the primary social act, not the last grammatical form in the sentence.
For example, “I uploaded the file; please confirm” is primarily `delivery`, and
“I will support you if the audit is opened” is `conditional_offer`, not a generic
`request`.

For each impact:

- `variable` is required and must be one exact path from the corresponding
  supplied allowlist. Every non-empty impact object has exactly these five keys:
  `variable`, `direction`, `evidence_strength`, `directness`, `new_evidence`.
- `direction` is `increase` or `decrease` for that named variable.
- `evidence_strength` is 1 for clear but limited evidence, 2 only when the newest action is consequential enough to change near-term conduct.
- `directness` is `direct` only when the action itself clearly supports the impact; otherwise `indirect`.
- `new_evidence` is false when the impact merely repeats an old condition; such an impact will be deterministically suppressed.

Use 0–4 unique evidence IDs copied exactly from `memory.relevant_turn_ids`.

Return one compact JSON object only:

{"appraisal":{"speaker_intent":"...","social_act":"request","event_features":{"goal_alignment":0,"cooperation_signal":0,"repair_signal":0,"pressure":0,"face_threat":0,"commitment_signal":0,"uncertainty_reduction":0,"boundary_violation":0,"respect_signal":0,"withdrawal_signal":0},"state_impacts":[],"dynamics_impacts":[]},"evidence_turn_ids":[]}

Private appraisal request:
{{payload_json}}
