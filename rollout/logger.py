"""Atomic JSON trajectory logger."""

import json
import os
from pathlib import Path


class TrajectoryLogger:
    def __init__(self, output_dir):
        self.output_dir = Path(output_dir)

    def write(self, trajectory):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        target = self.output_dir / f"{trajectory['trajectory_id']}.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(trajectory, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, target)
        return target
