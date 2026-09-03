# SocialFlux Semantic State Update v1

Purpose: convert a completed appraisal into qualitative changes for only the scenario-selected latent state S_t and separate interaction dynamics D_t.

Author-side inputs: previous state, previous dynamics, completed appraisal, and relevant observable memory.

Constraints:

- base changes on the appraisal and relevant history, not on an action category or authored transition table;
- output every existing variable exactly once and add no variables;
- persona/background/goals/hidden intention are stable context and cannot be modified;
- opposing variables are independent constructs, not forced mathematical complements;
- do not output new numeric state values;
- use only strong_decrease, moderate_decrease, mild_decrease, similar, mild_increase, moderate_increase, strong_increase;
- internally verify shape equality with previous_state and previous_dynamics.

Return JSON only:

{"state_delta": {...}, "interaction_dynamics_delta": {...}}

Private request:
{{payload_json}}
