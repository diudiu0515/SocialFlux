# SocialFlux T4 Terminal Judge v2

Evaluate only the supplied **completed observable trajectory**. A valid episode may end naturally before turn 20 or stop at the 20-turn maximum; never treat a natural short ending as missing turns, and never treat a maximum-horizon cutoff as a natural resolution. Score the evaluated participant relative to their public role and explicit goal, the scenario trade-off, and observable adaptation across the whole trajectory. Low conflict is not automatically good.

Use exactly these five dimensions:

- goal_achievement
- state_adaptation
- risk_management
- recovery
- relationship_outcome

For each dimension, return a 0–10 score, 1–3 valid evidence IDs from t1 through t20, a concise rationale, an uncertainty statement, and insufficient_evidence. Recovery may use score null only when no deterioration or repair opportunity occurred; then insufficient_evidence must be true. This automatic judgment is not human ground truth.

Return JSON only, with exactly this structure and no extra keys:

{
  "dimensions": {
    "goal_achievement": {"score": 0, "evidence_turn_ids": ["t1"], "rationale": "...", "uncertainty": "...", "insufficient_evidence": false},
    "state_adaptation": {"score": 0, "evidence_turn_ids": ["t1"], "rationale": "...", "uncertainty": "...", "insufficient_evidence": false},
    "risk_management": {"score": 0, "evidence_turn_ids": ["t1"], "rationale": "...", "uncertainty": "...", "insufficient_evidence": false},
    "recovery": {"score": 0, "evidence_turn_ids": ["t1"], "rationale": "...", "uncertainty": "...", "insufficient_evidence": false},
    "relationship_outcome": {"score": 0, "evidence_turn_ids": ["t1"], "rationale": "...", "uncertainty": "...", "insufficient_evidence": false}
  },
  "overall_uncertainty": "...",
  "human_validation_status": "not_human_validated"
}

Judge packet:
{{payload_json}}
