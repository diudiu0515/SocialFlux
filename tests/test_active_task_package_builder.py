import unittest

from tasks.package_builder import TaskPackageBuilder


class ActiveTaskPackageBuilderTest(unittest.TestCase):
    def test_resume_can_attach_t2_without_rebuilding_other_tasks(self):
        t2_result = {
            "status": "completed",
            "pair": {
                "source_a": {"trajectory_id": "trajectory-1"},
                "model_pair_review": {"decision": "approve"},
                "model_answer_review": {"decision": "approve"},
                "instance": {
                    "instance_id": "t2-1",
                    "input": {"history_a": [], "history_b": []},
                },
                "llm_answer": {"instance_id": "t2-1", "predictions": []},
                "answer_provenance": {
                    "model": "claude-fable-5",
                    "request_count": 2,
                },
            },
        }
        builder = TaskPackageBuilder(
            ".",
            model_routes=None,
            t2_results={7: t2_result},
        )
        package = {
            "ordinal": 7,
            "source_trajectory_id": "trajectory-1",
            "status": "constructed_partial_machine_proposals",
            "tasks": {
                "T1": {"status": "kept"},
                "T3": {"status": "kept"},
                "T4": {"status": "kept"},
            },
            "task_statuses": {"T1": "kept", "T3": "kept", "T4": "kept"},
            "task_gaps": {"T2": {"reason": "source_adapted_pair_unavailable"}},
            "task_errors": {},
            "request_count": 9,
        }
        updated = builder.attach_t2(package)
        self.assertNotIn("T2", package["tasks"])
        self.assertEqual(updated["tasks"]["T1"], {"status": "kept"})
        self.assertIn("T2", updated["tasks"])
        self.assertNotIn("T2", updated["task_gaps"])
        self.assertEqual(
            updated["status"], "constructed_all_task_machine_proposals",
        )
        self.assertEqual(updated["request_count"], 9)
        self.assertEqual(updated["t2_attachment"]["source_request_count"], 2)

    def test_resume_does_not_attach_mismatched_source(self):
        builder = TaskPackageBuilder(
            ".",
            model_routes=None,
            t2_results={1: {
                "status": "completed",
                "pair": {
                    "source_a": {"trajectory_id": "other"},
                    "model_pair_review": {"decision": "approve"},
                    "model_answer_review": {"decision": "approve"},
                },
            }},
        )
        package = {
            "ordinal": 1,
            "source_trajectory_id": "current",
            "tasks": {},
        }
        self.assertEqual(builder.attach_t2(package), package)


if __name__ == "__main__":
    unittest.main()
