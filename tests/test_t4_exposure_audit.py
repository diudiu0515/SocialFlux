import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.audit_t4_multimodal_exposure import Evidence, read_episode


class ExposureAuditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = self.root / "build/test/run/episodes/GPT50_001/gpt/text_video"

    def save(self, name, value):
        path = self.base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def read(self):
        return read_episode(
            Evidence(self.root), "test", "GPT50_001", "gpt", "text_video",
            {"providers": {"gpt": {"model": "test-model"}}},
            {"selected_transport": "video_frames"}, False,
        )[0]

    def test_prepared_delivery_does_not_prove_successful_media_request(self):
        self.save("result.json", {"status": "failed", "error": "timeout"})
        self.save("video_deliveries.json", [{"asset_id": "asset"}])
        self.save("calls/policy/0001.json", {
            "status": "failed", "error": "timeout",
            "messages": [{"content": [{"type": "image_url", "image_url": {"url": "fixture"}}]}],
        })
        row = self.read()
        self.assertEqual(row["prepared_media_count"], 1)
        self.assertEqual(row["media_call_count"], 1)
        self.assertEqual(row["successful_media_call_count"], 0)
        self.assertFalse(row["scored_with_verified_media"])

    def test_environment_failure_retains_prior_successful_media_exposure(self):
        self.save("result.json", {"status": "failed", "error": "The read operation timed out"})
        self.save("calls/policy/0002.json", {
            "status": "completed", "raw_output": "next action",
            "messages": [{"content": [{"type": "image", "source": {"type": "base64"}}]}],
        })
        self.save("calls/state/0002.json", {
            "status": "failed", "error": "The read operation timed out", "messages": [],
        })
        row = self.read()
        self.assertEqual(row["successful_media_call_count"], 1)
        self.assertEqual(row["first_successful_media_call_index"], 2)
        self.assertEqual(row["terminal_failure_roles"], ["state"])
        self.assertFalse(row["scored_with_verified_media"])

    def test_final_turn_trigger_is_not_policy_exposure(self):
        self.save("result.json", {"status": "completed_without_video_exposure", "video_delivery_count": 0})
        self.save("calls/policy/0001.json", {
            "status": "completed", "raw_output": "next action",
            "messages": [{"content": "text only"}],
        })
        self.save("trajectory.json", {
            "turns": [{"turn_id": "t1", "trigger_events": [{
                "media_type": "video", "media_asset_id": "asset", "event_family": "tension",
            }]}],
            "ending": {"reason": "natural_completion"},
        })
        row = self.read()
        self.assertEqual(row["recorded_trigger_count"], 1)
        self.assertEqual(row["successful_media_call_count"], 0)
        self.assertEqual(row["exposure_status"], "triggered_without_media_call")

    def test_nonempty_response_required_and_corrupt_evidence_is_not_zero(self):
        self.save("calls/policy/0001.json", {
            "status": "completed", "raw_output": "",
            "messages": [{"content": [{"type": "video_url"}]}],
        })
        self.assertEqual(self.read()["successful_media_call_count"], 0)
        (self.base / "result.json").write_text("{")
        with self.assertRaisesRegex(ValueError, "Cannot read live JSON"):
            self.read()


if __name__ == "__main__":
    unittest.main()
