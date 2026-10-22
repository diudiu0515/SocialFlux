import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.finalize_multimodal_video_queue import main as finalize
from scripts.prepare_multimodal_video_queue import (
    select_important_turns,
    stable_review_sample,
    validate_public_rendering,
)
from environment.video_requests import (
    DEFAULT_EXPRESSION_POLICY,
    build_video_request,
    estimate_spoken_duration,
)
from scripts.run_autodl_seedance_video import validate_payload, video_url
from scripts.run_multimodal_video_queue import seedance_payload, select_records, ensure_state


class MultimodalVideoQueueTest(unittest.TestCase):
    def test_image_identity_reference_is_audio_free_and_hash_bound(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'identity.png').write_bytes(b'first-image')
            request = {'prompt': 'Say exactly the new English line.', 'duration_seconds': 5,
                       'generate_audio': True, 'reference_image_file': 'identity.png'}
            payload = seedance_payload(request, reference_root=root)
            self.assertEqual(payload['content'][1]['role'], 'reference_image')
            self.assertTrue(payload['content'][1]['image_url']['url'].startswith('data:image/png;base64,'))
            self.assertNotIn('local_reference_video', payload)
            with self.assertRaises(ValueError):
                seedance_payload({**request, 'reference_video_file': 'old.mp4'}, reference_root=root)
            with self.assertRaises(ValueError):
                seedance_payload({**request, 'reference_image_file': '../outside.png'}, reference_root=root)
            (root / 'requests').mkdir()
            (root / 'requests/x.json').write_text(json.dumps(request))
            record = {'request_id': 'x', 'request_file': 'requests/x.json'}
            ensure_state(root, record, model='doubao-seedance-2-0-260128', resolution='720p')
            (root / 'identity.png').write_bytes(b'changed-image')
            with self.assertRaisesRegex(ValueError, 'changed after state creation'):
                ensure_state(root, record, model='doubao-seedance-2-0-260128', resolution='720p')

    def test_review_sample_covers_scenarios_then_fills_target(self):
        records = [
            {
                "request_id": f"{scenario}-{index}",
                "scenario_id": scenario,
                "importance_score": index,
            }
            for scenario in ("s1", "s2")
            for index in range(3)
        ]
        selected = stable_review_sample(records, 4)
        self.assertEqual(len(selected), 4)
        self.assertEqual({item["scenario_id"] for item in selected}, {"s1", "s2"})
        self.assertEqual(len({item["request_id"] for item in selected}), 4)

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

    def test_provider_neutral_request_converts_to_seedance_payload(self):
        payload = seedance_payload({
            "prompt": "A fictional adult speaks naturally in an unbranded office.",
            "duration_seconds": 3.1,
        })
        self.assertEqual(payload["duration"], 4)
        self.assertEqual(payload["resolution"], "480p")
        self.assertTrue(payload["generate_audio"])
        self.assertFalse(payload["watermark"])

    def test_gate2_selection_preserves_review_sample_order(self):
        with TemporaryDirectory() as directory:
            batch = Path(directory)
            gate2 = batch / "gate2"
            gate2.mkdir()
            manifest = {
                "requests": [
                    {"request_id": "r1"},
                    {"request_id": "r2"},
                    {"request_id": "r3"},
                ]
            }
            (gate2 / "video_state_consistency.json").write_text(
                json.dumps({
                    "review_items": [
                        {"request_id": "r3"},
                        {"request_id": "r1"},
                    ]
                }),
                encoding="utf-8",
            )
            selected = select_records(batch, manifest, "gate2")
            self.assertEqual([item["request_id"] for item in selected], ["r3", "r1"])

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
        self.assertIn(
            "completely original, fictional, non-famous adult", request["prompt"]
        )
        self.assertIn("generic unbranded setting", request["prompt"])
        self.assertTrue(request["generate_audio"])
        self.assertEqual(request["audio"]["exact_line"], (
            "I understand. Let us review the evidence first."
        ))

    def test_talking_head_uses_provider_reference_field_and_identity(self):
        request = build_video_request(
            {
                "scenario_id": "TEST_001",
                "environment_agent": {"persona": {
                    "name": "Alex", "role": "project partner",
                }},
            },
            "I will verify that before deciding.",
            {
                "facial_expression": "restrained concern",
                "gaze": "steady eye contact",
                "speech_style": "measured",
                "prosody": "even",
                "behavioral_cues": ["one small nod"],
            },
            continuity_reference="multimodal_delivery_v1/online_multimodal/assets/anchor.mp4",
        )
        self.assertEqual(
            request["reference_video_file"], request["continuity_reference"]
        )
        self.assertIn(request["identity"]["appearance"], request["prompt"])
        self.assertIn("Every spoken phoneme must align", request["prompt"])

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
        value["observable_expression"]["gaze"] = "steady eye contact"
        value["observable_expression"]["behavioral_cues"] = [
            "Presents both constraints in parallel"
        ]
        with self.assertRaisesRegex(ValueError, "visible micro-action"):
            validate_public_rendering(value)

    def test_public_rendering_accepts_common_visible_micro_actions(self):
        value = {
            "english_spoken_line": "I need a moment to verify that.",
            "observable_expression": {
                "facial_expression": "restrained concern",
                "gaze": "briefly looks away, then returns",
                "speech_style": "measured",
                "prosody": "quiet and even",
                "behavioral_cues": [
                    "Briefly looks down",
                    "Raises the eyebrows slightly",
                ],
            },
        }
        self.assertEqual(validate_public_rendering(value), value)

    def test_public_rendering_counts_curly_apostrophe_as_one_word(self):
        value = {
            "english_spoken_line": (
                "I’ll draft the memo now and send it after you confirm receipt."
            ),
            "observable_expression": {
                "facial_expression": "attentive",
                "gaze": "steady eye contact",
                "speech_style": "measured",
                "prosody": "even",
                "behavioral_cues": ["One small nod"],
            },
        }
        self.assertEqual(validate_public_rendering(value), value)

    def test_public_rendering_counts_clock_time_as_one_word(self):
        value = {
            "english_spoken_line": " ".join(["word"] * 31 + ["06:30"]),
            "observable_expression": {
                "facial_expression": "attentive",
                "gaze": "steady eye contact",
                "speech_style": "measured",
                "prosody": "even",
                "behavioral_cues": [
                    "Touches the tabletop once",
                    "Lightly taps one finger",
                ],
            },
        }
        self.assertEqual(validate_public_rendering(value), value)

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

    def test_finalizer_preserves_terminal_provider_failure(self):
        with TemporaryDirectory() as directory:
            batch = Path(directory)
            multimodal = batch / "multimodal"
            provider_states = multimodal / "provider_states"
            gate2_root = batch / "gate2"
            provider_states.mkdir(parents=True)
            gate2_root.mkdir()
            request_id = "request-failed"
            request_file = "multimodal/requests/failed-request.json"
            manifest = {
                "requests": [{
                    "request_id": request_id,
                    "request_file": request_file,
                    "video_file": "multimodal/assets/failed-request.mp4",
                    "status": "request_ready",
                }],
                "provider_status": "awaiting_video_api_configuration",
            }
            (multimodal / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            (provider_states / "failed-request.json").write_text(
                json.dumps({
                    "status": "failed",
                    "task_id": "task-failed",
                    "latest_query_response": {
                        "error": {"code": "PolicyViolation", "message": "blocked"}
                    },
                }),
                encoding="utf-8",
            )
            (gate2_root / "video_state_consistency.json").write_text(
                json.dumps({
                    "record": {"request_safety_passed": True},
                    "review_items": [{"request_id": request_id}],
                }),
                encoding="utf-8",
            )

            finalize(["--batch-root", str(batch), "--skip-probe"])

            updated_manifest = json.loads(
                (multimodal / "manifest.json").read_text()
            )
            result = json.loads(
                (gate2_root / "video_state_consistency.json").read_text()
            )
            self.assertEqual(updated_manifest["provider_status"], "provider_failed")
            self.assertEqual(updated_manifest["provider_failure_count"], 1)
            self.assertEqual(
                updated_manifest["requests"][0]["status"], "provider_failed"
            )
            self.assertEqual(result["record"]["provider_failure_count"], 1)
            self.assertEqual(
                result["review_items"][0]["video_status"], "provider_failed"
            )
            self.assertFalse(result["record"]["machine_screen_passed"])

    def test_finalizer_uses_versioned_evidence_and_counts_expired_job(self):
        with TemporaryDirectory() as directory:
            batch = Path(directory)
            queue = batch / "delivery" / "talking_head"
            provider_states = queue / "provider_states"
            evidence_path = queue / "video_state_consistency.json"
            provider_states.mkdir(parents=True)
            request_id = "request-expired"
            request_file = "delivery/talking_head/requests/expired.json"
            manifest_path = queue / "manifest.json"
            manifest_path.write_text(json.dumps({
                "gate2_evidence_file": str(evidence_path),
                "requests": [{
                    "request_id": request_id,
                    "request_file": request_file,
                    "video_file": "delivery/talking_head/assets/expired.mp4",
                    "status": "request_ready",
                }],
            }), encoding="utf-8")
            (provider_states / "expired.json").write_text(json.dumps({
                "status": "expired",
                "task_id": "task-expired",
                "latest_query_response": {
                    "error": {"code": "Expired", "message": "deadline"}
                },
            }), encoding="utf-8")
            evidence_path.write_text(json.dumps({
                "record": {"request_safety_passed": True},
                "review_items": [{"request_id": request_id}],
            }), encoding="utf-8")

            finalize([
                "--batch-root", str(batch),
                "--manifest", str(manifest_path),
                "--skip-probe",
            ])

            updated_manifest = json.loads(manifest_path.read_text())
            evidence = json.loads(evidence_path.read_text())
            self.assertEqual(updated_manifest["provider_failure_count"], 1)
            self.assertEqual(
                updated_manifest["requests"][0]["provider_terminal_status"],
                "expired",
            )
            self.assertEqual(evidence["record"]["provider_failure_count"], 1)
            self.assertFalse(
                (batch / "gate2" / "video_state_consistency.json").exists()
            )


if __name__ == "__main__":
    unittest.main()
