import json
from pathlib import Path
import tempfile
import unittest

from evaluation.quality_gates import TASK_REVIEW_RATINGS, audit_task_instance_gate
from evaluation.rollout_gate import content_sha256


class TaskReviewGateTest(unittest.TestCase):
    def _review(self, reviewer, ratings, status="approved"):
        return {
            "reviewer": reviewer,
            "reviewed_at_utc": "2026-09-06T02:00:00Z",
            "review_status": status,
            "human_attestation": True,
            "ratings": ratings,
            "notes": "",
        }

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

    def test_two_distinct_reviewers_receive_same_deterministic_sample(self):
        instance = {"instance_id": "i1", "task_type": "T1_state_tracking", "metadata": {"source_trajectory_id": "t1"}}
        ratings = {key: True for key in TASK_REVIEW_RATINGS["T1_state_tracking"]}
        record = {
            "instance_id": "i1",
            "instance_sha256": content_sha256(instance),
            "reviews": {
                "reviewer_a": self._review("human-a", ratings),
                "reviewer_b": self._review("human-b", ratings),
            },
            "adjudication": {},
        }
        payload = {
            "format": "socialflux_gate4_double_audit_v2",
            "sampling": {
                "fraction_per_task_type": 0.1,
                "minimum_per_task_type": 2,
                "same_sample_for_both_reviewers": True,
            },
            "records": [record],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = audit_task_instance_gate([instance], [], human_review_path=path)
            self.assertEqual(result["checks"]["independent_or_human_semantic_review"]["status"], "pass")
            self.assertEqual(result["human_review_audit"]["sample_size"], 1)
            record["reviews"]["reviewer_b"]["reviewer"] = "human-a"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = audit_task_instance_gate([instance], [], human_review_path=path)
            self.assertEqual(result["checks"]["independent_or_human_semantic_review"]["status"], "pending")

    def test_disagreement_requires_distinct_third_adjudicator(self):
        instance = {"instance_id": "i1", "task_type": "T1_state_tracking", "metadata": {"source_trajectory_id": "t1"}}
        approved = {key: True for key in TASK_REVIEW_RATINGS["T1_state_tracking"]}
        rejected = dict(approved)
        rejected["current_only_insufficient"] = False
        record = {
            "instance_id": "i1",
            "instance_sha256": content_sha256(instance),
            "reviews": {
                "reviewer_a": self._review("human-a", approved),
                "reviewer_b": self._review("human-b", rejected, "rejected"),
            },
            "adjudication": {},
        }
        payload = {
            "format": "socialflux_gate4_double_audit_v2",
            "sampling": {"fraction_per_task_type": 0.1, "minimum_per_task_type": 2, "same_sample_for_both_reviewers": True},
            "records": [record],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = audit_task_instance_gate([instance], [], human_review_path=path)
            self.assertEqual(result["checks"]["independent_or_human_semantic_review"]["status"], "pending")
            record["adjudication"] = self._review("human-c", approved)
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = audit_task_instance_gate([instance], [], human_review_path=path)
            self.assertEqual(result["checks"]["independent_or_human_semantic_review"]["status"], "pass")


if __name__ == "__main__":
    unittest.main()
