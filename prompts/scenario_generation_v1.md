# SocialFlux Stateful Scenario Generation Prompt v1

You design one canonical SocialFlux pipeline scenario. Return one strict JSON object that validates against `schemas/scenario.schema.json`; do not wrap it in Markdown and do not invent a separately maintained prose specification.

The JSON must define:

- a concrete social conflict with a real trade-off and a named social mechanism;
- environment persona, explicit goal, private hidden intention, and evaluated-agent role;
- scenario-selected state variables, target state IDs, frozen initial state S0, and initial dynamics D0 on the 0–10 scale;
- repair, neutral, and escalation action effects using the seven legal semantic delta labels;
- observable cues and response templates;
- default observable expression and `media_generation`;
- scenario-specific video triggers with mode, AND-combined conditions, numeric thresholds, cooldown, 3–8 second duration, cue template, and observable expression;
- max turns, T3 delayed horizon, and T1/T2/T3 sampling plan.

Design rules:

1. State variables must be operationally interpretable and relevant to this conflict.
2. Action branches must create meaningful but plausible directional divergence.
3. Persona changes appraisal magnitude without serving as a second mutable state.
4. Trigger thresholds must represent salient state events; prefer `crossing` for one-time transitions and document all variables needed for the event.
5. Trigger `conditions` use AND semantics. Avoid thresholds that fire immediately from S0 or cannot be reached within the configured horizon.
6. Observable expression may reveal behavior but not private state names, values, hidden intention, trigger IDs, or threshold logic to the evaluated model.
7. Do not claim simulator state is psychological ground truth.

After saving the JSON as `configs/scenarios/scenario_NNN.json`, the repository workflow MUST run:

```bash
python scripts/scenario_docs.py configs/scenarios/scenario_NNN.json
python scripts/scenario_docs.py --check
```

This creates `scenario_NNN.md` from the JSON, records the source SHA-256, explains initialization/state/action/video thresholds in natural language, and rebuilds the scenario manifest. The generated Markdown is a human-review projection; JSON remains canonical.

Request payload:
{{payload_json}}
