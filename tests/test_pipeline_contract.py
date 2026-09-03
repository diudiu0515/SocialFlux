import json
import tempfile
import unittest
from pathlib import Path

from evaluation.leakage import assert_no_leaks
from providers.factory import build_provider
from scripts.run_pipeline import load_rollout_config, load_scenarios
from scripts.scenario_docs import (
    assert_document_current,
    assert_manifest_current,
    write_document,
)


class PipelineContractTest(unittest.TestCase):
    def test_scenario_catalog_has_both_sources_and_coverage(self):
        directory = Path("configs/scenarios")
        scenarios = load_scenarios(directory)
        manifest = json.loads(assert_manifest_current(directory).read_text(encoding="utf-8"))
        coverage = json.loads((directory / "coverage_matrix.json").read_text(encoding="utf-8"))
        self.assertEqual(len(scenarios), 20)
        self.assertEqual(manifest["source_counts"]["narrative-derived"], 15)
        self.assertEqual(manifest["source_counts"]["synthetic-script"], 5)
        self.assertRegex(manifest["prompt_manifest_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(len(coverage["rows"]), len(scenarios))
        for entry in manifest["scenarios"]:
            self.assertRegex(entry["scenario_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(entry["documentation_sha256"], r"^[0-9a-f]{64}$")

    def test_every_scenario_has_current_markdown_and_no_action_taxonomy(self):
        for path in sorted(Path("configs/scenarios").glob("scenario_*/scenario_*.json")):
            paired = assert_document_current(path)
            scenario = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(path.parent.name, path.stem)
            self.assertNotIn("action_effects", scenario)
            text = paired.read_text(encoding="utf-8")
            self.assertIn("## 1. 叙事结构与初始化", text)
            self.assertIn("## 2. 自由交互与状态更新契约", text)
            self.assertIn("candidate_pending_human_freeze", text)
            self.assertIn("JSON SHA-256", text)

    def test_screen_inspired_scenarios_are_originalized_and_non_template(self):
        paths = sorted(Path("configs/scenarios").glob("scenario_*/scenario_*.json"))[10:]
        self.assertEqual(len(paths), 10)
        scenarios = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
        self.assertTrue(all(item["source"]["type"] == "narrative-derived" for item in scenarios))
        self.assertTrue(all(
            "no copied dialogue or scene sequence" in item["source"]["provenance_note"]
            for item in scenarios
        ))
        self.assertEqual(len({item["opening_response"] for item in scenarios}), 10)
        self.assertEqual(len({item["mechanism"] for item in scenarios}), 10)
        self.assertGreaterEqual(len({
            tuple(sorted(
                variable
                for family in item["selected_state_variables"].values()
                for variable in family
            ))
            for item in scenarios
        }), 8)
        trigger_ids = [
            trigger["trigger_id"]
            for item in scenarios
            for trigger in item["video_triggers"]
        ]
        self.assertEqual(len(trigger_ids), len(set(trigger_ids)))

    def test_missing_and_stale_documentation_are_rejected(self):
        source = Path("configs/scenarios/scenario_001/scenario_001.json")
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

    def test_rollout_config_requires_model_sampling_diversity(self):
        config = load_rollout_config("configs/rollout_pool.example.json")
        self.assertGreaterEqual(len(config["policies"]), 2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            bad = {
                "format": "socialflux_rollout_pool_v1",
                "environment": {"provider": {}},
                "construction": {"provider": {}},
                "policies": [{"policy_id": "only-one", "provider": {"model": "x"}}],
            }
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_rollout_config(path)

    def test_provider_factory_contracts(self):
        configs = [
            {"provider": "openai_compatible", "endpoint": "http://localhost/v1/chat/completions", "model": "x"},
            {"provider": "anthropic", "endpoint": "http://localhost/messages", "model": "x", "api_key": "x"},
            {"provider": "gemini", "endpoint": "http://localhost", "model": "x", "api_key": "x"},
            {"provider": "local_vllm", "endpoint": "http://localhost/v1/chat/completions", "model": "x"},
        ]
        for config in configs:
            self.assertIsNotNone(build_provider(config))

    def test_leakage_audit(self):
        assert_no_leaks({"input": {"history": []}, "ground_truth": None})


if __name__ == "__main__":
    unittest.main()
