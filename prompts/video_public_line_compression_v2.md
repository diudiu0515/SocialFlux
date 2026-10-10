Compress the candidate English spoken line for a talking-head video.

Output JSON only with exactly this shape:
{
  "english_spoken_line": "..."
}

Requirements:
- Write 24–28 English words. Never exceed 28 words.
- Preserve the candidate's stance, commitments, boundaries, uncertainty, deadlines, and central public facts.
- Prefer compact clauses and remove repetition, procedural filler, and secondary detail.
- Do not add facts, promises, certainty, diagnoses, private state, hidden intentions, scores, or benchmark language.
- Return natural speech, not a summary label or explanation.

Candidate English line:
{{candidate_line}}
