# SocialFlux T2 Shared Observation Construction v2

Given two naturally evolved, behaviorally divergent public histories from the same scenario, write one exact current environment observation that is semantically compatible with both histories while not revealing which latent state is higher.

Identity lock:

- The sole speaker in `current_response` is the explicitly supplied top-level `target_character`.
- The recipient is the explicitly supplied top-level `evaluated_character`.
- Begin in the target character's voice, normally addressing the evaluated character by their name/role. Never begin by addressing the target character's own name, surname+title, or role.
- Never write the evaluated character's proposed action, never address the target character by the target's own name/role, and never swap speakers.

Compatibility constraints:

- continue both histories by only one locally possible turn;
- introduce no new event, elapsed-time claim, document, decision, or fact that is unsupported by both histories;
- do not copy one history's latest response or assume that one path happened;
- keep `current_response` to 1–3 concise natural sentences with no stage directions or analysis;
- observable cues/expression may only contain safe public behavior and must be compatible with both histories;
- do not reveal private state, appraisal, hidden intention, trajectory IDs, source history, or which state is higher.

Return JSON only with exactly `current_response`, `observable_cues`, `observable_expression`, and `media`.

Histories:
{{payload_json}}
