import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from evaluation.review_registry import load_review_registry, validate_human_review
from scripts.apply_gpt50_gate1 import apply_review
from scripts.scenario_docs import write_document


class ApplyGpt50Gate1Test(unittest.TestCase):
    def _fixture(self, root):
        source = Path("data/gpt50/experiment/scenario/scenarios/scenario_001/scenario_001.json")
        scenario = json.loads(source.read_text(encoding="utf-8"))
        scenario["construction_status"]["quality_gate"] = "pending_human_review"
        scenario["construction_status"]["initial_state"] = (
            "candidate_pending_human_freeze"
        )
        scenario["quality_gate"] = {
            key: "pass" for key in scenario["quality_gate"]
        }
        target = root / "scenario_001" / "scenario_001.json"
        target.parent.mkdir(parents=True)
        target.write_text(
            json.dumps(scenario, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        write_document(target)
        return target, scenario

    def _draft(self, target, scenario_id):
        return {
            "format": "socialflux_gpt50_gate1_browser_export_v1",
            "records": [{
                "record_type": "gpt50_gate1",
                "scenario_id": scenario_id,
                "reviewer": "human-reviewer",
                "reviewed_at_utc": "2026-09-19T12:00:00Z",
                "scenario_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "decision": "approved",
                "human_attestation": True,
                "attestations": {
                    "variables_relevant": True,
                    "values_justified": True,
                    "no_policy_effect_baked_in": True,
                    "initial_triggers_inactive": True,
                    "multiple_future_paths_possible": True,
                    "shared_across_models_and_seeds": True,
                },
                "quality_scores": {
                    "social_plausibility": 4,
                    "character_coherence": 4,
                    "tradeoff_quality": 4,
                    "history_necessity": 4,
                    "interaction_richness": 4,
                    "t1_t4_suitability": 4,
                },
                "notes": "human reviewed",
            }],
        }

    def test_applies_human_freeze_and_writes_valid_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "scenarios"
            target, scenario = self._fixture(root)
            draft_path = Path(directory) / "draft.json"
            draft_path.write_text(
                json.dumps(self._draft(target, scenario["scenario_id"])),
                encoding="utf-8",
            )
            output = Path(directory) / "review.signed.json"
            result = apply_review(draft_path, root, output)
            self.assertEqual(result["approved"], 1)
            frozen = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(
                frozen["construction_status"]["quality_gate"], "approved"
            )
            self.assertEqual(
                frozen["construction_status"]["initial_state"], "human_frozen"
            )
            registry = load_review_registry(output)
            self.assertTrue(validate_human_review(frozen, target, registry))
            self.assertEqual(
                registry[scenario["scenario_id"]]["scenario_sha256"],
                hashlib.sha256(target.read_bytes()).hexdigest(),
            )

    def test_rejects_stale_browser_hash_before_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "scenarios"
            target, scenario = self._fixture(root)
            draft = self._draft(target, scenario["scenario_id"])
            draft["records"][0]["scenario_sha256"] = "0" * 64
            draft_path = Path(directory) / "draft.json"
            draft_path.write_text(json.dumps(draft), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "changed after browser review"):
                apply_review(draft_path, root, Path(directory) / "review.json")
            unchanged = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(
                unchanged["construction_status"]["quality_gate"],
                "pending_human_review",
            )


if __name__ == "__main__":
    unittest.main()
