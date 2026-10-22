import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.generate_long_rollout_pool import _scenario_fingerprint
from scripts.restore_valid_requeued_rollouts import restore_valid_requeued


class RestoreValidRequeuedRolloutsTest(unittest.TestCase):
    def test_dry_run_selects_only_accepted_current_scenario_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rollouts = root / "rollouts"
            scenarios = root / "scenarios"
            archived = (
                rollouts / "scenario_001" / "requeued_short_trajectories"
                / "trajectory.json"
            )
            archived.parent.mkdir(parents=True)
            scenario_dir = scenarios / "scenario_001"
            scenario_dir.mkdir(parents=True)
            scenario = {"scenario_id": "CF150_001", "title": "fixture"}
            (scenario_dir / "scenario_001.json").write_text(
                json.dumps(scenario), encoding="utf-8"
            )
            trajectory = {
                "trajectory_id": "trajectory",
                "policy_id": "policy",
                "scenario_fingerprint": _scenario_fingerprint(scenario),
                "turns": [{"turn_id": "t1"}] * 10,
            }
            archived.write_text(json.dumps(trajectory), encoding="utf-8")
            progress = {
                "expected_slot_count": 1,
                "completed_slots": {},
                "attempts": [{
                    "slot_id": "CF150_001::policy",
                    "trajectory_id": "trajectory",
                    "status": "accepted",
                    "planned_policy_id": "policy",
                    "finished_at_utc": "earlier",
                }],
                "requeue_history": [{"records": [{
                    "slot_id": "CF150_001::policy",
                    "scenario_id": "CF150_001",
                    "archived_to": (
                        "scenario_001/requeued_short_trajectories/trajectory.json"
                    ),
                }]}],
            }
            (rollouts / "progress.json").write_text(
                json.dumps(progress), encoding="utf-8"
            )
            with patch(
                "scripts.restore_valid_requeued_rollouts._machine_precheck",
                return_value={"passed": True, "candidate_classification": "main_candidate"},
            ):
                result = restore_valid_requeued(
                    rollouts, scenarios, dry_run=True
                )
            self.assertEqual(len(result["restored"]), 1)
            self.assertTrue(archived.exists())
            persisted = json.loads(
                (rollouts / "progress.json").read_text(encoding="utf-8")
            )
            self.assertEqual(persisted["completed_slots"], {})

    def test_fingerprint_mismatch_is_not_restored(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rollouts = root / "rollouts"
            scenarios = root / "scenarios" / "scenario_001"
            archived = (
                rollouts / "scenario_001" / "requeued_short_trajectories"
                / "trajectory.json"
            )
            archived.parent.mkdir(parents=True)
            scenarios.mkdir(parents=True)
            (scenarios / "scenario_001.json").write_text(
                json.dumps({"scenario_id": "CF150_001", "title": "new"}),
                encoding="utf-8",
            )
            archived.write_text(json.dumps({
                "trajectory_id": "trajectory",
                "scenario_fingerprint": "old",
            }), encoding="utf-8")
            (rollouts / "progress.json").write_text(json.dumps({
                "completed_slots": {},
                "attempts": [{
                    "slot_id": "CF150_001::policy",
                    "trajectory_id": "trajectory",
                    "status": "accepted",
                }],
                "requeue_history": [{"records": [{
                    "slot_id": "CF150_001::policy",
                    "scenario_id": "CF150_001",
                    "archived_to": (
                        "scenario_001/requeued_short_trajectories/trajectory.json"
                    ),
                }]}],
            }), encoding="utf-8")
            result = restore_valid_requeued(rollouts, root / "scenarios", dry_run=True)
            self.assertEqual(result["restored"], [])
            self.assertEqual(
                result["skipped"][0]["reason"], "scenario_fingerprint_mismatch"
            )


if __name__ == "__main__":
    unittest.main()
