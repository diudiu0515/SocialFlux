import json
import unittest
from pathlib import Path

from scripts.prepare_talking_head_assets import prosody_controls
from web.server import load_media_assets


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "archives" / "legacy_qwen_scale300_20260919" / "raw"


class TalkingHeadFrameworkTest(unittest.TestCase):
    def test_legacy_assets_models_and_tools_are_permanently_removed(self):
        removed_paths = [
            ROOT / "media" / "talking_head",
            ROOT / "media" / "task_examples",
            ROOT / "build" / "talking_head",
            ROOT / "configs" / "talking_head_voice_profiles.json",
            ROOT / ".local_models" / "EchoMimicV2",
            ROOT / ".local_models" / "echomimic-env",
            ROOT / ".local_models" / "musetalk-env",
            ROOT / ".local_tools" / "echomimic_v2",
            ROOT / ".local_tools" / "musetalk",
            ARCHIVE / "build" / "talking_head",
            ARCHIVE / "media" / "talking_head",
            ARCHIVE / "configs" / "talking_head_voice_profiles.json",
        ]
        self.assertTrue(all(not path.exists() for path in removed_paths))
        self.assertEqual(load_media_assets(), [])

    def test_provider_neutral_framework_is_preserved(self):
        expected_scripts = {
            "prepare_talking_head_assets.py",
            "generate_talking_head_musetalk.py",
            "generate_talking_head_videos.py",
            "audit_talking_head_av_sync.py",
            "audit_talking_head_visual_stability.py",
            "audit_talking_head_release.py",
        }
        scripts = ROOT / "scripts"
        self.assertTrue(all((scripts / name).is_file() for name in expected_scripts))
        self.assertTrue((ROOT / "prompts" / "talking_head_generation_v1.md").is_file())
        self.assertTrue((ROOT / "schemas" / "talking_head_request.schema.json").is_file())
        self.assertTrue((ROOT / "web" / "static" / "task_examples.html").is_file())
        self.assertTrue((ROOT / "requirements-video.txt").is_file())

    def test_active_scenarios_do_not_claim_deleted_assets(self):
        paths = sorted((ROOT / "configs" / "scenarios").glob("scenario_*/scenario_*.json"))
        self.assertEqual(len(paths), 20)
        for path in paths:
            scenario = json.loads(path.read_text(encoding="utf-8"))
            media = scenario["media_generation"]
            self.assertEqual(media["asset_status"], "not_generated")
            self.assertEqual(media["provider"], "external_api_pending")
            self.assertEqual(media["profile"], "provider_neutral_v1")
            self.assertTrue(
                all(trigger.get("media_asset_id") is None for trigger in scenario["video_triggers"])
            )

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
