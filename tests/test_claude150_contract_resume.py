import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.generate_claude150_scenarios import _scenario_complete


class Claude150ContractResumeTest(unittest.TestCase):
    def test_resume_requires_completed_v2_scenario(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)
            target = (
                output
                / "scenarios"
                / "scenario_001"
                / "scenario_001.json"
            )
            run = (
                output
                / "authoring"
                / "scenario_001"
                / "run_manifest.json"
            )
            target.parent.mkdir(parents=True)
            run.parent.mkdir(parents=True)
            run.write_text(json.dumps({
                "status": "candidate_generated_pending_human_gate1",
                "model_routes_sha256": "routes-hash",
            }), encoding="utf-8")
            with patch(
                "scripts.generate_claude150_scenarios.validate_scenario"
            ):
                target.write_text(json.dumps({}), encoding="utf-8")
                self.assertFalse(_scenario_complete(
                    output,
                    1,
                    "routes-hash",
                ))
                target.write_text(json.dumps({
                    "state_contract_version": "socialflux_state_v2",
                }), encoding="utf-8")
                self.assertTrue(_scenario_complete(
                    output,
                    1,
                    "routes-hash",
                ))


if __name__ == "__main__":
    unittest.main()
