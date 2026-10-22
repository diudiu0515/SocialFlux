# SocialFlux State-Layer Machine Semantic Audit v1

Audit one model-authored candidate state layer before human review. This is
optional model-generated reviewer triage, not a release gate or automated
ground truth. It must never claim human approval, replace human judgment, or
change a value. Report only clear violations supported by the frozen scenario
and ontology; do not manufacture issues from mere ambiguity.

Return JSON only with exactly these top-level keys:

decision, issues

decision is "pass" only when issues is empty; otherwise it is "revise".
Each issue has exactly path, field, code, and reason. field is one of
selection, initial_state, rationale, increase_evidence, decrease_evidence, or
video_trigger. code is one of:

- owner_inversion
- relationship_direction_inversion
- risk_bearer_inversion
- factual_role_inversion
- construct_mismatch
- direction_mismatch
- post_update_evidence
- unreachable_evidence
- redundant_construct
- correlated_state_reasoning
- trigger_semantic_mismatch

For a state issue, path must be exactly one selected family.variable such as
"emotion.guilt"; never prefix it with candidate_state_layer,
transition_evidence_plan, initial_state, or a field name. For a trigger issue,
path must be exactly the trigger_id.

Inspect every selected variable, every S0 rationale, all increase/decrease
evidence leaves, and all three triggers against the supplied scenario and
ontology. In particular:

1. All state belongs to environment_agent. Behavioral disposition is that
   character's readiness, not the evaluated participant's readiness.
2. Relationship is the environment character's belief about the evaluated
   participant. role_legitimacy is not self-legitimacy; responsiveness is not
   the environment character responding; safety is not whether the evaluated
   participant is safe from the environment character.
3. Consequence risk must keep the declared environment-side goal, standing,
   autonomy, material position, safety, relationship, or institution as the
   risk bearer.
4. Do not swap who recruited, funded, supervised, promised, threatened,
   documented, observed, or decided anything in the frozen scenario.
5. Each plan leaf is a counterfactual for a possible later turn. Wording such
   as "B would state/report/offer" is valid: when B performs that act it becomes
   the current evaluated action before appraisal. Do not call it post-update
   merely because it is future relative to S0. Use post_update_evidence only
   when the proposed cause is an action by the environment character after the
   state update, or a consequence that can occur only after that response.
6. Increase and decrease must match the exact ontology anchors. Reject a route
   when the proposed cause more plausibly produces the opposite direction.
   Pressure or refusal does not decrease evidence-seeking unless it plausibly
   causes the environment character to stop checking.
7. The evidence must be reachable in this scenario without inventing a new
   institution, capability, relationship, or hidden fact.
8. Do not accept several constructs justified by one generic fact or by another
   state changing.
9. Trigger conditions and public expressions must refer to the intended
   environment-character state and remain semantically compatible.

Do not score style. Do not reject merely because state is stable or because a
planned change might not occur. Do not require forced change.
Use owner_inversion only when the state is assigned to the wrong character;
use construct_mismatch or direction_mismatch for weak or incorrect evidence
about a state that is still owned by the environment character.

Audit payload:
{{payload_json}}
