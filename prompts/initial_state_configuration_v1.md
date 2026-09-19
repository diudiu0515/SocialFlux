# SocialFlux Initial State Configuration v2

Purpose: propose candidate S0/D0 only after an approved v2 source has been normalized. Solve causal consistency first and serialize last.

Inputs include the private stable environment persona, background, goals, hidden intention, canonical selected state variables, and multimodal concepts. This is an author-side prompt; none of its private fields may enter the evaluated model's observation.

Constraints:

- require `state_contract_version=socialflux_state_v2`;
- initialize exactly `emotion`, `behavioral_disposition`, `relationship`, and `consequence_risk` using the selected approved variables on 0–10;
- persona traits remain stable context, never state;
- use 2–5 flat canonical external dynamics only: `deadline_pressure`, `resource_scarcity`, `information_asymmetry`, `public_exposure`, `negotiation_openness`, `coordination_stability`, `institutional_constraint`;
- do not duplicate external dynamics as consequence-risk state;
- values must follow from persona, background, goals, hidden intention, history, and initial situation;
- avoid unjustified extremes and preserve several plausible interaction paths; never copy a default state bundle or trigger pair across unrelated scenarios;
- no video trigger may already be active at S0/D0;
- set max_turns to 20 and t3_delayed_horizon to 5–10;
- create thresholds and observable-expression specifications, never action effects, answers, or a prescribed strategy;
- status is `candidate_pending_human_freeze`; a model cannot freeze its own proposal.

Return JSON only conforming to `schemas/initial_state_proposal.schema.json`.

Approved scenario blueprint:
{{payload_json}}
