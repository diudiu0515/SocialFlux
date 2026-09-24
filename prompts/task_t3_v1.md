# SocialFlux T3 Counterfactual State Transition Prediction v1

Generate a machine candidate answer for later human review; this is not ground truth.

All candidate actions branch from the same public checkpoint. Use only public history, current observation, the candidate actions, and the common horizon to predict each action's immediate and delayed effects on the target character's requested states. The optional author-side Persona may condition interpretation, but it is not public evidence and must never be cited, copied, or disclosed.

The main task contains no latent state. Do not infer other private information, introduce branch-specific external events, or treat a promised action as completed. {{condition_instruction}}

Different actions may have similar effects, but do not mechanically copy one distribution across all actions and states. Delayed predictions must respect the shared continuation protocol and frozen event plan. Raise cannot_determine when support is weak. Evidence IDs may cite only real public input turns, never invented post-action futures. Every probability object must sum to 1.

Return JSON only, with exactly this structure and no additional keys:

{{output_schema_json}}

T3 instance:

{{payload_json}}

{{private_persona_section}}
