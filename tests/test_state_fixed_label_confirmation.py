import json
from pathlib import Path
import tempfile
import unittest

from rollout.configuration import load_rollout_config
from scripts.confirm_state_fixed_labels import (
    DEFAULT_MANIFEST,
    DEFAULT_PACKET,
    build_confirmed_manifest,
)
from scripts.run_state_judgment_primary_fixed_validation import (
    DEFAULT_CONFIG,
    DEFAULT_INTERFACE_AUDIT,
    summarize,
    validate_inputs,
)


class StateFixedLabelConfirmationTest(unittest.TestCase):
    def make_export(self, path):
        manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        packet = json.loads(DEFAULT_PACKET.read_text(encoding="utf-8"))
        annotations = {}
        for case in manifest["cases"]:
            is_new = case["expected_judgment"] in {
                "ordinary_new_evidence", "decisive_new_evidence"
            }
            annotations[case["case_id"]] = {
                "status": "complete",
                "judgment": case["expected_judgment"],
                "direction": case["expected_direction"],
                "evidence_span": case["latest_action"][:12] if is_new else "",
                "directness": "direct" if is_new else None,
                "evidence_feature": None,
                "should_update_this_turn": (
                    "yes" if case["requires_nonzero_final_update"] else "no"
                ),
                "suggested_delta": (
                    "moderate_increase"
                    if case["requires_nonzero_final_update"] else "similar"
                ),
                "rationale": "Independent human rationale.",
                "confidence_1_to_5": 4,
                "label_is_ambiguous": "no",
                "ambiguity_note": "",
                "reviewer_note": "",
            }
        value = {
            "format": "socialflux_state_human_annotations_v1",
            "round_id": packet["round_id"],
            "packet_sha256": packet["packet_sha256"],
            "reviewer": "unit-test-reviewer",
            "exported_at_utc": "2026-10-04T00:00:00+00:00",
            "annotations": annotations,
        }
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return value

    def test_complete_export_becomes_human_confirmed_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            export = Path(directory) / "annotations.json"
            self.make_export(export)
            result = build_confirmed_manifest(DEFAULT_MANIFEST, DEFAULT_PACKET, export)
        self.assertEqual(result["status"], "human_labels_complete")
        self.assertEqual(result["human_confirmation"]["confirmed_case_count"], 8)
        self.assertEqual(result["human_confirmation"]["ambiguous_case_ids"], [])
        self.assertEqual(len(result["cases"]), 8)
        self.assertTrue(all(case["adjudicated_label"] for case in result["cases"]))

    def test_final_update_opinion_is_optional_human_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            export = Path(directory) / "annotations.json"
            value = self.make_export(export)
            for annotation in value["annotations"].values():
                annotation.pop("should_update_this_turn", None)
            export.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            result = build_confirmed_manifest(DEFAULT_MANIFEST, DEFAULT_PACKET, export)
        self.assertTrue(all(
            case["adjudicated_label"]["reviewer_update_opinion"] is None
            for case in result["cases"]
        ))

    def test_pending_or_nonverbatim_export_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            export = Path(directory) / "annotations.json"
            value = self.make_export(export)
            first = next(iter(value["annotations"].values()))
            first["status"] = "pending"
            export.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not complete"):
                build_confirmed_manifest(DEFAULT_MANIFEST, DEFAULT_PACKET, export)

            first["status"] = "complete"
            first["evidence_span"] = "not present in the target action"
            export.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not verbatim"):
                build_confirmed_manifest(DEFAULT_MANIFEST, DEFAULT_PACKET, export)

    def test_v7_runner_accepts_only_confirmed_labels_and_audited_interface(self):
        with tempfile.TemporaryDirectory() as directory:
            export = Path(directory) / "annotations.json"
            self.make_export(export)
            confirmed = build_confirmed_manifest(
                DEFAULT_MANIFEST, DEFAULT_PACKET, export
            )
        config = load_rollout_config(DEFAULT_CONFIG)
        audit = json.loads(DEFAULT_INTERFACE_AUDIT.read_text(encoding="utf-8"))
        validate_inputs(confirmed, config, audit)

        pending = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        with self.assertRaisesRegex(ValueError, "human-confirmed"):
            validate_inputs(pending, config, audit)

    def test_summary_reports_false_positives_separately(self):
        rows = [{
            "case_id": "x",
            "result": {
                "status": "completed",
                "evaluation": {
                    "variable_recognition_pass": False,
                    "judgment_classification_pass": False,
                    "evidence_strength_pass": False,
                    "false_positive": True,
                    "false_negative": False,
                    "final_update_integrity_pass": True,
                    "call_completeness_pass": True,
                },
            },
        }]
        result = summarize(rows)
        self.assertEqual(result["false_positive_count"], 1)
        self.assertEqual(result["false_negative_count"], 0)
        self.assertEqual(result["call_completeness"], {"passed": 1, "total": 1})


if __name__ == "__main__":
    unittest.main()
