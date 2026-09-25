Convert the following already-public dialogue response and observable behavior into natural English instructions for a continuous talking-head video.

Output JSON only with exactly this shape:
{
  "english_spoken_line": "...",
  "observable_expression": {
    "facial_expression": "...",
    "gaze": "...",
    "speech_style": "...",
    "prosody": "...",
    "behavioral_cues": ["...", "..."]
  }
}

Requirements:
- The spoken line must contain 3–32 English words.
- Preserve the speaker's stance, commitments, uncertainty, boundaries, and materially important public facts.
- Prefer concise, idiomatic speech over literal word order.
- Render every observable-expression field in concise, natural English.
- Keep at most two subtle, mutually compatible behavioral cues.
- Do not add facts, promises, certainty, diagnoses, private state, hidden intentions, scores, or benchmark language.
- Do not mention translation or adaptation.
- Do not include subtitles, labels, quoted dialogue, or private explanations.

Public rendering payload:
{{payload_json}}
