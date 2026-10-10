# SocialFlux State-Layer Reauthoring v1

Reauthor only the mutable state layer of the supplied frozen scenario. Keep
the public situation, both roles, both personas, goals, history, choice space,
and external dynamics unchanged. This output is model-authored and remains
pending human review.

The mutable state belongs exclusively to the supplied environment_agent.
Never initialize or describe the evaluated_agent's feelings, intentions,
relationship beliefs, action readiness, or risk assessment. Every rationale
must begin with the environment character's exact name.

Return exactly these seven top-level keys:

ontology_version, selected_state_variables, target_state_ids, initial_state,
rationale, transition_evidence_plan, video_triggers

Set ontology_version to socialflux_state_ontology_v3.

selected_state_variables uses exactly the four families emotion,
behavioral_disposition, relationship, and consequence_risk, with 9-13 total
variables and normally 10-11. Select 3-4 emotion variables, 2-3 behavioral
variables, 2-3 relationship variables, and 2-3 consequence-risk variables.
Every family list contains leaf names only: use "anxiety", never
"emotion.anxiety"; use "perceived_responsiveness", never
"relationship.perceived_responsiveness". In contrast, target_state_ids and
transition_evidence_plan keys use complete family.variable paths.

Use only the supplied approved ontology. Choose variables that distinguish
plausible paths in this specific 20-turn interaction. Do not default to
anxiety, trust, cooperation, or goal-failure risk. Select trust only when
verified follow-through, costly honesty, or dependable conduct can become
publicly observable within the scenario. For turn-level acknowledgment or
evasion, prefer perceived_responsiveness rather than deep trust.
Select guilt only when the frozen scenario gives the environment character a
specific preventable action, omission, accepted duty, or acknowledged
responsibility for harm. Procedural involvement, a difficult allocation, or an
evaluated participant's disappointment alone is not guilt evidence.

Do not select redundant or inverse proxies merely to fill eight slots.
Emotion is current affect; behavioral disposition is current action readiness;
relationship is the environment character's belief about the other party;
consequence risk is the environment character's assessment of a concrete
downstream harm.

All four families describe the environment character:

- emotion is what the environment character currently feels, never what the
  evaluated participant feels;
- behavioral_disposition is what the environment character is currently ready
  to do, never what the evaluated participant is ready to do;
- relationship is what the environment character believes about the evaluated
  participant, never the reverse relationship and never the environment
  character's belief about themself;
- consequence_risk is the environment character's assessment of harm to the
  environment character's goal, standing, autonomy, material position, safety,
  relationship, or relevant institution. Do not silently switch the person at
  risk to the evaluated participant.

For every relationship variable, the "other party" is the evaluated
participant, never the environment character. For example, environment
character A's relationship.role_legitimacy means A's belief that evaluated
participant B is exercising B's role appropriately; it never means A's belief
that A's own authority is legitimate. Do not select role_legitimacy merely
because A's own power is salient. perceived_responsiveness asks whether B
addresses A's concerns, not whether A addresses B's concerns. perceived_safety
asks whether A experiences engagement with B as safe, not whether B is safe
from A. A documentation preference alone is not role legitimacy unless it
shows B using or exceeding B's actual role, authority, or mandate.

target_state_ids contains 6-9 unique selected paths and covers all four
families. A target must have both a plausible increase route and a plausible
decrease route in this scenario.

initial_state exactly mirrors the selected family-variable shape. Values are
numeric in [1, 9]. Use varied, grounded starting values and leave room in both
directions. Do not derive several values from one generic fact and do not make
all dimensions share the same initial level.

rationale exactly mirrors initial_state. Every leaf is concise and begins
exactly "<environment complete name>'s <family.variable> is initialized at
<value> because ". The value must match initial_state. For relationship leaves,
continue exactly "<environment complete name> believes <evaluated complete
name> ..." and describe the evaluated participant's conduct toward the
environment character. For behavioral_disposition leaves, explain what the
environment character is ready to do. For consequence_risk leaves, identify
the environment character's own exposed goal, standing, autonomy, material
position, safety, relationship, or relevant institution. Names must be copied
verbatim; a title plus surname or abbreviation is invalid. Every leaf must use
distinct scenario facts without prescribing a preferred evaluated-agent
action.

