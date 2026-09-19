import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from web.server import (
    annotation_contract,
    api_payload,
    credentials_match,
    load_instances,
    load_gpt50_review,
    load_gpt50_scenario,
    load_rollouts,
    load_task_examples,
    load_scenarios,
    scenario_detail,
)


class ScenarioWebTest(unittest.TestCase):
    def test_gpt50_gate1_review_uses_one_explicit_hash_bound_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "scenarios"
            target = root / "scenario_001" / "scenario_001.json"
            target.parent.mkdir(parents=True)
            source = Path("configs/scenarios/scenario_001/scenario_001.json")
            scenario = json.loads(source.read_text(encoding="utf-8"))
            target.write_text(
                json.dumps(scenario, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with patch("web.server.GPT50_SCENARIO_ROOTS", (root,)):
                packet = load_gpt50_review()
                self.assertEqual(packet["scenario_count"], 1)
                self.assertEqual(packet["schema_valid_count"], 1)
                candidate = packet["candidates"][0]
                self.assertEqual(candidate["scenario_id"], scenario["scenario_id"])
                self.assertEqual(
                    candidate["scenario_sha256"],
                    hashlib.sha256(target.read_bytes()).hexdigest(),
                )
                detail = load_gpt50_scenario(scenario["scenario_id"])
                self.assertEqual(detail["schema_status"], "valid")
                self.assertEqual(detail["scenario"], scenario)

    def test_gpt50_gate1_page_is_linked_from_review_center(self):
        review = Path("web/static/review.html").read_text(encoding="utf-8")
        page = Path("web/static/gpt50_gate1.html").read_text(encoding="utf-8")
        script = Path("web/static/gpt50_gate1.js").read_text(encoding="utf-8")
        self.assertIn('href="/gpt50_gate1.html"', review)
        self.assertIn('src="/gpt50_gate1.js?v=1"', page)
        self.assertIn("/api/gpt50-review", script)
        self.assertIn("human_attestation", script)

    def test_basic_auth_credentials(self):
        encoded = base64.b64encode(b"socialflux:correct-horse").decode("ascii")
        self.assertTrue(
            credentials_match(f"Basic {encoded}", "socialflux", "correct-horse")
        )
        self.assertFalse(
            credentials_match(f"Basic {encoded}", "socialflux", "wrong-password")
        )
        self.assertFalse(
            credentials_match("Bearer token", "socialflux", "correct-horse")
        )

    def test_scenario_catalog_reads_hybrid_sources(self):
        payload = api_payload("/api/scenarios")
        self.assertEqual(len(payload["scenarios"]), len(load_scenarios()))
        self.assertEqual(len(payload["scenarios"]), 20)
        self.assertTrue(all(item["source_type"] for item in payload["scenarios"]))
        self.assertTrue(all("action_ids" not in item for item in payload["scenarios"]))
        self.assertTrue(all(item["task_count"] <= 3 for item in payload["scenarios"]))
        self.assertNotEqual(sum(item["task_count"] for item in payload["scenarios"]), 180)

    def test_detail_contains_annotation_materials(self):
        detail = scenario_detail("IA_PIPE_001")
        self.assertEqual(detail["summary"]["scenario_id"], "IA_PIPE_001")
        self.assertEqual(detail["summary"]["screening"]["final_trajectory_count"], 0)
        self.assertIn("narrative_design", detail["scenario"])
        self.assertNotIn("action_effects", detail["scenario"])
        self.assertIn("## 1. 叙事结构与初始化", detail["documentation"])
        self.assertIn("## 2. 自由交互与状态更新契约", detail["documentation"])
        self.assertGreaterEqual(
            len(detail["rollouts"]),
            detail["long_rollout_generation"]["completed_slot_count"],
        )
        self.assertTrue(all("screening" in item for item in detail["rollouts"]))
        self.assertEqual(
            detail["summary"]["screening"]["candidate_count"],
            detail["long_rollout_generation"]["completed_slot_count"],
        )
        self.assertLessEqual(len(detail["instances"]), 3)
        self.assertTrue(
            {item["task_type"] for item in detail["instances"]}.issubset({
                "T1_state_tracking",
                "T2_history_sensitive_merge",
                "T3_counterfactual_choice_effect",
            })
        )
        self.assertIn("task_review", detail)
        model_contract = detail["evaluated_model_contract"]
        self.assertEqual(model_contract["horizon_turns"], 20)
        self.assertEqual(model_contract["prompt_id"], "task_t4_action_v21")
        self.assertTrue(model_contract["role_card"]["role"])
        self.assertTrue(model_contract["role_card"]["explicit_goal"])
        self.assertIn("{{payload_json}}", model_contract["prompt_template"])
        rendered = model_contract["rendered_initial_prompt"]
        self.assertNotIn(
            detail["scenario"]["environment_agent"]["hidden_intention"], rendered
        )
        self.assertIn(
            "environment_agent.hidden_intention",
            model_contract["private_author_fields_excluded"],
        )
        self.assertEqual(detail["long_rollout_generation"]["required_turns"], 20)

    def test_annotation_contract_uses_canonical_gate_fields(self):
        contract = annotation_contract()
        self.assertEqual(contract["storage"], "browser_local_draft")
        self.assertEqual(len(contract["rollout_quality_dimensions"]), 6)
        self.assertEqual(len(contract["rollout_hard_reject_reasons"]), 10)
        self.assertEqual(contract["rollout_screening"]["final_per_scenario"], 1)
        self.assertEqual(set(contract["task_review_ratings"]), {
            "T1_state_tracking",
            "T2_history_sensitive_merge",
            "T3_counterfactual_choice_effect",
        })
        self.assertLessEqual(len(load_instances("IA_PIPE_001")), 3)
        self.assertEqual(
            api_payload("/api/annotation-contract")["format"],
            "socialflux_annotation_ui_v1",
        )

    def test_archived_outputs_are_not_exposed_as_current_data(self):
        manual = api_payload("/api/manual-review")
        self.assertEqual(manual["format"], "socialflux_manual_review_catalog_v1")
        self.assertEqual(len(manual["categories"]), 9)

        workspace = api_payload("/api/review-workspace")
        self.assertEqual(workspace["format"], "socialflux_human_review_workspace_v1")
        self.assertEqual(workspace["staffing_plan"]["gate1"]["reviewers_required"], 1)
        self.assertEqual(workspace["staffing_plan"]["gate4"]["independent_reviewers"], 2)

        self.assertEqual(api_payload("/api/scale20-pilot")["candidates"], [])
        self.assertEqual(api_payload("/api/scale20-review")["candidates"], [])
        self.assertTrue(all(
            load_rollouts(f"IA_PIPE_{number:03d}") == []
            for number in range(1, 21)
        ))

        task_review = api_payload("/api/scale300-tasks")
        self.assertEqual(task_review["total_scenarios"], 0)
        self.assertEqual(task_review["processed"], 0)
        self.assertEqual(task_review["candidates"], [])
        self.assertEqual(load_task_examples()["examples"], [])

        detail = scenario_detail("IA_PIPE_003")
        self.assertEqual(detail["summary"]["scenario_id"], "IA_PIPE_003")
        self.assertEqual(detail["rollouts"], [])

    def test_rollout_frontend_renders_all_three_stages_per_turn(self):
        script = Path("web/static/app.js").read_text(encoding="utf-8")
        self.assertNotIn("innerHTML = `\n  const diagnostic", script)
        self.assertIn("Structured Appraisal · 独立 LLM 调用", script)
        self.assertIn("确定性校准与数值更新 · 无 LLM", script)
        self.assertIn("Response 与 ledger · 第二次独立 LLM 调用后结构记录", script)
        self.assertIn("被评估 Agent 行动", script)
        self.assertIn("Environment 角色回应", script)
        self.assertIn("历史诊断轨迹", script)

    def test_gate1_review_exposes_all_current_hash_bound_scenarios(self):
        packet = api_payload("/api/gate1-review")
        self.assertEqual(packet["format"], "socialflux_scenario_review_registry_v1")
        self.assertEqual(len(packet["records"]), 20)
        self.assertEqual(len({item["scenario_id"] for item in packet["records"]}), 20)
        for item in packet["records"]:
            number = int(item["scenario_id"].rsplit("_", 1)[1])
            path = Path(f"configs/scenarios/scenario_{number:03d}/scenario_{number:03d}.json")
            self.assertEqual(
                item["scenario_sha256"],
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            detail = scenario_detail(item["scenario_id"])
            self.assertEqual(detail["gate1_review_packet"], item)

    def test_gate1_contract_uses_registry_scores_and_all_checks(self):
        contract = annotation_contract()
        self.assertEqual(set(contract["scenario_rating_scale"]["dimensions"]), {
            "social_plausibility", "character_coherence", "tradeoff_quality",
            "history_necessity", "interaction_richness", "t1_t4_suitability",
        })
        self.assertEqual(len(contract["scenario_checks"]), 15)

    def test_health_reports_annotation_workbench(self):
        health = api_payload("/api/health")
        self.assertEqual(health["pipeline_version"], "20turn-selected-v1")
        self.assertEqual(health["site_mode"], "annotation_workbench")

    def test_unknown_scenario_is_not_found(self):
        self.assertIsNone(api_payload("/api/scenarios/does-not-exist"))


if __name__ == "__main__":
    unittest.main()
