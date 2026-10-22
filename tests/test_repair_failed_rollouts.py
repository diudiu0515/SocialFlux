import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.repair_failed_rollouts import (
    _archived_gate_ids,
    _bundle_gate_ids,
    _gate_rejected_ids,
    _generate_clean,
    _merge_candidate_judgments,
    _replacement_policy_lookup,
)


class RepairFailedRolloutsTest(unittest.TestCase):
    def test_bundle_gate_ids_scope_active_and_archived_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "scenario_001"
            rejected = root / "rollouts" / "rejected"
            rejected.mkdir(parents=True)
            (root / "scenario_001.json").write_text("{}", encoding="utf-8")
            (root / "rollouts" / "manifest.json").write_text(
                json.dumps({"trajectory_ids": ["active"]}), encoding="utf-8"
            )
            (rejected / "manifest.json").write_text(
                json.dumps([{"old_trajectory_id": "archived"}]), encoding="utf-8"
            )
            self.assertEqual(
                _bundle_gate_ids([(root / "scenario_001.json", {})]),
                {"active", "archived"},
            )

    def test_extracts_only_gate_three_rejected_ids(self):
        payload = {
            "gates": {
                "gate_3_rollout_quality": {
                    "audits": [
                        {"trajectory_id": "reject-me", "status": "rejected"},
                        {"trajectory_id": "wait-for-evidence", "status": "pending_evidence"},
                        {"trajectory_id": "keep-me", "status": "passed"},
                    ]
                }
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gate.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(_gate_rejected_ids(path), {"reject-me"})

    def test_archived_gate_ids_support_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            scenario_dir = Path(directory) / "scenario_001"
            rejected = scenario_dir / "rollouts" / "rejected"
            rejected.mkdir(parents=True)
            scenario_path = scenario_dir / "scenario_001.json"
            scenario_path.write_text("{}", encoding="utf-8")
            (rejected / "manifest.json").write_text(
                json.dumps([
                    {
                        "old_trajectory_id": "gate-reject",
                        "selection_reason": "four_gate_rejected",
                    },
                    {
                        "old_trajectory_id": "machine-reject",
                        "selection_reason": "machine_structure_rejected",
                    },
                ]),
                encoding="utf-8",
            )
            self.assertEqual(
                _archived_gate_ids([(scenario_path, {})]),
                {"gate-reject"},
            )

    def test_generate_clean_retries_primary_judge_rejection(self):
        trajectories = [
            {"trajectory_id": "semantic-reject"},
            {"trajectory_id": "semantic-keep"},
        ]
        config = {
            "environment": {"provider": {}, "sampling": {}},
            "pilot_limits": {"rollout_turns": 20},
        }
        spec = {"policy_id": "policy", "sampling": {}}
        judged = []
        attempts_seen = []

        def quality_judge(trajectory, scenario):
            judged.append(trajectory["trajectory_id"])
            return {"trajectory_id": trajectory["trajectory_id"]}

        with (
            patch("scripts.repair_failed_rollouts.ModelEnvironmentFactory"),
            patch("scripts.repair_failed_rollouts.build_policy", return_value=object()),
            patch("scripts.repair_failed_rollouts.RolloutRunner") as runner_class,
            patch("scripts.repair_failed_rollouts.audit_trajectory", return_value={"passed": True}),
            patch(
                "scripts.repair_failed_rollouts.audit_rollout",
                side_effect=[
                    {"status": "rejected"},
                    {"status": "pending_evidence"},
                ],
            ),
        ):
            runner_class.return_value.run.side_effect = trajectories
            trajectory, attempts, judgment = _generate_clean(
                {"scenario_id": "scenario"},
                config,
                spec,
                0,
                2,
                quality_judge,
                attempt_recorder=attempts_seen.append,
            )
        self.assertEqual(trajectory["trajectory_id"], "semantic-keep")
        self.assertEqual(attempts, 2)
        self.assertEqual(judgment["primary"]["trajectory_id"], "semantic-keep")
        self.assertIsNone(judgment["secondary"])
        self.assertEqual(judged, ["semantic-reject", "semantic-keep"])
        self.assertEqual(
            [item["status"] for item in attempts_seen],
            ["semantic_rejected", "accepted"],
        )

    def test_candidate_judgments_are_merged_conservatively(self):
        primary = {
            "trajectory_id": "trajectory",
            "scores": {"naturalness": 5, "history_dependence": 4},
            "hard_reject_reasons": [],
            "rationale": "primary rationale",
        }
        secondary = {
            "trajectory_id": "trajectory",
            "scores": {"naturalness": 3, "history_dependence": 4},
            "hard_reject_reasons": ["repetitive_loop"],
            "rationale": "secondary rationale",
        }
        merged = _merge_candidate_judgments(primary, secondary)
        self.assertEqual(merged["scores"], {"naturalness": 4.0, "history_dependence": 4.0})
        self.assertEqual(merged["hard_reject_reasons"], ["repetitive_loop"])
        self.assertIn("primary rationale", merged["rationale"])
        self.assertIn("secondary rationale", merged["rationale"])

    def test_replacement_policy_slots_map_from_original_ids(self):
        original = {
            "policies": [
                {"policy_id": "old-a", "runs": 1},
                {"policy_id": "old-b", "runs": 1},
            ]
        }
        replacement = {
            "policies": [
                {"policy_id": "new-a", "runs": 1},
                {"policy_id": "new-b", "runs": 1},
            ]
        }
        lookup = _replacement_policy_lookup(original, replacement)
        self.assertEqual(lookup["old-a"][0]["policy_id"], "new-a")
        self.assertEqual(lookup["old-b"][0]["policy_id"], "new-b")
        self.assertEqual(lookup["new-a"][0]["policy_id"], "new-a")
        self.assertEqual(lookup["new-b"][0]["policy_id"], "new-b")

    def test_missing_gate_three_audits_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gate.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "lacks Gate 3"):
                _gate_rejected_ids(path)


if __name__ == "__main__":
    unittest.main()
