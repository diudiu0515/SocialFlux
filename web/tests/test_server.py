import unittest

from web.server import api_payload, load_scenarios, scenario_detail


class ScenarioWebTest(unittest.TestCase):
    def test_scenario_catalog_reads_current_configs(self):
        payload = api_payload("/api/scenarios")
        self.assertEqual(len(payload["scenarios"]), len(load_scenarios()))
        self.assertGreaterEqual(len(payload["scenarios"]), 10)
        self.assertTrue(all(item["action_ids"] for item in payload["scenarios"]))

    def test_detail_contains_scenario_and_pipeline_views(self):
        detail = scenario_detail("IA_PIPE_001")
        self.assertEqual(detail["summary"]["scenario_id"], "IA_PIPE_001")
        self.assertIn("video_triggers", detail["scenario"])
        self.assertIn("## 1. 故事初始化", detail["documentation"])
        self.assertIn("### 视频触发规则", detail["documentation"])
        self.assertIn("Rollout Dialogues", detail["rollout_dialogues"])
        self.assertIn("configs/scenarios/scenario_001/rollouts", detail["summary"]["rollout_bundle"])
        self.assertTrue(detail["rollouts"])

    def test_unknown_scenario_is_not_found(self):
        self.assertIsNone(api_payload("/api/scenarios/does-not-exist"))


if __name__ == "__main__":
    unittest.main()
