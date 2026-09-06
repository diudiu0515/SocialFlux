# SocialFlux Semantic State Update v2

Purpose: convert a completed appraisal into calibrated qualitative changes for only the scenario-selected latent state S_t and separate interaction dynamics D_t.

Author-side inputs: previous state, previous dynamics, completed appraisal, and relevant observable memory.

Constraints:

- base each change on the appraisal and relevant history, not on an action category, dramatic wording, or authored transition table;
- each delta is the incremental effect of the newest action relative to the previous state, not a summary of the scene's absolute mood; do not re-apply an old conflict, risk, or power imbalance when the newest turn adds no new evidence;
- model one-turn inertia: `similar` and `mild_*` should be common; use `moderate_*` only for clear consequential evidence and `strong_*` only for rare acute, unambiguous, high-impact events;
- when the appraisal says the newest action delivers a concrete result, verifiable information, or workable cooperation and identifies no fresh threat, deception, evasion, or broken commitment, anger/anxiety/hostility should not increase and trust should not decrease merely because prior history was difficult;
- a respectful firm boundary is not by itself hostility; only move threat-sensitive variables negatively when the appraisal identifies fresh socially harmful evidence;
- do not move every variable together merely because the turn is positive or negative; assess emotion, motivation, relationship, and dynamics independently;
- if a variable is already at 0 or 10, do not keep selecting a clipped outward delta without new evidence; use `similar` unless the turn supports reversal;
- distinguish temporary emotional reaction from slower trust, respect, openness, and control changes;
- output every existing variable exactly once and add no variables;
- persona/background/goals/hidden intention are stable context and cannot be modified;
- opposing variables are independent constructs, not forced mathematical complements;
- do not output numeric state values or numeric deltas;
- every leaf in both delta objects must be exactly one string from: `strong_decrease`, `moderate_decrease`, `mild_decrease`, `similar`, `mild_increase`, `moderate_increase`, `strong_increase`; values such as `-2`, `0`, or `1` are invalid;
- internally verify evidence, calibration, and exact shape equality with previous_state and previous_dynamics.

Return one compact JSON object only, with no Markdown fence or trailing text:

{"state_delta": {...}, "interaction_dynamics_delta": {...}}

Private request:
{{payload_json}}
