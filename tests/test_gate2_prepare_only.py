import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.prepare_batch_gate2 import main


class Gate2PrepareOnlyTest(unittest.TestCase):
    def test_prepare_only_never_loads_model_routes(self):
        with TemporaryDirectory() as directory:
            batch = Path(directory)
            with (
                patch(
                    "scripts.prepare_batch_gate2.load_actual_scenarios",
                    return_value=[{"scenario_id": "CF150_001"}],
                ),
                patch(
                    "scripts.prepare_batch_gate2.load_records",
                    return_value=[{"trajectory_id": "trajectory-1"}],
                ),
                patch(
                    "scripts.prepare_batch_gate2.e1_packet",
                    return_value=[{"review_id": "e1"}],
                ),
                patch(
                    "scripts.prepare_batch_gate2.e2_packet",
                    return_value=[{"review_id": "e2"}],
                ),
                patch("scripts.prepare_batch_gate2.pending_e1_e2"),
                patch(
                    "scripts.prepare_batch_gate2.machine_evidence_ready",
                    return_value=(False, {}),
                ),
                patch("scripts.prepare_batch_gate2.ModelRoutes.load") as routes,
            ):
                main([
                    "--batch-root", str(batch),
                    "--scenario-root", str(batch / "scenarios"),
                    "--rollout-root", str(batch / "rollouts"),
                    "--rollout-config", str(batch / "rollout.json"),
                    "--prepare-only",
                ])
            routes.assert_not_called()
            manifest = json.loads(
                (batch / "gate2" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["mode"], "prepare_only")
            self.assertEqual(manifest["network_requests_performed"], 0)
            self.assertEqual(manifest["e1_review_items"], 1)
            self.assertEqual(manifest["e2_review_items"], 1)


if __name__ == "__main__":
    unittest.main()
