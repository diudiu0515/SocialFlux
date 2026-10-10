import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from evaluation.t4_asset_coverage import audit_asset_coverage, require_complete_assets
from evaluation.t4_media import compact_media, provider_messages
from providers.anthropic import AnthropicProvider


class T4AssetCoverageTest(unittest.TestCase):
    def test_one_playable_clip_is_not_complete_event_coverage(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "anchor.mp4"
            path.write_bytes(b"test fixture")
            records = [{"request_id": "anchor", "scenario_id": "a", "event_family": "tension",
                        "video_file": path.name, "status": "generated_structural_pass",
                        "video_sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
                       {"request_id": "relief", "scenario_id": "a", "event_family": "relief",
                        "video_file": "absent.mp4", "status": "request_ready"}]
            report = audit_asset_coverage({"requests": records}, directory, expected_scenarios=1)
            self.assertEqual(report["scenarios_with_any_video"], 1)
            self.assertEqual(report["scenarios_with_all_required_videos"], 0)
            with self.assertRaises(ValueError):
                require_complete_assets(report)
            report = audit_asset_coverage({"requests": records[:1]}, directory, expected_scenarios=1)
            require_complete_assets(report)
            path.write_bytes(b"changed")
            self.assertFalse(audit_asset_coverage({"requests": records[:1]}, directory,
                                                expected_scenarios=1)["generation_complete"])

    def test_actual_image_payload_is_preserved_and_video_never_becomes_text(self):
        original = [{"role": "user", "content": [{"type": "text", "text": "Observe"},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,YWJj"}}]}]
        messages = provider_messages(original, "anthropic")
        source = messages[0]["content"][1]["source"]
        self.assertEqual(source, {"type": "base64", "media_type": "image/jpeg", "data": "YWJj"})
        _, accepted = AnthropicProvider._messages(messages)
        self.assertEqual(accepted[0]["content"][1]["source"]["data"], "YWJj")
        self.assertNotIn("YWJj", str(compact_media(messages)))
        with self.assertRaises(ValueError):
            provider_messages([{"role": "user", "content": [{"type": "video_url", "video_url": {"url": "x"}}]}], "anthropic")
        self.assertEqual(original[0]["content"][1]["type"], "image_url")


if __name__ == "__main__":
    unittest.main()
