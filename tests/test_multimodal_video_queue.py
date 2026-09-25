import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.finalize_multimodal_video_queue import main as finalize
from scripts.prepare_multimodal_video_queue import (
    select_important_turns,
    validate_public_rendering,
)
from environment.video_requests import (
    DEFAULT_EXPRESSION_POLICY,
    build_video_request,
    estimate_spoken_duration,
)
from scripts.run_autodl_seedance_video import validate_payload, video_url


class MultimodalVideoQueueTest(unittest.TestCase):
    def test_seedance_payload_requires_english_synchronized_audio(self):
        payload = {
            "model": "doubao-seedance-2-0-260128",
            "content": [{"type": "text", "text": "A natural English line."}],
            "duration": 4,
            "resolution": "480p",
            "generate_audio": True,
            "watermark": False,
        }
        self.assertIs(validate_payload(payload), payload)
        payload["content"][0]["text"] = "不能包含中文"
        with self.assertRaisesRegex(ValueError, "entirely English"):
            validate_payload(payload)

    def test_seedance_result_requires_https_video(self):
        self.assertEqual(
            video_url({"content": {"video_url": "https://example.test/a.mp4"}}),
            "https://example.test/a.mp4",
        )
        with self.assertRaisesRegex(ValueError, "safe HTTPS"):
            video_url({"content": {"video_url": "http://example.test/a.mp4"}})

    def test_expression_policy_is_subtle_and_limits_simultaneous_cues(self):
        config = json.loads(
            Path("configs/multimodal_generation.json").read_text(encoding="utf-8")
        )
        self.assertEqual(config["expression_rendering"], DEFAULT_EXPRESSION_POLICY)
        request = build_video_request(
            {"environment_agent": {"persona": {
                "name": "Alex", "role": "project partner",
            }}},
            "I understand. Let us review the evidence first.",
            {
                "facial_expression": "calm but concerned",
                "gaze": "steady eye contact",
                "speech_style": "measured",
                "prosody": "even",
                "behavioral_cues": [
                    "subtle brow tension",
                    "one small nod",
                    "dramatic arm movement",
                ],
            },
        )
        self.assertIn("subtle, context-appropriate guidance", request["prompt"])
        self.assertIn("subtle brow tension", request["prompt"])
        self.assertIn("one small nod", request["prompt"])
        self.assertNotIn("dramatic arm movement", request["prompt"])
        self.assertIn("low-to-moderate", request["prompt"])

    def test_english_speech_duration_is_adaptive_and_bounded(self):
        self.assertEqual(estimate_spoken_duration("See you tomorrow."), 3.0)
        self.assertEqual(estimate_spoken_duration("Okay."), 3.0)
        self.assertEqual(estimate_spoken_duration("word " * 100), 15.0)

    def test_public_rendering_adaptation_requires_all_english_fields(self):
        value = {
            "english_spoken_line": "I will verify the record before deciding.",
            "observable_expression": {
                "facial_expression": "calm and attentive",
                "gaze": "steady eye contact",
                "speech_style": "measured and direct",
                "prosody": "even with a slight final rise",
                "behavioral_cues": ["one small nod", "brief pause"],
            },
        }
        self.assertEqual(validate_public_rendering(value), value)
        value["observable_expression"]["gaze"] = "直视对方"
        with self.assertRaisesRegex(ValueError, "not English"):
            validate_public_rendering(value)

    def test_important_nodes_prefer_stateful_and_consequential_turns(self):
        turns = [
            {"turn_id": f"t{index}", "numeric_state_delta": {"trust": 0}}
            for index in range(1, 7)
        ]
        turns[1]["numeric_state_delta"] = {"trust": 3}
        turns[4]["response_consequential_claims"] = [{"claim": "承诺"}]
        selected = select_important_turns({"turns": turns}, 2, 2)
        self.assertEqual(
            {item[2]["turn_id"] for item in selected},
            {"t2", "t5"},
        )

    def test_finalizer_registers_api_outputs_and_unblocks_machine_screen(self):
        with TemporaryDirectory() as directory:
            batch = Path(directory)
            assets = batch / "multimodal" / "assets"
            gate2_root = batch / "gate2"
            assets.mkdir(parents=True)
            gate2_root.mkdir()
            requests = []
            review_items = []
            for index in range(2):
                video = assets / f"video_{index}.mp4"
                video.write_bytes(b"generated-video")
                request_id = f"request-{index}"
                requests.append({
                    "request_id": request_id,
                    "video_file": str(video.relative_to(batch)),
                    "status": "request_ready",
                })
                review_items.append({"request_id": request_id})
            manifest = {
                "requests": requests,
                "provider_status": "awaiting_video_api_configuration",
            }
            (batch / "multimodal" / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            evidence = {
                "record": {"request_safety_passed": True},
                "review_items": review_items,
            }
            (gate2_root / "video_state_consistency.json").write_text(
                json.dumps(evidence), encoding="utf-8"
            )
            finalize([
                "--batch-root", str(batch),
                "--minimum-review-videos", "2",
                "--skip-probe",
            ])
            result = json.loads(
                (gate2_root / "video_state_consistency.json").read_text()
            )
            self.assertEqual(result["record"]["generated_video_count"], 2)
            self.assertTrue(result["record"]["machine_screen_passed"])
            self.assertEqual(result["record"]["review_status"], "pending_human")


if __name__ == "__main__":
    unittest.main()
