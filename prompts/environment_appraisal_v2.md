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
- isolate the newest action's incremental effect from the pre-existing baseline: old conflict or pressure may shape interpretation but is not a new injury on every turn;
- distinguish a delivered result or verifiable new information from a promise, repetition, evasion, threat, accusation, concession, boundary, or concrete proposal; describe the evidence in plain social terms rather than as a category label;
- do not interpret respectful firmness as hostility unless the exact wording or history supplies a fresh threat, insult, deception, coercion, or meaningful loss of control;
- support same action + different history and same action + different persona producing different appraisals;
- never classify into repair, neutral, escalation, or another fixed taxonomy;
- never use keywords as a transition lookup;
- do not update state, dynamics, persona, goals, or history in this step;
- internally check that every evidence turn exists in supplied history;
- set evidence_turn_ids to 0–4 unique IDs copied exactly from memory.relevant_turn_ids; use [] when that list is empty, and never enumerate or invent IDs;
- keep each appraisal field concise and close the JSON object immediately after evidence_turn_ids.

Return one compact JSON object only, with no Markdown fence or trailing text:

{"appraisal": {"other_party_intent": "...", "explicit_goal_effect": "...", "hidden_intention_effect": "...", "persona_conditioned_interpretation": "...", "history_conditioned_interpretation": "..."}, "evidence_turn_ids": []}

Private request:
{{payload_json}}
