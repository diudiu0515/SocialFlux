import json
import unittest
from collections import Counter
from pathlib import Path

from scripts.prepare_talking_head_assets import prosody_controls


ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "media" / "talking_head"


class TalkingHeadAssetTest(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(
            (MEDIA / "manifest.json").read_text(encoding="utf-8")
        )

    def test_manifest_covers_three_triggers_for_all_scenarios(self):
        assets = self.manifest["assets"]
        self.assertEqual(self.manifest["format"], "socialflux_talking_head_assets_v2")
        self.assertEqual(self.manifest["asset_count"], 60)
        self.assertEqual(len(assets), 60)
        self.assertEqual(len({item["asset_id"] for item in assets}), 60)
        counts = Counter(item["scenario_id"] for item in assets)
        self.assertEqual(len(counts), 20)
        self.assertTrue(all(count == 3 for count in counts.values()))

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

    def test_role_conditioned_voice_profiles_cover_all_scenarios(self):
        config = json.loads(
            (ROOT / "configs" / "talking_head_voice_profiles.json").read_text(encoding="utf-8")
        )
        profiles = config["profiles"]
        self.assertEqual(set(profiles), {f"IA_PIPE_{i:03d}" for i in range(1, 21)})
        self.assertGreaterEqual(len({item["voice"] for item in profiles.values()}), 5)
        self.assertEqual(config["sample_rate_hz"], 24000)
        self.assertLessEqual(config["lead_silence_ms"], 120)
        self.assertLessEqual(config["tail_silence_ms"], 450)
        self.assertEqual(config["minimum_duration_seconds"], 3.0)
        self.assertEqual(config["maximum_duration_seconds"], 8.0)

    def test_every_trigger_gets_bounded_nonuniform_prosody(self):
        config = json.loads(
            (ROOT / "configs" / "talking_head_voice_profiles.json").read_text(encoding="utf-8")
        )
        controls = []
        for number in range(1, 21):
            scenario = json.loads((
                ROOT / f"configs/scenarios/scenario_{number:03d}/scenario_{number:03d}.json"
            ).read_text(encoding="utf-8"))
            profile = config["profiles"][scenario["scenario_id"]]
            for trigger in scenario["video_triggers"]:
                value = prosody_controls(trigger, profile)
                self.assertGreaterEqual(value["rate_pct"], -14)
                self.assertLessEqual(value["rate_pct"], 4)
                self.assertGreaterEqual(value["pitch_hz"], -8)
                self.assertLessEqual(value["pitch_hz"], 4)
                controls.append((value["profile"], value["rate_pct"], value["pitch_hz"]))
        self.assertEqual(len(controls), 60)
        self.assertGreaterEqual(len(set(controls)), 8)
        self.assertGreaterEqual(len({item[0] for item in controls}), 3)

    def test_audio_pipeline_does_not_use_old_fixed_fast_six_second_recipe(self):
        script = (ROOT / "scripts" / "prepare_talking_head_assets.py").read_text(encoding="utf-8")
        self.assertNotIn('"--rate=+8%"', script)
        self.assertNotIn('"-ar", "16000"', script)
        self.assertIn("speech_duration + lead_seconds + tail_seconds", script)
        self.assertIn("multimodel_v4_natural_speech_musetalk_v15", script)

    def test_generated_metadata_is_complete_when_present(self):
        for asset in self.manifest["assets"]:
            if asset["status"] != "generated":
                continue
            self.assertTrue(asset.get("has_video"))
            self.assertTrue(asset.get("has_audio"))
            self.assertGreaterEqual(asset.get("width"), 512)
            self.assertGreaterEqual(asset.get("height"), 512)
            self.assertEqual(asset.get("fps"), 25)
            self.assertEqual(asset.get("video_codec"), "h264")
            self.assertEqual(asset.get("pixel_format"), "yuv420p")
            self.assertTrue(asset.get("duration_matches_request"))
            self.assertEqual(len(asset.get("video_sha256", "")), 64)
            self.assertTrue(3 <= asset["duration_seconds_actual"] <= 8)
