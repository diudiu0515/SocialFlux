import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.finalize_multimodal_video_queue import main as finalize
from scripts.prepare_multimodal_video_queue import select_important_turns


class MultimodalVideoQueueTest(unittest.TestCase):
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
