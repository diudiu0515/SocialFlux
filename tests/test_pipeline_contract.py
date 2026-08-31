import json
import unittest
from pathlib import Path

from evaluation.leakage import assert_no_leaks
from evaluation.metrics import macro_f1
from providers.factory import build_provider
from scripts.run_pipeline import load_scenarios


class PipelineContractTest(unittest.TestCase):
    def test_ten_scenario_manifest(self):
        scenarios = load_scenarios(Path("configs/scenarios"))
        self.assertEqual(len(scenarios), 10)
        self.assertEqual(len({item["scenario_id"] for item in scenarios}), 10)

    def test_provider_factory_contracts(self):
        configs = [
            {"provider": "openai_compatible", "endpoint": "http://localhost/v1/chat/completions", "model": "x"},
            {"provider": "anthropic", "endpoint": "http://localhost/messages", "model": "x", "api_key": "x"},
            {"provider": "gemini", "endpoint": "http://localhost", "model": "x", "api_key": "x"},
            {"provider": "local_vllm", "endpoint": "http://localhost/v1/chat/completions", "model": "x"},
        ]
        for config in configs:
            self.assertIsNotNone(build_provider(config))

    def test_leakage_audit_and_macro_f1(self):
        assert_no_leaks({"input": {"history": []}, "ground_truth": None})
        self.assertEqual(macro_f1(["a", "b"], ["a", "b"], ["a", "b"]), 1.0)


if __name__ == "__main__":
    unittest.main()
