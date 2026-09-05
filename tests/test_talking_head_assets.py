import json
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "media" / "talking_head"


class TalkingHeadAssetTest(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(
            (MEDIA / "manifest.json").read_text(encoding="utf-8")
        )

    def test_manifest_covers_two_triggers_for_all_scenarios(self):
        assets = self.manifest["assets"]
        self.assertEqual(self.manifest["format"], "socialflux_talking_head_assets_v1")
        self.assertEqual(self.manifest["asset_count"], 40)
        self.assertEqual(len(assets), 40)
        self.assertEqual(len({item["asset_id"] for item in assets}), 40)
        counts = Counter(item["scenario_id"] for item in assets)
        self.assertEqual(len(counts), 20)
        self.assertTrue(all(count == 2 for count in counts.values()))

    def test_requests_obey_public_information_boundary(self):
        expected_keys = {
            "prompt",
            "duration_seconds",
            "continuity_reference",
            "safety_check",
        }
        expected_safety = {
            "contains_private_state": False,
            "contains_threshold_logic": False,
            "contains_benchmark_answer": False,
        }
        forbidden = (
            "initial_state",
            "initial_dynamics",
            "hidden_intention",
            "state_delta",
            "appraisal",
        )
        for asset in self.manifest["assets"]:
            request_path = ROOT / asset["request_path"]
            request = json.loads(request_path.read_text(encoding="utf-8"))
            self.assertEqual(set(request), expected_keys)
            self.assertEqual(request["safety_check"], expected_safety)
            self.assertTrue(3 <= request["duration_seconds"] <= 8)
            serialized = json.dumps(request, ensure_ascii=False).lower()
            self.assertFalse(any(field in serialized for field in forbidden))

    def test_generated_metadata_is_complete_when_present(self):
        for asset in self.manifest["assets"]:
            if asset["status"] != "generated":
                continue
            self.assertTrue(asset.get("has_video"))
            self.assertTrue(asset.get("has_audio"))
            self.assertEqual(asset.get("width"), 768)
            self.assertEqual(asset.get("height"), 768)
            self.assertTrue(asset.get("duration_matches_request"))
            self.assertEqual(len(asset.get("video_sha256", "")), 64)
            self.assertTrue(3 <= asset["duration_seconds_actual"] <= 8)


