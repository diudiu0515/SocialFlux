import unittest
from pathlib import Path

from scripts.prepare_talking_head_assets import prosody_controls
from web.server import load_media_assets


ROOT = Path(__file__).resolve().parents[1]


class TalkingHeadFrameworkTest(unittest.TestCase):
    def test_legacy_assets_and_voice_profiles_are_not_active(self):
        self.assertFalse((ROOT / "media" / "talking_head").exists())
        self.assertFalse((ROOT / "build" / "talking_head").exists())
        self.assertFalse(
            (ROOT / "configs" / "talking_head_voice_profiles.json").exists()
        )
        self.assertEqual(load_media_assets(), [])

    def test_generation_and_audit_framework_is_preserved(self):
        expected = {
            "prepare_talking_head_assets.py",
            "generate_talking_head_musetalk.py",
            "generate_talking_head_videos.py",
            "audit_talking_head_av_sync.py",
            "audit_talking_head_visual_stability.py",
            "audit_talking_head_release.py",
        }
        scripts = ROOT / "scripts"
        self.assertTrue(all((scripts / name).is_file() for name in expected))
        self.assertTrue((ROOT / "requirements-video.txt").is_file())

    def test_prosody_controls_remain_batch_independent(self):
        profile = {
            "base_rate_pct": -2,
            "base_pitch_hz": 0,
            "volume_pct": 0,
        }
        urgent = prosody_controls(
            {"trigger_id": "public_alarm", "observable_expression": {}},
            profile,
        )
        quiet = prosody_controls(
            {
                "trigger_id": "hesitant_disclosure",
                "observable_expression": {"speech_style": "低声，停顿"},
            },
            profile,
        )
        self.assertEqual(urgent["profile"], "controlled_urgent")
        self.assertEqual(quiet["profile"], "quiet_reflective")
        self.assertNotEqual(urgent["rate_pct"], quiet["rate_pct"])


if __name__ == "__main__":
    unittest.main()
