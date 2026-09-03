# SocialFlux Initial State Configuration v1

Purpose: propose candidate S0/D0 only after an approved source has been normalized into a scenario blueprint. Solve causal consistency first; serialize last.

Inputs: approved normalized persona, background, goals, hidden intention, selected state variables, dynamics concepts, and multimodal event concepts.

Constraints:

- initialize only selected variables on the 0–10 scale;
- persona traits remain stable context, never state;
- values must follow from persona + background + goals + hidden intention + initial situation;
- avoid unjustified extremes and leave room for multiple natural trajectories;
- no video trigger may already be active at S0/D0;
- plausible free interaction within the horizon must be able to reach salient trigger regions;
- create thresholds and observable-expression specifications, never action effects or a prescribed strategy;
- media is sparse: ordinary turns are text, selected threshold/crossing/state-change events emit safe observable media specifications;
- status must be candidate_pending_human_freeze. A model cannot freeze its own proposal.

Return JSON only conforming to schemas/initial_state_proposal.schema.json with exactly: initial_state, initial_dynamics, observable_expression, media_generation, video_triggers, max_turns, t3_delayed_horizon, sampling_plan, rationale, trigger_reachability, status.

Approved scenario blueprint:
{{payload_json}}
