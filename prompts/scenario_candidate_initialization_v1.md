# SocialFlux Direct Scenario Candidate Initialization v2

Purpose: propose candidate S0/D0 and observable media triggers for a v2 blueprint before human Gate 1. The model cannot freeze or approve its proposal.

Constraints:

- require `state_contract_version=socialflux_state_v2`;
- initialize exactly the selected variables under the four families `emotion`, `behavioral_disposition`, `relationship`, and `consequence_risk` on the 0–10 scale;
- treat persona, role, explicit goal, and hidden intention as stable private context, never mutable state;
- use 2–5 flat canonical dynamics only: `deadline_pressure`, `resource_scarcity`, `information_asymmetry`, `public_exposure`, `negotiation_openness`, `coordination_stability`, `institutional_constraint`;
- external dynamics and the character's consequence-risk state must not duplicate each other;
- derive every value from persona, history, goals, hidden intention, and the opening situation while preserving multiple plausible trajectories;
- define exactly three distinct video triggers with unique positive priorities; no trigger may already be active at S0/D0;
- every trigger references only existing numeric state/dynamics paths, uses cooldown 2–4, and includes observable expression;
- set max_turns to 20 and t3_delayed_horizon to 5–10;
- do not create action taxonomies, action effects, response templates, best strategies, expected deltas, answers, or trajectories;
- set status to `candidate_pending_human_freeze`.

Return JSON only with exactly: initial_state, initial_dynamics, observable_expression, media_generation, video_triggers, max_turns, t3_delayed_horizon, sampling_plan, rationale, trigger_reachability, status.

Candidate blueprint:
{{payload_json}}
