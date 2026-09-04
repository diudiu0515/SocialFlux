import json
import tempfile
import unittest
from pathlib import Path

from scripts.merge_pipeline_outputs import merge_pipeline_outputs


class MergePipelineOutputsTest(unittest.TestCase):
    def _shard(self, root, scenario_id):
        scenario = root / scenario_id
        (scenario / "offline").mkdir(parents=True)
        instance = {
            "instance_id": f"{scenario_id}-t1",
            "story_id": scenario_id,
            "task_type": "T1_state_tracking",
            "input": {"history": []},
            "ground_truth": None,
        }
        (scenario / "offline" / "instances.jsonl").write_text(
            json.dumps(instance) + "\n", encoding="utf-8"
        )
        (scenario / "pipeline_manifest.json").write_text("{}", encoding="utf-8")
        summary = {
            "scenario_id": scenario_id, "trajectory_count": 3,
            "trajectory_origin": "free_form_model_interaction",
            "t1": 1, "t2": 0, "t3": 0,
        }
        manifest = {
            "format": "socialflux_pipeline_manifest_v2",
            "trajectory_origin": "free_form_model_interaction",
            "scenarios": [summary], "rollout_config": {"shard": scenario_id},
        }
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_merges_scenarios_instances_and_totals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            left, right, output = root / "left", root / "right", root / "out"
            left.mkdir(); right.mkdir()
            self._shard(left, "IA_PIPE_001")
            self._shard(right, "IA_PIPE_002")
            result = merge_pipeline_outputs([left, right], output)
            self.assertEqual(result["scenario_count"], 2)
            self.assertEqual(result["totals"]["trajectories"], 6)
            self.assertEqual(result["totals"]["instances"], 2)
            self.assertTrue((output / "IA_PIPE_001" / "pipeline_manifest.json").exists())
            self.assertEqual(len((output / "instances.jsonl").read_text().splitlines()), 2)

    def test_recovers_completed_scenarios_when_shard_manifest_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shard = root / "interrupted"
            shard.mkdir()
            self._shard(shard, "IA_PIPE_001")
            (shard / "manifest.json").unlink()
            summary_path = shard / "IA_PIPE_001" / "pipeline_manifest.json"
            summary_path.write_text(json.dumps({
                "scenario_id": "IA_PIPE_001",
                "trajectory_origin": "free_form_model_interaction",
                "trajectory_count": 3, "t1": 1, "t2": 0, "t3": 0,
            }), encoding="utf-8")
            result = merge_pipeline_outputs([shard], root / "out")
            self.assertEqual(result["scenario_count"], 1)
            self.assertEqual(result["totals"]["instances"], 1)

    def test_rejects_duplicate_scenarios(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            left, right = root / "left", root / "right"
            left.mkdir(); right.mkdir()
            self._shard(left, "IA_PIPE_001")
            self._shard(right, "IA_PIPE_001")
            with self.assertRaisesRegex(ValueError, "duplicate scenario"):
                merge_pipeline_outputs([left, right], root / "out")


if __name__ == "__main__":
    unittest.main()
