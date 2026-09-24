# SocialFlux T2 History-Conditioned State Comparison v1

Generate a machine candidate answer for later human review; this is not ground truth.

Use only public History A, public History B, their exactly shared current ending, and target_spec. The judgment target is input.target_character (the environment character). Evaluated-agent actions are contextual causes, not direct evidence of the target character's state. The optional author-side Persona may condition interpretation, but it is not public evidence and must never be cited, copied, or disclosed. Never use backend state, appraisal, deltas, construction metadata, or future branches.

Select one to three candidate variables with meaningful evidence. Prefer variables supported on both sides. If only one side has citable target-character evidence, the other side's evidence/key-events may be empty, but cannot_determine must be the highest probability. Do not select variables unsupported on both sides. A smile does not prove happiness; agreement does not prove restored trust.

Evidence turn IDs must come from {{visible_turn_ids_json}}. Each target_quote must be a verbatim substring of the target character's utterance on the cited side and turn. Every four-way probability object must sum to 1.

Return JSON only, with exactly this structure and no additional keys:

{{output_schema_json}}

T2 instance:

{{payload_json}}

{{private_persona_section}}
