"""Human-readable artifact writers shared by rollout and task stages."""

import json
from pathlib import Path


def write_dialogues(path, scenario, trajectories):
    lines = [
        f"# {scenario['title']} — Free-form Rollout Dialogues",
        "",
        "> Generated from open-ended model interaction. No predefined strategy labels or scripted action paths.",
        "",
        f"- Scenario ID: `{scenario['scenario_id']}`",
        f"- Trajectories: `{len(trajectories)}`",
        "",
    ]
    for trajectory in trajectories:
        provenance = trajectory.get("policy_provenance", {})
        lines.extend([
            f"## `{trajectory['policy_id']}`",
            "",
            f"Model: `{provenance.get('model', 'unknown')}` · sampling: `{json.dumps(provenance.get('sampling', {}), ensure_ascii=False, sort_keys=True)}`",
            "",
        ])
        for turn in trajectory["turns"]:
            lines.extend([
                f"### {turn['turn_id']}",
                "",
                f"**Evaluated model:** {turn['policy_action']['text']}",
                "",
                f"**Environment character:** {turn['environment_response']}",
                "",
            ])
            expression = turn.get("observable_expression", {})
            if expression:
                lines.extend([
                    f"_Expression: {expression.get('facial_expression', '—')}; gaze: {expression.get('gaze', '—')}; prosody: {expression.get('prosody', '—')}._",
                    "",
                ])
    Path(path).write_text("\n".join(lines), encoding="utf-8")
