import unittest

from web.server import api_payload, load_scenarios, scenario_detail


class ScenarioWebTest(unittest.TestCase):
    def test_scenario_catalog_reads_hybrid_sources(self):
        payload = api_payload("/api/scenarios")
        self.assertEqual(len(payload["scenarios"]), len(load_scenarios()))
        self.assertEqual(len(payload["scenarios"]), 10)
        self.assertTrue(all(item["source_type"] for item in payload["scenarios"]))
        self.assertTrue(all("action_ids" not in item for item in payload["scenarios"]))

    def test_detail_contains_revised_scenario_view(self):
        detail = scenario_detail("IA_PIPE_001")
        self.assertEqual(detail["summary"]["scenario_id"], "IA_PIPE_001")
        self.assertIn("narrative_design", detail["scenario"])
        self.assertNotIn("action_effects", detail["scenario"])
        self.assertIn("## 1. 叙事结构与初始化", detail["documentation"])
        self.assertIn("## 2. 自由交互与状态更新契约", detail["documentation"])
        self.assertFalse(detail["rollouts"])

    def test_health_reports_pipeline_v2(self):
        self.assertEqual(api_payload("/api/health")["pipeline_version"], "v2")

    def test_unknown_scenario_is_not_found(self):
        self.assertIsNone(api_payload("/api/scenarios/does-not-exist"))


if __name__ == "__main__":
    unittest.main()
