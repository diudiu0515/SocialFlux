# SocialFlux Direct Scenario Candidate Initialization v1

Purpose: propose candidate S0/D0 and observable media triggers for a newly
normalized scenario blueprint before human Gate 1. The model must never freeze
or approve its own proposal.

Constraints:

- initialize only the blueprint's selected state variables on the 0–10 scale;
- derive every value from the scenario's persona, history, goals, hidden
  intention, and opening situation;
- keep persona traits as stable context rather than mutable state;
- use scenario-specific initial dynamics and leave room for multiple natural
  trajectories;
- define exactly three distinct video triggers with unique positive priorities;
- no threshold or crossing trigger may already be active at S0/D0;
- every trigger may reference only numeric paths present in initial state or
  initial dynamics, use cooldown 2–4, and include observable expression;
- set max_turns to exactly 20 and t3_delayed_horizon to 5–10;
- do not create action taxonomies, action effects, response templates, best
  strategies, expected deltas, answers, or trajectories;
- set status to `candidate_pending_human_freeze`.

Return JSON only with exactly: initial_state, initial_dynamics,
observable_expression, media_generation, video_triggers, max_turns,
t3_delayed_horizon, sampling_plan, rationale, trigger_reachability, status. It
must conform to `schemas/initial_state_proposal.schema.json` and the canonical
scenario validator.

Candidate blueprint:
{{payload_json}}
