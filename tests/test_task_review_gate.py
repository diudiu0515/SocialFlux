import json
from pathlib import Path
import tempfile
import unittest

from evaluation.quality_gates import TASK_REVIEW_RATINGS, audit_task_instance_gate
from evaluation.rollout_gate import content_sha256


class TaskReviewGateTest(unittest.TestCase):
    def test_human_review_must_be_named_timestamped_and_hash_bound(self):
        instance = {"instance_id": "i1", "task_type": "T1_state_tracking", "metadata": {"source_trajectory_id": "t1"}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reviews.jsonl"
            base = {"instance_id": "i1", "review_status": "approved", "human_attestation": True, "reviewer": "human", "reviewed_at_utc": "2026-09-06T02:00:00Z", "instance_sha256": "wrong", "ratings": {key: True for key in TASK_REVIEW_RATINGS["T1_state_tracking"]}}
            path.write_text(json.dumps(base) + "\n", encoding="utf-8")
            result = audit_task_instance_gate([instance], [], human_review_path=path)
            self.assertEqual(result["checks"]["independent_or_human_semantic_review"]["status"], "pending")
            base["instance_sha256"] = content_sha256(instance)
            path.write_text(json.dumps(base) + "\n", encoding="utf-8")
            result = audit_task_instance_gate([instance], [], human_review_path=path)
            self.assertEqual(result["checks"]["independent_or_human_semantic_review"]["status"], "pass")
            base["ratings"]["current_only_insufficient"] = False
            path.write_text(json.dumps(base) + "\n", encoding="utf-8")
            result = audit_task_instance_gate([instance], [], human_review_path=path)
            self.assertEqual(result["checks"]["independent_or_human_semantic_review"]["status"], "pending")


if __name__ == "__main__":
    unittest.main()
