import unittest

from scripts.merge_history_dependence import merge_records


class MergeHistoryDependenceTests(unittest.TestCase):
    def test_targeted_record_replaces_removed_trajectory_evidence(self):
        base = {"records": [
            {"trajectory_id": "old", "passed": False},
            {"trajectory_id": "keep", "passed": True},
        ]}
        patch = {"records": [{"trajectory_id": "new", "passed": True}]}
        records = merge_records({"keep", "new"}, [base, patch])
        self.assertEqual(
            [record["trajectory_id"] for record in records],
            ["keep", "new"],
        )

    def test_missing_active_trajectory_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing active trajectories"):
            merge_records({"required"}, [{"records": []}])


if __name__ == "__main__":
    unittest.main()
