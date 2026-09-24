# SocialFlux T3 Candidate Action Authoring v1

Author free-form candidate actions for the evaluated agent at one shared public checkpoint.

Every candidate must directly respond to the latest observable context, be executable immediately at that point, and use a materially distinct strategy. Clarification, bounded proposals, refusal, delay, and relationship repair are allowed. Do not create near-synonyms that differ only in politeness. Do not invent institutions, authority, decisive facts, completed actions, the other character's action, latent state, or future events.

Return exactly {{candidate_count}} candidates. Each text must contain one to three natural direct-utterance sentences.

Return JSON only, with exactly this structure and no additional keys:

{{output_schema_json}}

Public checkpoint:

{{payload_json}}
