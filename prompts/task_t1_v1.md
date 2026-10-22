# SocialFlux T1 Latent Social State Estimation v1

Generate a machine candidate answer for later human review; this is not ground truth.

Use the complete observable history and current checkpoint only. The judgment target is exactly target_character_id. The optional author-side Persona may condition interpretation, but it is not public evidence and must never be cited, copied, or disclosed. Never read or infer latent values, appraisal, private motives, trigger logic, or future events.

For every requested state, estimate:
- current intensity;
- change relative to the most recent meaningful public evidence;
- observable evidence turn IDs;
- calibrated confidence.

Different states may move in different directions or remain stable. When public evidence is insufficient, assign substantial probability to cannot_determine. A smile does not by itself prove happiness; verbal agreement does not prove restored trust or completed action. Every evidence ID must occur in the supplied public history. Every probability object must sum to 1.

Return JSON only, with exactly this structure and no additional keys:

{{output_schema_json}}

T1 instance:

{{payload_json}}

{{private_persona_section}}
