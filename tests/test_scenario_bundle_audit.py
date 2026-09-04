import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_scenario_bundles import audit_scenario_bundle


class ScenarioBundleAuditTest(unittest.TestCase):
    def _bundle(self, root):
        scenario_dir = root / "configs" / "scenario_001"
        rollout = scenario_dir / "rollouts"
        pipeline = root / "pipeline" / "IA_TEST"
        rollout.mkdir(parents=True)
        (pipeline / "offline").mkdir(parents=True)
        (pipeline / "validation").mkdir(parents=True)
        scenario_path = scenario_dir / "scenario_001.json"
        scenario_path.write_text(json.dumps({"scenario_id": "IA_TEST"}), encoding="utf-8")
        (rollout / "manifest.json").write_text(json.dumps({
            "config": {"origin": "free_form_model_interaction"},
            "trajectory_ids": ["a", "b"], "trajectory_count": 2,
        }), encoding="utf-8")
        for trajectory_id in ("a", "b"):
            (rollout / f"{trajectory_id}.json").write_text("{}", encoding="utf-8")
        (rollout / "dialogues.md").write_text(
            "# Free-form Rollout Dialogues\n**Evaluated model:** x\n**Environment character:** y",
            encoding="utf-8",
        )
        instances = [
            {"instance_id": "one", "task_type": "T1_state_tracking"},
            {"instance_id": "two", "task_type": "T2_history_sensitive_merge"},
            {
                "instance_id": "three",
                "task_type": "T3_counterfactual_choice_effect",
                "input": {
                    "candidate_actions": [
                        {"text": "a"},
                        {"text": "b"},
                        {"text": "c"},
                    ]
                },
            },
        ]
        (pipeline / "offline" / "instances.jsonl").write_text(
            "\n".join(json.dumps(item) for item in instances) + "\n", encoding="utf-8"
        )
        (pipeline / "validation" / "local_action_interventions.json").write_text(
            json.dumps([{}, {}, {}]), encoding="utf-8"
        )
        (rollout / "tasks.md").write_text(
            "## T1：当前状态跟踪\none\n## T2：历史敏感合流\ntwo\n"
            "## T3：局部反事实 action 效果\nthree\n不得作为模型输入或正式 GT",
            encoding="utf-8",
        )
        return scenario_path, root / "pipeline", pipeline

    def test_complete_bundle_is_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            scenario, pipeline_root, _ = self._bundle(Path(directory))
            result = audit_scenario_bundle(scenario, pipeline_root)
            self.assertTrue(result["ready_for_human_spot_check"])
            self.assertEqual(result["task_counts"]["T2_history_sensitive_merge"], 1)

    def test_missing_task_is_not_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            scenario, pipeline_root, pipeline = self._bundle(Path(directory))
            instances = pipeline / "offline" / "instances.jsonl"
            instances.write_text("{\"instance_id\":\"one\",\"task_type\":\"T1_state_tracking\"}\n", encoding="utf-8")
            result = audit_scenario_bundle(scenario, pipeline_root)
            self.assertFalse(result["ready_for_human_spot_check"])
            self.assertFalse(result["checks"]["t2_present"])


if __name__ == "__main__":
    unittest.main()
