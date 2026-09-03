import json
import unittest
from pathlib import Path

from evaluation.pipeline_acceptance import (
    CRITERIA,
    build_acceptance_report,
    load_scenarios,
)
from rollout.runner import RolloutRunner
from tests.support import TextPolicy, environment_factory


class PipelineAcceptanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenarios = load_scenarios("configs/scenarios")

    def test_report_has_nine_revision_criteria_and_no_fake_pass(self):
        report = build_acceptance_report(self.scenarios)
        self.assertEqual(tuple(item["criterion"] for item in report["criteria"]), CRITERIA)
        self.assertEqual(len(report["criteria"]), 9)
        self.assertFalse(report["gate"]["automated_artifacts_ready"])
        self.assertFalse(report["gate"]["research_acceptance"])
        self.assertIn("multi-turn repair/neutral/escalation controlled-policy sensitivity",
                      report["gate"]["deprecated_checks"])

    def test_natural_trajectory_structure_is_recognized(self):
        scenario = self.scenarios[0]
        trajectory = RolloutRunner(environment_factory(scenario)).run(
            TextPolicy("model-a-seed-1", ["请解释贡献证据。"], seed=1),
            max_turns=1,
        )
        report = build_acceptance_report(self.scenarios, [trajectory])
        criterion = next(
            item for item in report["criteria"]
            if item["criterion"] == "8. Full-Trajectory Plausibility"
        )
        self.assertEqual(criterion["status"], "provisionally_ready")
        self.assertEqual(criterion["formal_human_judgment"], "pending")


if __name__ == "__main__":
    unittest.main()
