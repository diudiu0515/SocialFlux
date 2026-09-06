import unittest

from scripts.merge_rollout_quality_evidence import merge_evidence


def _payload(records, model="judge-a"):
    return {
        "format": "socialflux_rollout_quality_judgments_v1",
        "judge_role": "primary",
        "model": model,
        "model_family": "family-a",
        "provider": {"provider": "fake", "model": model},
        "sampling": {"seed": 1},
        "records": records,
    }


class MergeRolloutQualityEvidenceTests(unittest.TestCase):
    def test_patch_replaces_removed_id_and_exactly_covers_active_pool(self):
        base = _payload([
            {"trajectory_id": "old", "scores": {}},
            {"trajectory_id": "keep", "scores": {}},
        ])
        patch = _payload([{"trajectory_id": "new", "scores": {}}])
        result = merge_evidence({"keep", "new"}, [base, patch])
        self.assertEqual(
            [record["trajectory_id"] for record in result["records"]],
            ["keep", "new"],
        )

    def test_mismatched_judge_metadata_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "metadata"):
            merge_evidence(
                {"x"},
                [_payload([{"trajectory_id": "x"}]), _payload([], model="judge-b")],
            )


if __name__ == "__main__":
    unittest.main()
