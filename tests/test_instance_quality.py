import json
from pathlib import Path
import unittest

from evaluation.instance_quality import (
    audit_trajectory,
    blind_instance_packet,
    build_instance_quality_report,
)
from offline.rollout_builders import (
    build_t1_checkpoints,
    build_t2_pairs,
    build_t3_candidates,
)
from rollout.counterfactual import branch_counterfactuals
from rollout.runner import RolloutRunner
from tests.support import TextPolicy, environment_factory


SCENARIO = json.loads(
    Path("configs/scenarios/scenario_001/scenario_001.json").read_text(encoding="utf-8")
)


class InstanceQualityTest(unittest.TestCase):
    def test_blind_packet_removes_model_and_trajectory_provenance(self):
        packet = blind_instance_packet({
            "instance_id": "source-id",
            "task_type": "T1_state_tracking",
            "language": "zh",
            "modality": "text",
            "input": {"history": []},
            "target_spec": {"target_state_ids": ["emotion.anger"]},
            "metadata": {"source_trajectory_id": "private-source"},
        })
        self.assertNotIn("instance_id", packet)
        self.assertNotIn("metadata", packet)
        self.assertEqual(packet["task_type"], "T1_state_tracking")

    def test_trajectory_audit_rejects_exact_response_repetition(self):
        trajectory = {
            "trajectory_id": "repeated",
            "policy_provenance": {"model": "test-model"},
            "turns": [
                {
                    "policy_action": {"text": f"行动 {index}"},
                    "environment_response": "重复回应" if index > 0 else "首次回应",
                    "state_after": {"emotion": {"anger": index}},
                }
                for index in range(5)
            ],
        }
        audit = audit_trajectory(trajectory)
        self.assertTrue(audit["passed"])
        self.assertFalse(audit["checks"]["responses_no_exact_repetition"])
        self.assertIn(
            "responses_no_exact_repetition", audit["check_groups"]["diagnostic"]
        )
        self.assertEqual(audit["diagnostics"]["action_unique_ratio"], 1.0)

    def test_audit_rejects_nested_question_churn_and_nonterminal_turn_20(self):
        actions = [
            f"我需要你说明第{index}个治理问题是否明确。"
            for index in range(1, 21)
        ]
        trajectory = {
            "trajectory_id": "question-churn",
            "policy_provenance": {"model": "test-model"},
            "public_scenario_context": {"environment_role": {"name": "程野"}},
            "turns": [
                {
                    "policy_action": {"text": action},
                    "environment_response": f"当前只回答第{index}个问题。",
                    "appraisal": {"speaker_intent": "被评估参与者继续追问"},
                    "state_after": {"emotion": {"anger": 5}},
                }
                for index, action in enumerate(actions, start=1)
            ],
        }
        audit = audit_trajectory(trajectory)
        self.assertFalse(audit["checks"]["actions_no_template_loop"])
        self.assertFalse(audit["checks"]["fixed_horizon_closes_naturally"])

    def test_existing_debt_erasure_is_a_hard_structural_failure(self):
        trajectory = {
            "trajectory_id": "debt-erasure",
            "policy_provenance": {"model": "test-model"},
            "turns": [
                {
                    "policy_action": {"text": (
                        "关于旧欠款，就让它自然留在过去吧。"
                        if index == 4 else f"我说明第{index + 1}点。"
                    )},
                    "environment_response": f"我回应第{index + 1}点。",
                    "state_after": {"emotion": {"anger": 5}},
                }
                for index in range(5)
            ],
        }
        audit = audit_trajectory(trajectory)
        self.assertFalse(audit["passed"])
        self.assertFalse(audit["checks"]["turns_preserve_existing_obligations"])
        self.assertIn(
            "turns_preserve_existing_obligations", audit["check_groups"]["hard"]
        )

    def test_incomplete_amount_arrangement_cannot_be_upgraded_in_trajectory(self):
        trajectory = {
            "trajectory_id": "proposal-upgrade",
            "policy_provenance": {"model": "test-model"},
            "turns": [{
                "observation": {"current_response": (
                    "14天内我确实能安排800元，这个节点可行。"
                    if index == 0 else "我们继续讨论。"
                )},
                "policy_action": {"text": (
                    "我认可这个首期安排。"
                    if index == 0 else f"我说明第{index + 1}点。"
                )},
                "environment_response": f"我回应第{index + 1}点。",
                "state_after": {"emotion": {"anger": 5}},
            } for index in range(5)],
        }
        audit = audit_trajectory(trajectory)
        self.assertFalse(audit["passed"])
        self.assertFalse(audit["checks"]["turns_preserve_proposal_strength"])
        self.assertIn(
            "turns_preserve_proposal_strength", audit["check_groups"]["hard"]
        )

    def test_public_transition_event_grounds_later_performance_amount(self):
        trajectory = {
            "trajectory_id": "public-event-grounding",
            "policy_provenance": {"model": "test-model"},
            "public_scenario_context": {
                "background": "朋友仍有欠款。",
                "public_situation": {},
            },
            "turns": [
                {
                    "policy_action": {"text": "那就先按约定执行。"},
                    "environment_response": "好，到节点再核对公开记录。",
                    "segment_transition_after": {
                        "public_events": [
                            {
                                "public": True,
                                "event_type": "commitment_performance",
                                "text": "公开转账记录显示：本节点约定600元，实际到账300元。",
                            }
                        ]
                    },
                },
                {
                    "policy_action": {"text": "这次实际还了300元，但执行仍不稳定。"},
                    "environment_response": "我理解你对执行稳定性的担忧。",
                },
            ],
        }
        audit = audit_trajectory(trajectory)
        self.assertTrue(audit["checks"]["performance_amounts_are_grounded"])

    def test_complete_rollout_derived_instances_pass_structural_audit(self):
        runner = RolloutRunner(environment_factory(SCENARIO))
        left = runner.run(
            TextPolicy("model-a-seed-1", ["请解释贡献证据。", "请继续解释证据。"]),
            max_turns=2,
        )
        right = runner.run(
            TextPolicy(
                "model-a-seed-2",
                ["我要追究责任。", "我会启动正式程序。"],
                seed=2,
            ),
            max_turns=2,
        )
        t1 = build_t1_checkpoints(left, SCENARIO["target_state_ids"])[0]
        shared = {
            "current_response": "我们先确认彼此掌握的事实。",
            "observable_cues": [],
            "observable_expression": {},
            "media": [],
        }
        t2 = build_t2_pairs(
            [left, right],
            lambda history_a, history_b, target, evaluated: shared,
            1,
            SCENARIO["target_state_ids"],
        )[0]
        turn = left["turns"][0]
        checkpoint = {
            **turn,
            "trajectory_id": left["trajectory_id"],
            "scenario_id": left["scenario_id"],
        }
        actions = [
            {"text": "请解释贡献证据。"},
            {"text": "我会启动正式程序追究责任。"},
        ]
        t3 = build_t3_candidates(
            checkpoint,
            actions,
            delayed_horizon=5,
            target_state_ids=SCENARIO["target_state_ids"],
        )
        branches = branch_counterfactuals(
            environment_factory(SCENARIO),
            turn,
            actions,
            lambda: TextPolicy("model-a-continuation", ["我们继续核对事实。"]),
            delayed_horizon=5,
        )
        for branch in branches:
            branch["source_trajectory_id"] = left["trajectory_id"]
        report = build_instance_quality_report(
            [t1, t2, t3],
            [left, right],
            branches,
        )
        self.assertEqual(report["instance_count"], 3)
        self.assertEqual(report["structurally_passed"], 3)
        self.assertEqual(report["mean_structural_score"], 1.0)
        self.assertEqual(
            set(report["by_source_model"]["test-model"]),
            {
                "T1_state_tracking",
                "T2_history_sensitive_merge",
                "T3_counterfactual_choice_effect",
            },
        )
        self.assertEqual(
            report["interpretation"]["comparison_status"],
            "requires matched-model rollouts and blind semantic review",
        )


if __name__ == "__main__":
    unittest.main()
