# SocialFlux Existing Scenario Revision v1

Revise one existing fictional SocialFlux scenario for natural interaction. This
is a scenario-design call, not a rollout and not a task-answer call.

Preserve every field listed in `immutable_fields`: identity, source provenance,
state ontology, target IDs, numeric S0/D0, and the maximum 20-turn budget. Return
only a patch for the explicitly requested narrative fields. Do not invent a new
metric, institution, legal right, contract power, or guaranteed outcome.

The scenario should naturally support a substantive interaction, usually 10–20
turns, through genuine differences in history interpretation, goals, trade-offs,
private concerns, and feasible choices. Do not extend it through repeated
confirmation, a fixed question/answer rhythm, or a generic
dispute→evidence→decision template. A coherent shorter ending remains allowed
and must not be padded.

Reasonable fictional completion is allowed when it makes the social situation
specific and remains compatible with provenance. Clearly separate:

- public facts already established;
- one participant's unverified report;
- a proposal or conditional commitment;
- an externally verifiable result that needs a later public event.

`relevant_history` must contain 3–8 scenario-specific facts, including one concise
entry beginning with `事实边界：`. `meaningful_choice_space` must contain 3–6
choices specific to these characters; do not use generic phrases such as “核对事实”
or “继续、暂停、退出” without saying what concrete choice is at stake.

The outward goal and hidden intention may conflict without making the character a
liar. Give both characters natural names and precise roles. `opening_response`
must be one plausible opening line from the environment character; it cannot
announce hidden information or dictate a resolution.

The `environment_agent` is the evaluated character's only conversational
counterparty in the rollout. Do not make a coordinator speak for another party,
do not put an additional disputant "on the line", and do not design dialogue
that requires the environment response to alternate among several speakers.
Third parties may appear only through already-authored public records or later
public events. If the original scenario confuses these roles, replace its
content with a two-person interaction while preserving the immutable fields.

Use `longitudinal_design: null` when the situation has no independently grounded
reason to reconnect. If time-separated interaction is genuinely needed, provide
2–3 variable segments using the existing `socialflux_longitudinal_v1` schema:

- segment `max_turns` values sum to 20, but no segment must consume its budget;
- each later segment has a scenario-specific elapsed time, public time record,
  and opening reason already supported by the scenario;
- time passing never proves fulfillment;
- an event pool may report only a result whose source and possible outcomes are
  defined here; use empty state/dynamics deltas;
- do not add a generic review/decision node merely to fill remaining turns;
- align time with the actual deadline or evidence opportunity in the scenario.

Return exactly this JSON shape:

```json
{
  "format": "socialflux_scenario_revision_v1",
  "scenario_id": "unchanged",
  "decision": "revise",
  "diagnosis": "specific reason the old content was weak",
  "estimated_natural_turn_range": [10, 16],
  "task_potential": {"T1": "strong", "T2": "strong", "T3": "usable", "T4": "strong"},
  "patch": {
    "title": "...",
    "mechanism": "...",
    "background": "...",
    "narrative_design": {
      "relationship_structure": "...",
      "power_structure": "...",
      "goal_conflict": "...",
      "information_asymmetry": "...",
      "relevant_history": ["...", "...", "事实边界：..."],
      "meaningful_choice_space": ["...", "...", "..."]
    },
    "environment_agent": {
      "persona": {"name": "...", "role": "...", "patience": 0.5, "empathy": 0.5},
      "explicit_goal": "...",
      "hidden_intention": "..."
    },
    "evaluated_agent_role": {
      "character_id": "unchanged",
      "name": "...",
      "role": "...",
      "explicit_goal": "..."
    },
    "opening_response": "...",
    "longitudinal_design": null
  }
}
```

Use `replace_content` instead of `revise` only when the original conflict cannot
support meaningful choices without a substantially new fictional situation.

Input:
{{payload_json}}
