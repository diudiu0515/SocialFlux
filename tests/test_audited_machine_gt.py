import unittest

from annotation.audited_machine_gt import FORMAT, LABEL_STATUS, release_audited_machine_labels
from evaluation.rollout_gate import content_sha256


class AuditedMachineGroundTruthTest(unittest.TestCase):
    def setUp(self):
        self.instance = {"instance_id": "i1", "task_type": "T1_state_tracking", "metadata": {"source_trajectory_id": "t1"}}
        self.proposals = {
            "format": "socialflux_machine_task_proposals_v1",
            "population_count": 1,
            "records": [{
                "instance_id": "i1",
                "instance_sha256": content_sha256(self.instance),
                "proposal": {"status": "machine_proposal_not_ground_truth", "labels": {"emotion.anger": 2}, "evidence": ["t6"]},
            }],
        }
        self.report = {
            "research_ready": True,
            "gates": {"gate_4_task_instance_quality": {
                "passed": True,
                "instance_count": 1,
                "human_review_audit": {"passed": True, "sample_size": 1, "pending_instance_ids": [], "rejected_instance_ids": []},
            }},
        }

    def test_releases_complete_hash_bound_proposals(self):
        result = release_audited_machine_labels([self.instance], self.proposals, self.report)
        self.assertEqual(result["format"], FORMAT)
        self.assertEqual(result["records"][0]["label_status"], LABEL_STATUS)
        self.assertNotIn("status", result["records"][0]["ground_truth"])

    def test_rejects_pending_human_audit(self):
        self.report["gates"]["gate_4_task_instance_quality"]["human_review_audit"]["passed"] = False
        with self.assertRaisesRegex(ValueError, "completed"):
            release_audited_machine_labels([self.instance], self.proposals, self.report)

    def test_rejects_hash_mismatch(self):
        self.proposals["records"][0]["instance_sha256"] = "wrong"
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            release_audited_machine_labels([self.instance], self.proposals, self.report)


if __name__ == "__main__":
    unittest.main()
