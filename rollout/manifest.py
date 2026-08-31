"""Write a reproducible manifest for a batch of rollout artifacts."""

import json
from pathlib import Path


def write_manifest(path, trajectories, config=None):
    payload = {
        "format": "emotree_rollout_manifest_v1",
        "trajectory_count": len(trajectories),
        "scenario_ids": sorted({x["scenario_id"] for x in trajectories}),
        "policy_ids": sorted({x["policy_id"] for x in trajectories}),
        "config": config or {},
        "trajectory_ids": [x["trajectory_id"] for x in trajectories],
    }
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
