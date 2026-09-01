import json
import unittest
import tempfile
from pathlib import Path

from evaluation.leakage import assert_no_leaks
from evaluation.metrics import macro_f1
from providers.factory import build_provider
from scripts.run_pipeline import load_scenarios
from scripts.scenario_docs import assert_document_current, assert_manifest_current, write_document


class PipelineContractTest(unittest.TestCase):
    def test_scenario_manifest_matches_catalog(self):
        directory = Path("configs/scenarios")
        scenarios = load_scenarios(directory)
        manifest = json.loads(assert_manifest_current(directory).read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(scenarios), 10)
        self.assertEqual(manifest["scenario_count"], len(scenarios))
        self.assertEqual(
            {item["scenario_id"] for item in manifest["scenarios"]},
            {item["scenario_id"] for item in scenarios},
        )

    def test_every_scenario_has_current_markdown(self):
        for path in sorted(Path("configs/scenarios").glob("scenario_*.json")):
            paired = assert_document_current(path)
            self.assertEqual(paired, path.with_suffix(".md"))
            text = paired.read_text(encoding="utf-8")
            self.assertIn("## 1. 故事初始化", text)
            self.assertIn("### 初始 State（0–10）", text)
            self.assertIn("### 视频触发规则", text)
            self.assertIn("JSON SHA-256", text)

    def test_missing_and_stale_documentation_are_rejected(self):
        source = Path("configs/scenarios/scenario_001.json")
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "scenario_001.json"
            candidate.write_bytes(source.read_bytes())
            with self.assertRaises(ValueError):
                assert_document_current(candidate)
            write_document(candidate)
            assert_document_current(candidate)
            candidate.write_text(candidate.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                assert_document_current(candidate)

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
