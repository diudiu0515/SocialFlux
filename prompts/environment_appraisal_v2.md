# SocialFlux Persona-Conditioned Appraisal v2

Purpose: privately interpret one exact free-form evaluated-agent action in its longitudinal social context. Complete the social interpretation first; serialization is only the output format.

Author-side inputs:

- stable persona, background, explicit goal, and hidden intention;
- observable relevant history;
- previous selected latent state and interaction dynamics;
- latest arbitrary natural-language action.

Reasoning constraints:

- infer what the other party is trying to achieve;
- assess effects on the explicit goal and hidden intention;
- explain how persona and specific historical events change the action's meaning;
- support same action + different history and same action + different persona producing different appraisals;
- never classify into repair, neutral, escalation, or another fixed taxonomy;
- never use keywords as a transition lookup;
- do not update state, dynamics, persona, goals, or history in this step;
- internally check that every evidence turn exists in supplied history.

Return JSON only:

{"appraisal": {"other_party_intent": "...", "explicit_goal_effect": "...", "hidden_intention_effect": "...", "persona_conditioned_interpretation": "...", "history_conditioned_interpretation": "..."}, "evidence_turn_ids": ["t1"]}

Private request:
{{payload_json}}
