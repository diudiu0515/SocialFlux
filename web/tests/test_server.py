import base64
import hashlib
from pathlib import Path
import unittest

from web.server import (
    annotation_contract,
    api_payload,
    credentials_match,
    load_instances,
    load_rollouts,
    load_task_examples,
    load_scenarios,
    scenario_detail,
)


class ScenarioWebTest(unittest.TestCase):
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

    def test_manual_review_catalog_exposes_every_stage(self):
        review = api_payload("/api/manual-review")
        identifiers = {item["id"] for item in review["categories"]}
        self.assertEqual(
            identifiers,
            {"gate1_scenario", "gate2_environment", "gate3_rollout", "gate4_tasks",
             "media", "filter_holdout", "dataset_audit",
             "long_rollout_generation", "scale20_pilot"},
        )
        self.assertEqual(review["screening_summary"].get("provisional_selected_count", 0), 0)
        self.assertEqual(review["long_rollout_generation"]["required_turns"], 20)
        by_id = {item["id"]: item for item in review["categories"]}
        self.assertEqual(by_id["gate3_rollout"]["required"], 60)
        self.assertEqual(by_id["gate4_tasks"]["required"], 6)
        self.assertIn("SocialFlux Rollout Screening Protocol v1", review["protocol_document"])
        diagnostic = review["r3_current_diagnostic_review"]
        self.assertEqual(diagnostic["quality_version"], "r3_semantic_ledger_v29")
        self.assertFalse(diagnostic["formal_acceptance"])
        self.assertEqual(diagnostic["short_appraisal_probe"]["passed_case_count"], 13)

    def test_scale20_pilot_exposes_all_statuses_and_complete_turns(self):
        pilot = api_payload("/api/scale20-pilot")
        self.assertEqual(len(pilot["scenario_results"]), 20)
        self.assertEqual(len(pilot["candidates"]), 8)
        self.assertEqual(
            {item["scenario_id"] for item in pilot["candidates"]},
            {"IA_PIPE_005", "IA_PIPE_012", "IA_PIPE_013", "IA_PIPE_018"},
        )
        for candidate in pilot["candidates"]:
            trajectory = candidate["trajectory"]
            self.assertEqual(len(trajectory["turns"]), candidate["turn_count"])
            self.assertTrue(all(
                turn.get("policy_action", {}).get("text")
                and turn.get("environment_response")
                for turn in trajectory["turns"]
            ))
            self.assertEqual(
                trajectory["diagnostic_review"]["review_type"],
                "model_semantic_review",
            )
            self.assertEqual(candidate["human_review"], "pending")

    def test_scale20_full_review_exposes_one_trajectory_per_scenario(self):
        review = api_payload("/api/scale20-review")
        self.assertEqual(review["generated_scenario_count"], 20)
        self.assertEqual(len(review["candidates"]), 20)
        self.assertEqual(len({item["scenario_id"] for item in review["candidates"]}), 20)
        self.assertEqual(
            sum(len(item["trajectory"]["turns"]) for item in review["candidates"]),
            review["total_turns"],
        )
        self.assertTrue(all(
            all(
                turn.get("appraisal")
                and "state_after" in turn
                and turn.get("environment_response")
                and "interaction_ledger_after" in turn
                for turn in item["trajectory"]["turns"]
            )
            for item in review["candidates"]
        ))
        self.assertTrue(all(item["human_review"] == "pending" for item in review["candidates"]))

    def test_review_workspace_exposes_staffing_models_and_same_gate4_sample(self):
        workspace = api_payload("/api/review-workspace")
        self.assertEqual(workspace["format"], "socialflux_human_review_workspace_v1")
        self.assertEqual(workspace["staffing_plan"]["gate1"]["reviewers_required"], 1)
        self.assertEqual(workspace["staffing_plan"]["gate2"]["reviewers_required"], 1)
        self.assertEqual(workspace["staffing_plan"]["gate4"]["independent_reviewers"], 2)
        self.assertTrue(workspace["gate4"]["sampling"]["same_sample_for_both_reviewers"])
        self.assertLessEqual(workspace["gate4"]["sampling"]["sample_count"], 6)
        self.assertEqual(
            len(workspace["gate4"]["records"]),
            workspace["gate4"]["sampling"]["sample_count"],
        )
        self.assertLessEqual(workspace["counts"]["task_population"], 60)
        self.assertIn("Qwen3.5-9B", workspace["model_stack"]["environment"]["model"])

    def test_ia003_exposes_rejected_r3_diagnostic_with_ledger(self):
        detail = scenario_detail("IA_PIPE_003")
        diagnostic = next(
            item for item in detail["rollouts"]
            if item.get("diagnostic_review")
        )
        self.assertEqual(len(diagnostic["turns"]), 19)
        self.assertEqual(diagnostic["screening"]["automatic_decision"], "REJECT")
        self.assertTrue(diagnostic["turns"][0].get("interaction_ledger_after"))

    def test_every_scenario_has_round_by_round_rollout_content(self):
        total_rollouts = 0
        total_turns = 0
        for number in range(1, 21):
            scenario_id = f"IA_PIPE_{number:03d}"
            rollouts = load_rollouts(scenario_id)
            self.assertTrue(rollouts, scenario_id)
            self.assertTrue(all(item.get("turns") for item in rollouts), scenario_id)
            self.assertTrue(all(
                turn.get("policy_action", {}).get("text")
                and turn.get("environment_response")
                for item in rollouts for turn in item["turns"]
            ), scenario_id)
            total_rollouts += len(rollouts)
            total_turns += sum(len(item["turns"]) for item in rollouts)
        self.assertGreaterEqual(total_rollouts, 60)
        self.assertGreaterEqual(total_turns, 300)

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

    def test_scale300_task_review_uses_v3_and_exposes_four_machine_answers(self):
        review = api_payload("/api/scale300-tasks")
        self.assertEqual(review["total_scenarios"], 300)
        self.assertEqual(review["processed"], 300)
        self.assertEqual(review["summary"]["answer_counts"], {
            "T1": 50, "T2": 50, "T3": 50, "T4": 50,
        })
        package = api_payload("/api/scale300-task/IA_PIPE_003")
        self.assertEqual(package["format"], "socialflux_scale300_task_package_v3")
        self.assertEqual(set(package["tasks"]), {"T1", "T2", "T3", "T4"})
        self.assertTrue(all(
            task["answer_status"] == "machine_proposal_pending_human_review"
            for task in package["tasks"].values()
        ))
        self.assertTrue(all(
            not task["formal_pool_eligible"]
            for task in package["tasks"].values()
        ))

    def test_task_examples_expose_three_machine_proposals_without_gt(self):
        packet = api_payload("/api/task-examples")
        self.assertEqual({item["task"] for item in packet["examples"]}, {"T1", "T2", "T3"})
        self.assertEqual(packet["human_ground_truth_count"], 0)
        for item in packet["examples"]:
            self.assertIsNone(item["text_instance"]["ground_truth"])
            self.assertIsNotNone(item["llm_answer"])
            self.assertIn("not_ground_truth", item["answer_provenance"]["answer_type"])
        t3 = next(item for item in packet["examples"] if item["task"] == "T3")
        self.assertFalse(t3["media"]["shown_to_model"])
        self.assertEqual(load_task_examples()["status"], packet["status"])



    def test_unknown_scenario_is_not_found(self):
        self.assertIsNone(api_payload("/api/scenarios/does-not-exist"))


if __name__ == "__main__":
    unittest.main()
