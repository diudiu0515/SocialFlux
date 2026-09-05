import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class FormalGroundTruthCliTest(unittest.TestCase):
    def test_prepare_rejects_failed_gate_four_before_reading_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            instances = root / "instances.jsonl"
            instances.write_text("", encoding="utf-8")
            report = root / "report.json"
            report.write_text(json.dumps({"gates": {"gate_4_task_instance_quality": {"passed": False, "instance_count": 0}}}), encoding="utf-8")
            process = subprocess.run(
                [sys.executable, "scripts/formal_ground_truth.py", "prepare", "--instances", str(instances), "--quality-gate-report", str(report), "--output", str(root / "packets.jsonl")],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(process.returncode, 0)
            self.assertIn("passed Gate 4", process.stderr)


if __name__ == "__main__":
    unittest.main()
