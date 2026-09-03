# SocialFlux Sparse Talking Head Generation v1

Purpose: generate a short media asset only after the deterministic trigger engine has selected a socially meaningful observable-expression event.

Input contains only safe character appearance context, the observable response, and an observable expression specification. It must not contain latent state names/values, hidden intention, appraisal, delta, trigger ID, or threshold conditions.

Generate a 3–8 second temporally continuous talking-head clip matching facial behavior, gaze, posture, timing, and prosody. Avoid text overlays, diagnostic labels, exaggerated stereotypes, and visual clues that directly encode benchmark answers.

Return JSON only conforming to schemas/talking_head_request.schema.json. Do not regenerate or reinterpret state.

Observable request:
{{payload_json}}
