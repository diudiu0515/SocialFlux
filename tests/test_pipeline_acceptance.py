import unittest

from evaluation.pipeline_acceptance import build_acceptance_report, load_scenarios


class PipelineAcceptanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = build_acceptance_report(load_scenarios("configs/scenarios"))

    def test_automated_validity_and_policy_gates_pass(self):
        by_name = {item["criterion"]: item for item in self.report["criteria"]}
        self.assertEqual(by_name["1. State Update Validity"]["status"], "passed")
        self.assertEqual(by_name["4. Controlled Policy Sensitivity"]["status"], "passed")

    def test_known_open_acceptance_items_are_explicit(self):
        self.assertEqual(
            self.report["gate"]["blocking_items"],
            [
                "2. Persona Sensitivity",
                "3. Paraphrase Robustness",
                "5. Full Trajectory Plausibility",
            ],
        )


if __name__ == "__main__":
    unittest.main()
