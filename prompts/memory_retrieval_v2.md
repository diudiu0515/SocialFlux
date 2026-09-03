# SocialFlux Observable Memory Retrieval v2

Purpose: select and summarize observable prior interaction events that materially affect interpretation of the latest free-form action. Full raw history remains authoritative; this is only a retrieval layer.

Evaluated-history inputs: observable dialogue history, latest action, and maximum event count.

Constraints:

- access only supplied observable history;
- do not infer hidden state as fact;
- do not access or mention hidden intention, appraisal, state delta, trigger rules, author metadata, or future trajectory;
- preserve turn IDs exactly;
- distinguish unresolved observable events from speculative motives;
- internally verify every selected ID exists and no future turn is selected.

Return JSON only with exactly:

{"relevant_turn_ids": ["t1"], "memory_summary": "...", "important_unresolved_events": ["..."]}

Request:
{{payload_json}}
