import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.generate_claude150_scenarios import _scenario_complete
from prompts.loader import prompt_manifest


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
                "prompts": {
                    prompt_id: prompt_manifest()["prompts"][prompt_id]
                    for prompt_id in (
                        "scenario_candidate_script_v2",
                        "scenario_candidate_quality_gate_v1",
                        "scenario_candidate_core_v1",
                        "scenario_candidate_runtime_design_v2",
                "scenario_evaluated_persona_backfill_v1",
                        "scenario_candidate_state_values_v1",
                        "scenario_candidate_expression_triggers_v1",
                    )
                },
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
                    "evaluated_agent_role": {
                        "persona": {
                            "name": "Lin",
                            "role": "participant",
                            "core_values": ["fairness"],
                            "temperament": "measured",
                            "communication_style": "direct",
                            "decision_style": "evidence-led",
                            "conflict_style": "calm",
                            "boundaries": ["no fabrication"],
                        },
                    },
                }), encoding="utf-8")
                self.assertTrue(_scenario_complete(
                    output,
                    1,
                    "routes-hash",
                ))


if __name__ == "__main__":
    unittest.main()
