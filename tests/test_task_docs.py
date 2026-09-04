import tempfile
import unittest
from pathlib import Path

from scripts.task_docs import render_task_review, write_task_review


class TaskReviewDocumentTest(unittest.TestCase):
    def setUp(self):
        self.scenario = {
            "scenario_id": "IA_TEST",
            "title": "夜班交接",
            "environment_agent": {"persona": {"name": "林主管", "role": "值班主管"}},
        }
        observation = {
            "current_response": "先把事实说清楚。",
            "observable_expression": {
                "facial_expression": "皱眉", "gaze": "直视", "prosody": "克制"
            },
            "observable_cues": ["翻看记录"],
        }
        turn_a = {
            "turn_id": "t1",
            "state_before": {"emotion": {"trust": 3}},
            "state_after": {"emotion": {"trust": 5}},
            "dynamics_before": {"pressure": 6},
            "dynamics_after": {"pressure": 5},
        }
        turn_b = {
            "turn_id": "t2",
            "state_before": {"emotion": {"trust": 5}},
            "state_after": {"emotion": {"trust": 4}},
            "dynamics_before": {"pressure": 5},
            "dynamics_after": {"pressure": 6},
        }
        self.trajectories = [
            {"trajectory_id": "tr-a", "initial_state": {"emotion": {"trust": 3}}, "turns": [turn_a, turn_b]},
            {"trajectory_id": "tr-b", "initial_state": {"emotion": {"trust": 3}}, "turns": [turn_a, {**turn_b, "state_before": {"emotion": {"trust": 2}}}]},
        ]
        public_turn = {
            "turn_id": "t1",
            "policy_action": {"text": "我按记录逐项解释。"},
            "environment_response": "那就从第一项开始。",
        }
        target = {"target_character_id": "ENV", "target_state_ids": ["emotion.trust"]}
        self.instances = [
            {
                "instance_id": "t1-case", "task_type": "T1_state_tracking",
                "input": {"target_character_id": "ENV", "history": [public_turn], "current_checkpoint": observation},
                "target_spec": target, "metadata": {"source_trajectory_id": "tr-a"},
            },
            {
                "instance_id": "t2-case", "task_type": "T2_history_sensitive_merge",
                "input": {"history_a": [public_turn], "history_b": [{**public_turn, "policy_action": {"text": "你先别问。"}}], "shared_current_observation": observation},
                "target_spec": target, "metadata": {"source_trajectory_ids": ["tr-a", "tr-b"]},
            },
            {
                "instance_id": "t3-case", "task_type": "T3_counterfactual_choice_effect",
                "input": {"history": [{"turn_id": 1, "role": "environment_agent", "text": "解释一下。"}], "current_observation": observation, "candidate_actions": [{"text": "提交证据"}, {"text": "转移话题"}]},
                "target_spec": {**target, "delayed_horizon": 5},
                "metadata": {"source_trajectory_id": "tr-a", "checkpoint_turn_id": "t1"},
            },
        ]
        base_branch = {
            "source_trajectory_id": "tr-a", "checkpoint_turn_id": "t1",
            "state_before": {"emotion": {"trust": 3}},
            "state_after_immediate": {"emotion": {"trust": 4}},
            "state_after_delayed": {"emotion": {"trust": 6}},
            "dynamics_before": {"pressure": 6},
            "dynamics_after_immediate": {"pressure": 5},
            "dynamics_after_delayed": {"pressure": 3},
        }
        self.branches = [base_branch, {**base_branch, "state_after_delayed": {"emotion": {"trust": 1}}}]

    def test_document_explains_all_three_tasks_and_private_boundary(self):
        text = render_task_review(self.scenario, self.instances, self.trajectories, self.branches)
        self.assertIn("T1/T2/T3 人工抽查包", text)
        self.assertIn("## T1：当前状态跟踪", text)
        self.assertIn("## T2：历史敏感合流", text)
        self.assertIn("## T3：局部反事实 action 效果", text)
        self.assertIn("我按记录逐项解释", text)
        self.assertIn("共享当前观察", text)
        self.assertIn("提交证据", text)
        self.assertIn("即时状态", text)
        self.assertIn("不得作为模型输入或正式 GT", text)
        self.assertNotIn("尚未提取", text)

    def test_writer_places_deterministic_markdown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            write_task_review(path, self.scenario, self.instances, self.trajectories, self.branches)
            first = path.read_text(encoding="utf-8")
            write_task_review(path, self.scenario, self.instances, self.trajectories, self.branches)
            self.assertEqual(first, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
