import unittest

from evaluation.pipeline_acceptance import build_acceptance_report, load_scenarios


class PipelineAcceptanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = build_acceptance_report(load_scenarios("configs/scenarios"))

    def test_all_automated_criteria_pass(self):
        by_name = {item["criterion"]: item for item in self.report["criteria"]}
        for name in (
            "1. State Update Validity",
            "2. Persona Sensitivity",
            "3. Paraphrase Robustness",
            "4. Controlled Policy Sensitivity",
        ):
            self.assertEqual(by_name[name]["status"], "passed", name)
        self.assertEqual(by_name["5. Full Trajectory Plausibility"]["status"], "provisionally_passed")
        self.assertTrue(self.report["gate"]["automated_passed"])

    def test_formal_human_signoff_is_explicit(self):
        self.assertEqual(
            self.report["gate"]["formal_human_pending"],
            ["5. Full Trajectory Plausibility"],
        )
        self.assertFalse(self.report["gate"]["research_acceptance"])


if __name__ == "__main__":
    unittest.main()
