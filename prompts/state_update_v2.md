# SocialFlux Semantic State Update v2

Purpose: convert a completed appraisal into calibrated qualitative changes for only the scenario-selected latent state S_t and separate interaction dynamics D_t.

Author-side inputs: previous state, previous dynamics, completed appraisal, and relevant observable memory.

Constraints:

- base each change on the appraisal and relevant history, not on an action category, dramatic wording, or authored transition table;
- model one-turn inertia: `similar` and `mild_*` should be common; use `moderate_*` only for clear consequential evidence and `strong_*` only for rare acute, unambiguous, high-impact events;
- do not move every variable together merely because the turn is positive or negative; assess emotion, motivation, relationship, and dynamics independently;
- if a variable is already at 0 or 10, do not keep selecting a clipped outward delta without new evidence; use `similar` unless the turn supports reversal;
- distinguish temporary emotional reaction from slower trust, respect, openness, and control changes;
- output every existing variable exactly once and add no variables;
- persona/background/goals/hidden intention are stable context and cannot be modified;
- opposing variables are independent constructs, not forced mathematical complements;
- do not output new numeric state values;
- use only strong_decrease, moderate_decrease, mild_decrease, similar, mild_increase, moderate_increase, strong_increase;
- internally verify evidence, calibration, and exact shape equality with previous_state and previous_dynamics.

Return JSON only:

{"state_delta": {...}, "interaction_dynamics_delta": {...}}

Private request:
{{payload_json}}