transition_evidence_plan has exactly one key for every selected
family.variable path, including selected paths absent from target_state_ids,
and no other keys. Its key count must equal the total number of selected
variables. Every path maps to exactly increase_evidence and decrease_evidence.
Each evidence value describes exactly one route and must use this exact causal
form: "<evaluated complete name> would <one concrete action>, causing
<environment complete name>'s <family.variable> to <increase|decrease> because
<construct-specific reason about the environment character>." The action must
be a scenario-reachable statement, report, offer, refusal, commitment, or
supplied fact from the evaluated participant. The because-clause must explain
why that action changes that exact construct for the environment character.
This is causal evidence about the environment character's state, never a
description of the evaluated participant having the same-named emotion,
disposition, relationship belief, or risk. Evidence must be available before
the appraisal and state update.
The direction must match the supplied ontology anchors, not merely the surface
polarity of the evaluated action. Refusal, pressure, or missing evidence often
increases the environment character's evidence-seeking rather than decreasing
it. A decrease in evidence-seeking requires a plausible cause for the
environment character to accept without verification or explicitly stop
checking. Apply the same causal-direction test to every construct.
Never use an action that the environment character would perform only after
the update as evidence for that update. External events count only when the
evaluated participant reports or supplies them in the action being appraised.
It is an audit plan, not an instruction to make the event occur. Generic tone,
repetition, and another state changing are invalid evidence.
Across variables, do not reuse one generic proposal, disclosure, refusal, or
respect signal as the cause for several changes. If one event could affect two
variables, each plan must identify a genuinely independent aspect and a
construct-specific causal route; otherwise keep only the better-matched path.

video_triggers contains exactly three metadata triggers for observable
expressions by the environment character. This does not request or generate
video. Each trigger contains trigger_id, trigger_mode, conditions, priority,
cooldown_turns, cue_template, and observable_expression. observable_expression
must be a non-empty JSON object, preferably exactly {"cue":"one concise public
behavior"}; a bare string is invalid. trigger_mode is threshold, crossing, or
state_change. Conditions map an exact selected state path or supplied
initial_dynamics path to exactly {"operator":">=","threshold":7}, using an
operator from >=, >, <=, <, == and a numeric threshold. A state_change trigger
also contains non-empty change_conditions in that same path-to-condition
shape; {"direction":"decrease","magnitude":1} is invalid. A state_change
trigger may use an empty conditions object. Threshold/crossing conditions must
be inactive initially. Compare each condition against the matching S0 value
before returning: if anxiety starts at 7, a >=7 threshold is invalid while a
>=8 threshold can be initially inactive. Priorities are unique positive
integers and cooldown_turns is 2-4.
Each trigger's public expression must visibly fit its construct: frustration
must show obstruction-related irritation rather than generic checking;
evidence-seeking must show verification behavior rather than generic tension.

Avoid convergence: routine repeated cooperation, respect, pressure, or promises
must not make several variables move together. Avoid non-transition: at least
one selected variable in every family must have distinct, concrete, observable
evidence that could plausibly arise on both sides during the 20-turn
interaction. Do not force any state to change.

Before returning, verify all of the following: family lists use leaf names;
target and evidence-plan keys use full paths; every relationship rationale
contains the exact required "<environment> believes <evaluated>" clause; the
evidence-plan keyset equals every selected path; all evidence uses the causal
form and the environment character as state owner; all threshold or crossing
triggers are inactive at S0; observable_expression is a non-empty object; each
increase and decrease matches that variable's supplied ontology anchors and is
more plausible than the opposite direction.

Return JSON only.

Frozen scenario and approved ontology:
{{payload_json}}
