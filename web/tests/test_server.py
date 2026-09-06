import unittest

from web.server import (
    annotation_contract,
    api_payload,
    load_instances,
    load_scenarios,
    scenario_detail,
)


class ScenarioWebTest(unittest.TestCase):
    def test_scenario_catalog_reads_hybrid_sources(self):
        payload = api_payload("/api/scenarios")
        self.assertEqual(len(payload["scenarios"]), len(load_scenarios()))
        self.assertEqual(len(payload["scenarios"]), 20)
        self.assertTrue(all(item["source_type"] for item in payload["scenarios"]))
        self.assertTrue(all("action_ids" not in item for item in payload["scenarios"]))
        self.assertTrue(all(item["task_count"] == 9 for item in payload["scenarios"]))

    def test_detail_contains_annotation_materials(self):
        detail = scenario_detail("IA_PIPE_001")
        self.assertEqual(detail["summary"]["scenario_id"], "IA_PIPE_001")
        self.assertIn("narrative_design", detail["scenario"])
        self.assertNotIn("action_effects", detail["scenario"])
        self.assertIn("## 1. 叙事结构与初始化", detail["documentation"])
        self.assertIn("## 2. 自由交互与状态更新契约", detail["documentation"])
        self.assertEqual(len(detail["rollouts"]), 3)
        self.assertEqual(len(detail["instances"]), 9)
        self.assertEqual(
            {item["task_type"] for item in detail["instances"]},
            {
                "T1_state_tracking",
                "T2_history_sensitive_merge",
                "T3_counterfactual_choice_effect",
            },
        )
        self.assertIn("task_review", detail)

    def test_annotation_contract_uses_canonical_gate_fields(self):
        contract = annotation_contract()
        self.assertEqual(contract["storage"], "browser_local_draft")
        self.assertEqual(len(contract["rollout_quality_dimensions"]), 6)
        self.assertEqual(len(contract["rollout_hard_reject_reasons"]), 8)
        self.assertEqual(set(contract["task_review_ratings"]), {
            "T1_state_tracking",
            "T2_history_sensitive_merge",
            "T3_counterfactual_choice_effect",
        })
        self.assertEqual(len(load_instances("IA_PIPE_001")), 9)
        self.assertEqual(
            api_payload("/api/annotation-contract")["format"],
            "socialflux_annotation_ui_v1",
        )

    def test_health_reports_annotation_workbench(self):
        health = api_payload("/api/health")
        self.assertEqual(health["pipeline_version"], "v2")
        self.assertEqual(health["site_mode"], "annotation_workbench")

    def test_unknown_scenario_is_not_found(self):
        self.assertIsNone(api_payload("/api/scenarios/does-not-exist"))


if __name__ == "__main__":
    unittest.main()
