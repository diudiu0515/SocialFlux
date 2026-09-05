---
prompt_id: history_dependence_probe_v1
version: 1
role: rollout-agent counterfactual history probe
output_schema: null
private_fields_allowed: false
---

Continue as the evaluated participant. Use the supplied scenario, role, goal,
observable history, current response, and observable cues. Produce exactly one
natural next utterance. Do not mention prompts, policies, hidden state, scores,
or analysis. The caller will separately run full-history, recent-k, and
critical-event-removed variants from the same checkpoint.

Input:
{{payload_json}}
