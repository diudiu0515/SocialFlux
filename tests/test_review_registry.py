import copy
import json
from pathlib import Path
import tempfile
import unittest

from evaluation.review_registry import (
    REQUIRED_ATTESTATIONS,
    REQUIRED_QUALITY_SCORES,
    file_sha256,
    validate_human_review,
)
from schemas.validate import QUALITY_CHECKS


class ScenarioReviewRegistryTest(unittest.TestCase):
    def test_review_is_bound_to_exact_human_frozen_file(self):
        scenario = {
            "scenario_id": "S1",
            "construction_status": {
                "quality_gate": "approved",
                "initial_state": "human_frozen",
            },
            "quality_gate": {key: "pass" for key in QUALITY_CHECKS},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.json"
            path.write_text(json.dumps(scenario), encoding="utf-8")
            record = {
                "scenario_id": "S1",
                "reviewer": "human-reviewer",
                "reviewed_at_utc": "2026-09-06T01:00:00Z",
                "scenario_sha256": file_sha256(path),
                "decision": "approved",
                "human_attestation": True,
                "attestations": {key: True for key in REQUIRED_ATTESTATIONS},
                "quality_scores": {key: 4 for key in REQUIRED_QUALITY_SCORES},
            }
            self.assertTrue(validate_human_review(scenario, path, {"S1": record}))
            path.write_text(json.dumps({**scenario, "changed": True}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "changed after"):
                validate_human_review(scenario, path, {"S1": record})

    def test_automated_or_incomplete_review_is_rejected(self):
        scenario = {
            "scenario_id": "S1",
            "construction_status": {
                "quality_gate": "approved",
                "initial_state": "human_frozen",
            },
            "quality_gate": {key: "pass" for key in QUALITY_CHECKS},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.json"
            path.write_text(json.dumps(scenario), encoding="utf-8")
            record = {
                "scenario_id": "S1",
                "reviewer": "model",
                "reviewed_at_utc": "2026-09-06T01:00:00Z",
                "scenario_sha256": file_sha256(path),
                "decision": "approved",
                "human_attestation": False,
                "attestations": {key: True for key in REQUIRED_ATTESTATIONS},
                "quality_scores": {key: 4 for key in REQUIRED_QUALITY_SCORES},
            }
            with self.assertRaisesRegex(ValueError, "not human-approved"):
                validate_human_review(scenario, path, {"S1": record})

    def test_below_threshold_human_quality_is_rejected(self):
        scenario = {
            "scenario_id": "S1",
            "construction_status": {"quality_gate": "approved", "initial_state": "human_frozen"},
            "quality_gate": {key: "pass" for key in QUALITY_CHECKS},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.json"
            path.write_text(json.dumps(scenario), encoding="utf-8")
            scores = {key: 4 for key in REQUIRED_QUALITY_SCORES}
            scores["history_necessity"] = 3
            record = {
                "scenario_id": "S1", "reviewer": "human-reviewer",
                "reviewed_at_utc": "2026-09-06T01:00:00Z",
                "scenario_sha256": file_sha256(path), "decision": "approved",
                "human_attestation": True,
                "attestations": {key: True for key in REQUIRED_ATTESTATIONS},
                "quality_scores": scores,
            }
            with self.assertRaisesRegex(ValueError, ">=4"):
                validate_human_review(scenario, path, {"S1": record})


if __name__ == "__main__":
    unittest.main()
