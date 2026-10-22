# SocialFlux Structured Appraisal v22 — Slow-First Candidate Recall

This is environment LLM call 1. Interpret only the evaluated participant's
latest utterance. The mutable state always belongs to "environment_agent".
Do not write the environment character's reply and do not choose numeric
updates. Python calibrates candidates before a separate response call.

Return all ten event_features as integers from -2 to 2:
goal_alignment, cooperation_signal, repair_signal, pressure,
face_threat, commitment_signal, uncertainty_reduction,
boundary_violation, respect_signal, withdrawal_signal.

## State impacts

Use only supplied state paths. Each state_impacts or dynamics_impacts item
has exactly variable, direction (increase/decrease), evidence_feature,
evidence_span, evidence_strength (1/2), directness (direct/indirect), and
new_evidence (boolean).

Every impact requires a non-empty verbatim span from the latest utterance.
The selected variable's state_semantics.evidence_features is binding:
the impact's feature must be one of that variable's allowed features.
Definitions, increase/decrease evidence, non-evidence, and timescale are also
binding. Initialization rationale explains the starting value only.

state_semantics may include scenario_transition_evidence with scenario-specific
increase and decrease examples. These are private construct-matching guides,
not events that happened. Never output a candidate merely because an example
exists. The current latest utterance must itself contain a substantively
matching exact evidence span.

Before choosing candidates, independently check every supplied state path
against the latest utterance and its variable-specific semantics. Do not stop
after finding a salient variable or family, and do not let a candidate in one
family displace independent support for another family. Omit every unsupported
path; this scan is not a coverage target and an empty impact list is valid.

Apply this binding candidate-selection order before writing JSON:

1. Slow pass first. For every path whose timescale is cross_turn_slow, compare
   the latest exact words with each independently meaningful component of its
   scenario_transition_evidence. A composite scenario example is accumulated
   across turns; the current utterance need perform only one new component to
   be a candidate. Candidate does not mean state changed: Python still requires
   one decisive event or two independent consistent observations.
2. A present-tense adoption of a bounded plan or agreed process is a performed
   commitment_signal when that exact conduct is named in the scenario-specific
   slow evidence. An actual disclosure that closes the scenario's named
   information gap may be repair_signal. A future promise, generic agreement,
   praise, or task progress alone is not slow evidence.
3. If and only if a slow relationship path passes steps 1-2 with a verbatim
   current span and an allowed non-zero feature, reserve one of the two
   relationship candidate slots for it. Then fill any remaining slot with the
   strongest independently supported non-slow relationship candidate. Never
   let responsiveness or role legitimacy crowd out a supported slow candidate.
   If no slow path passes, reserve nothing and emit no slow candidate.

Example of classification, not evidence: if a supplied trust plan explicitly
names accepting an interim bounded arrangement while leaving long-term matters
to later review, a latest utterance that presently adopts that arrangement is a
trust-increase candidate using its exact adoption span and commitment_signal. It
does not itself prove trust changed. If the supplied trust plan does not name
that conduct, or the latest utterance merely promises to consider it, omit it.

The mutable state owner is always environment_agent. The latest utterance is
produced by evaluated_agent and is causal evidence only. Never copy an
evaluated-agent disposition into an Environment state merely because both use
verbs such as disclose, cooperate, investigate, avoid, or set a boundary.

Before emitting any behavioral_disposition candidate, silently complete:
"Because evaluated_agent did [exact event], environment_agent is now more/less
likely to [this variable's defined behavior]." The mechanism must be grounded
in the Environment persona, goal, variable definition, and scenario-specific
transition evidence. If it works only by swapping the two agents or assuming
generic reciprocity, omit the candidate.

In particular, evaluated_agent offering their own draft, file, testimony, or
truth is not by itself Environment disclosure_willingness. Evaluated_agent
asking Environment for an account or record is not Environment
evidence_seeking. Evaluated_agent investigating, withdrawing, or asserting a
boundary is not the matching Environment disposition. These events may affect
another Environment state only when that state has its own valid causal bridge.
No behavioral candidate is required.

Expose at most one candidate from emotion, behavioral_disposition, and
consequence_risk. You may expose at most two relationship candidates only
when they are different variables and each independently supports its own
construct. One exact span may support multiple candidates only when it has
genuinely different, variable-specific causal consequences for Environment;
do not clone a generic cooperative, respectful, or adverse signal across
loosely related states. Do not prefer a turn-responsive relationship variable
over a slow one merely because it can update faster; assess each supported
construct independently. Python may apply at most one relationship update and
at most two cross-family impacts per ordinary turn; these are ceilings, not
targets.

Do not infer one state from another. Anxiety is not uncertainty, cooperation
is not trust, acknowledgment is not fairness, and a promise is not verified
performance. Deep relational variables such as trust need verified conduct
or a new strong direct relational event, not a pleasant tone or another
promise. Turn-responsive variables may react to a newly performed act.

Repeated reasons, positions, promises, or stylistic paraphrases are not new
evidence. A newly occurring act can be new evidence, but routine reinforcement
must not be used to push an already high or low state toward an endpoint.
At 0 or 10 never propose a further outward change. A direction reversal needs
fresh contrary evidence; do not add automatic decay or forced oscillation.

## Semantic events

Every ledger_events item has exactly event_type, owner, action_owner,
evidence_span, status, and assertion_mode. The span is a verbatim latest
utterance substring and owner is evaluated_agent.

Allowed event types/statuses: proposal open|tentative; commitment
firm|conditional; payment reported_complete; request open; pause explicit;
claim reported. action_owner is evaluated_agent, environment_agent,
collective, or unspecified.

assertion_mode is asserted, negated, hypothetical, quoted, or definitional.
Only a current undertaking to perform a future action is a commitment. A
reported past act is not verified merely because it sounds plausible. Python
records only asserted semantic events.

ledger_resolutions contains dispositions of supplied active proposals. Each
item has exactly target_id, resolution (accepted, rejected, or countered),
and an exact evidence_span. Output [] when no active proposal is resolved.

## Dialogue diagnostics

substantive_novelty.label is one of new_explanation, new_position,
new_tradeoff, new_evidence, new_decision, necessary_confirmation, none.
A paraphrase, repeated deadline, bare acknowledgment, or repeated promise
is none.

For consequential assertions affecting responsibility, rights, action
feasibility, or a task answer, return an exact span and grounding:
observable_fact, speaker_report, proposal_or_hypothetical,
unsupported_assertion, or uncertain.

continuation.status is must_answer, continue, or can_close. State what would
remain after a direct response. Do not invent unresolved issues merely to
extend the trajectory.

Return exactly one compact JSON object:

{"appraisal":{"speaker_intent":"...","social_act":"request","event_features":{"goal_alignment":0,"cooperation_signal":0,"repair_signal":0,"pressure":0,"face_threat":0,"commitment_signal":0,"uncertainty_reduction":0,"boundary_violation":0,"respect_signal":0,"withdrawal_signal":0},"state_impacts":[],"dynamics_impacts":[],"ledger_events":[],"ledger_resolutions":[],"dialogue_diagnostics":{"substantive_novelty":{"label":"new_position","evidence_span":"exact substring"},"consequential_claims":[],"continuation":{"status":"must_answer","evidence_span":"exact substring","after_direct_response":{"status":"can_close","evidence_span":"exact substring","resolved_live_questions":[],"remaining_live_questions":[]}}}},"evidence_turn_ids":[]}

Private appraisal request:
{{payload_json}}

Exact latest action:
{{latest_action_text}}
