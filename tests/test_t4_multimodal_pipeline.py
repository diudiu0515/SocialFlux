import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from evaluation.t4_multimodal import AssetPolicy, RequestBudget
from evaluation.t4_media import sha_file
from policies.model_policy import ModelPolicy
from scripts.run_autodl_seedance_video import materialize_local_references


class T4MultimodalPipelineTest(unittest.TestCase):
    def test_reference_transport_is_explicit_and_internal_fields_are_removed(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "anchor.mp4"
            path.write_bytes(b"synthetic video fixture")
            payload = {"content": [], "local_reference_video": str(path),
                       "local_reference_transport": "provided_url", "local_reference_url": "https://provider.example/anchor.mp4"}
            result = materialize_local_references(payload)
            self.assertEqual(set(result), {"content"})
            self.assertEqual(result["content"][0]["video_url"]["url"], "https://provider.example/anchor.mp4")
            payload["local_reference_url"] = "http://provider.example/anchor.mp4"
            with self.assertRaises(ValueError):
                materialize_local_references(payload)

    def test_budget_persists_and_stops_before_extra_request(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "budget.json"
            budget = RequestBudget(path, 1)
            budget.take()
            with self.assertRaises(RuntimeError):
                budget.take()
            with self.assertRaises(RuntimeError):
                RequestBudget(path, 1).take()
            self.assertEqual(json.loads(path.read_text())["request_count"], 1)

    def test_text_identical_and_real_video_added_without_trigger_descriptions(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mp4"
            path.write_bytes(b"video fixture")
            asset = {"path": str(path), "sha256": sha_file(path)}
            observation = {"turn_id": 1, "role": {"name": "A", "role": "reporter", "explicit_goal": "Agree"},
                "target_character": {"name": "B", "role": "editor"}, "media": [{"media_type": "video", "media_asset_id": "secret-family"}],
                "observable_cues": ["PRIVATE_CUE_MARKER"]}
            text = ModelPolicy("a", None, validation_profile="hard_only")
            video = AssetPolicy("a", None, validation_profile="hard_only", observation_condition="text_video",
                                media_input_format="openai_video_url", assets={"secret-family": asset},
                                transport="native_video", audit_path=Path(directory) / "audit.json")
            a, _ = text._build_request(observation)
            b, _ = video._build_request(observation)
            self.assertEqual(a[1]["content"], b[1]["content"][0]["text"])
            self.assertEqual(b[1]["content"][1]["type"], "video_url")
            self.assertNotIn("secret-family", json.dumps(b))
            self.assertNotIn("PRIVATE_CUE_MARKER", json.dumps(b))
            path.write_bytes(b"changed video")
            with self.assertRaises(ValueError):
                video._build_request(observation)


if __name__ == "__main__":
    unittest.main()
