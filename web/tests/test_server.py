import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from web.server import (
    GPT50_SCENARIO_ROOTS,
    annotation_contract,
    api_payload,
    credentials_match,
    load_instances,
    load_gpt50_review,
    load_gpt50_gate2,
    load_gpt50_rollout,
    load_gpt50_rollout_progress,
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
            source = Path(
                "data/gpt50/experiment/scenario/scenarios/"
                "scenario_001/scenario_001.json"
            )
            scenario = json.loads(source.read_text(encoding="utf-8"))
            target.write_text(
                json.dumps(scenario, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with patch("web.server.GPT50_SCENARIO_ROOTS", (root,)):
                packet = load_gpt50_review()
                self.assertEqual(packet["scenario_count"], 1)
                self.assertEqual(packet["expected_scenario_count"], 50)
                self.assertEqual(packet["batch_status"], "formal_batch_incomplete")
                self.assertFalse(packet["review_ready"])
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

    def test_gpt50_review_never_falls_back_to_smoke_data(self):
        self.assertTrue(all("smoke" not in str(root) for root in GPT50_SCENARIO_ROOTS))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "formal" / "scenarios"
            with patch("web.server.GPT50_SCENARIO_ROOTS", (root,)):
                packet = load_gpt50_review()
        self.assertEqual(packet["scenario_count"], 0)
        self.assertEqual(packet["batch_status"], "missing_formal_batch")
        self.assertFalse(packet["review_ready"])
        self.assertIn("smoke", packet["review_blocker"])

    def test_gpt50_rollout_progress_is_exposed_for_the_review_site(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            progress = {
                "status": "in_progress",
                "expected_slot_count": 50,
                "completed_slots": {
                    "GPT50_001::policy": {
                        "scenario_id": "GPT50_001",
                        "turn_count": 4,
                        "accepted_at_utc": "2026-09-20T08:00:00+00:00",
                        "admission": "human_postfilter",
                        "machine_precheck_passed": False,
                    }
                },
                "attempts": [
                    {
                        "scenario_id": "GPT50_002",
                        "status": "generation_error",
                        "error_type": "TimeoutError",
                        "error": "timed out",
                        "finished_at_utc": "2026-09-20T08:01:00+00:00",
                    }
                ],
                "updated_at_utc": "2026-09-20T08:01:00+00:00",
            }
            (root / "progress.json").write_text(
                json.dumps(progress), encoding="utf-8"
            )
            with patch("web.server.GPT50_ROLLOUT_ROOT", root):
                packet = load_gpt50_rollout_progress()
                api = api_payload("/api/gpt50-rollout")
            self.assertTrue(packet["available"])
            self.assertEqual(packet["completed_count"], 0)
            self.assertEqual(packet["retained_count"], 1)
            self.assertEqual(packet["short_trajectory_count"], 1)
            self.assertEqual(packet["pending_count"], 48)
            self.assertEqual(packet["reviewable_count"], 1)
            self.assertEqual(packet["without_readable_rollout_count"], 49)
            self.assertEqual(
                packet["by_scenario"]["GPT50_001"]["turn_count"], 4
            )
            self.assertEqual(
                packet["attempt_status_counts"]["generation_error"], 1
            )
            self.assertEqual(api["completed_count"], 0)

    def test_gpt50_rollout_detail_exposes_dialogue_for_human_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "rollouts"
            scenario_path = (
                Path(directory)
                / "scenarios"
                / "scenario_001"
                / "scenario_001.json"
            )
            trajectory_path = root / "scenario_001" / "trajectory.json"
            trajectory_path.parent.mkdir(parents=True)
            trajectory_path.write_text(json.dumps({
                "trajectory_id": "trajectory-1",
                "scenario_id": "GPT50_001",
                "policy_id": "policy-1",
                "policy_provenance": {
                    "prompt_id": "task_rollout_action_v1",
                    "minimum_natural_turns": 10,
                },
                "turns": [{
                    "turn_id": "t1",
                    "policy_action": {"text": "policy text"},
                    "environment_response": "environment text",
                    "appraisal": {
                        "social_act": "request",
                        "speaker_intent": "ask clearly",
                    },
                    "state_delta": {"trust": 1},
                    "dynamics_delta": {},
                    "trigger_events": [],
                }],
                "ending": {"reason": "natural_completion", "turn_id": 1},
            }), encoding="utf-8")
            (root / "progress.json").write_text(json.dumps({
                "completed_slots": {
                    "GPT50_001::policy": {
                        "scenario_id": "GPT50_001",
                        "trajectory_file": "trajectory.json",
                        "turn_count": 1,
                    }
                },
                "attempts": [],
            }), encoding="utf-8")
            records = [(
                scenario_path,
                {"scenario_id": "GPT50_001"},
                "valid",
                "",
            )]
            with (
                patch("web.server.GPT50_ROLLOUT_ROOT", root),
                patch(
                    "web.server._gpt50_scenario_records",
                    return_value=(scenario_path.parents[1], records, []),
                ),
            ):
                detail = load_gpt50_rollout("GPT50_001")
            self.assertEqual(detail["status"], "short_trajectory")
            self.assertEqual(detail["turn_count"], 1)
            self.assertFalse(detail["gate3_candidate"])
            self.assertEqual(
                detail["policy_prompt_id"], "task_rollout_action_v1"
            )
            self.assertEqual(detail["minimum_natural_turns"], 10)
            self.assertIn("不足 10 turn", detail["quality_warning"])
            self.assertEqual(
                detail["turns"][0]["policy_action"], "policy text"
            )
            self.assertEqual(
                detail["turns"][0]["environment_response"],
                "environment text",
            )
            self.assertEqual(detail["human_review"], "pending")

    def test_gpt50_rollout_detail_exposes_machine_rejected_dialogue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "rollouts"
            scenario_path = (
                Path(directory)
                / "scenarios"
                / "scenario_002"
                / "scenario_002.json"
            )
            rejected = (
                root / "scenario_002" / "rejected" / "rejected.json"
            )
            rejected.parent.mkdir(parents=True)
            rejected.write_text(json.dumps({
                "trajectory_id": "trajectory-rejected",
                "scenario_id": "GPT50_002",
                "policy_id": "policy-2",
                "turns": [{
                    "turn_id": "t1",
                    "policy_action": {"text": "I can explain what changed."},
                    "environment_response": "Then start with the missing fact.",
                    "appraisal": {
                        "social_act": "challenge",
                        "speaker_intent": "seek accountability",
                    },
                    "state_delta": {},
                    "dynamics_delta": {},
                    "trigger_events": [],
                }],
                "ending": {"reason": "natural_completion", "turn_id": 1},
            }), encoding="utf-8")
            (root / "progress.json").write_text(json.dumps({
                "completed_slots": {},
                "attempts": [{
                    "scenario_id": "GPT50_002",
                    "slot_id": "GPT50_002::policy",
                    "status": "machine_rejected",
                    "attempt": 1,
                    "trajectory_id": "trajectory-rejected",
                    "trajectory_file": "rejected.json",
                    "precheck": {
                        "candidate_classification": "machine_rejected",
                        "hard_reject_reasons": ["template_loop"],
                        "structural": {
                            "turn_count": 1,
                            "checks": {"distinct_turns": False},
                        },
                    },
                }],
            }), encoding="utf-8")
            records = [(
                scenario_path,
                {"scenario_id": "GPT50_002"},
                "valid",
                "",
            )]
            with (
                patch("web.server.GPT50_ROLLOUT_ROOT", root),
                patch(
                    "web.server._gpt50_scenario_records",
                    return_value=(scenario_path.parents[1], records, []),
                ),
            ):
                detail = load_gpt50_rollout("GPT50_002")
            self.assertEqual(detail["status"], "machine_rejected")
            self.assertEqual(detail["artifact_kind"], "rejected_or_partial")
            self.assertEqual(detail["turn_count"], 1)
            self.assertEqual(
                detail["turns"][0]["environment_response"],
                "Then start with the missing fact.",
            )
            self.assertEqual(
                detail["machine_review"]["hard_reject_reasons"],
                ["template_loop"],
            )
            self.assertEqual(
                detail["machine_review"]["false_checks"],
                ["distinct_turns"],
            )

    def test_gpt50_gate2_labels_evidence_without_deleting_or_failing_unsampled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.json").write_text(json.dumps({
                "mode": "prepare_only",
                "e1_review_items": 1,
            }), encoding="utf-8")
            (root / "state_transition_agreement.json").write_text(json.dumps({
                "record": {"review_status": "pending_human"},
                "review_items": [{
                    "scenario_id": "GPT50_001",
                    "review_id": "e1",
                }],
            }), encoding="utf-8")
            (root / "history_intervention.json").write_text(json.dumps({
                "record": {"machine_screen_passed": False},
                "records": [{
                    "scenario_id": "GPT50_001",
                    "automatic_screen_passed": False,
                }],
            }), encoding="utf-8")
            with patch("web.server.GPT50_GATE2_ROOT", root):
                packet = load_gpt50_gate2()
                detail = load_gpt50_gate2("GPT50_001")
                unsampled = load_gpt50_gate2("GPT50_050")
            self.assertEqual(packet["deletion_policy"], "retain_all_and_label")
            self.assertEqual(
                packet["by_scenario"]["GPT50_001"]["status"],
                "machine_flagged",
            )
            self.assertEqual(
                detail["scenario_overview"]["evidence_item_count"], 2
            )
            self.assertEqual(
                unsampled["scenario_overview"]["status"], "not_sampled"
            )
            e3 = next(
                item for item in detail["experiments"]
                if item["experiment_id"] == "E3"
            )
            self.assertEqual(
                e3["items"][0]["gate2_screen_status"], "machine_fail"
            )

    def test_gpt50_gate1_page_is_linked_from_review_center(self):
        review = Path("web/static/review.html").read_text(encoding="utf-8")
        page = Path("web/static/gpt50_gate1.html").read_text(encoding="utf-8")
        script = Path("web/static/gpt50_gate1.js").read_text(encoding="utf-8")
        self.assertIn('href="/gpt50_gate1.html"', review)
        self.assertIn('src="/gpt50_gate1.js?v=7"', page)
        self.assertIn("/api/gpt50-review", script)
        self.assertIn("GPT rollout 与 Gate 2 实时进度", script)
        self.assertIn("本轮结构化 appraisal 与状态变化", script)
        self.assertIn("Rollout 人工审查", script)
        self.assertIn("rollout_review", script)
        self.assertIn("被测模型扮演", script)
        self.assertIn("Gate 2 筛选复核", script)
        self.assertIn("gate2_review", script)
        self.assertIn("未抽中不等于失败", script)
        self.assertIn("setInterval", script)
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
