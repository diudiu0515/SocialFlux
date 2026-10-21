# Environment Paraphrase Probe v2

Rewrite only `latest_action` in the SAME LANGUAGE as the original action.
Do not translate. Preserve the speaker, social intent, commitments, requests,
facts, politeness, urgency, negation, conditions, and intensity. Change wording
and syntax without adding, removing, strengthening, or weakening claims.
Context explains meaning; do not import context into the rewritten action.
Do not answer the action or continue the dialogue.

The supplied strict_surface_constraints remain mandatory: preserve the exact
semantic_numbers_exact sequence, retain at least one marker from each required
group, introduce none from forbidden groups, and preserve question_force.
Return a distinct rewording, without a speaker label or commentary.

Return exactly {"paraphrase":"one single-speaker turn"}.

{{payload_json}}
