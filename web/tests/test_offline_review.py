"""Public/reference isolation, frozen source identity and paired media integrity."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_offline_choice import item as choice_item
import web.offline_review as review
from web.server import api_payload


class OfflineReviewTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, value in [("ROOT", self.root), ("BANK", self.root / "bank"),
                            ("VIDEO_ROOT", self.root / "videos")]:
            mock = patch.object(review, name, value)
            mock.start()
            self.addCleanup(mock.stop)
        review.BANK.mkdir()
        self.item = choice_item()
        self.item["label_status"] = "pending_human_annotation"
        self.item["authoring"]["construction_source"] = {
            "scenario_path": "scenario.json", "scenario_sha256": self.write("scenario.json", {"title": "frozen scenario"}),
            "trajectory_path": "trajectory.json", "trajectory_sha256": self.write("trajectory.json", {"turns": [
                {"turn_id": "t1", "state_after": {"relationship": {"trust": 6}}, "state_appraisal_call": "PRIVATE_API_SENTINEL"},
                {"turn_id": "t2", "environment_response": "HIDDEN_FUTURE_SENTINEL"}]})}
        self.save_bank()

    def write(self, name, data):
        raw = json.dumps(data).encode()
        (self.root / name).write_bytes(raw)
        return review.digest(raw)

    def save_bank(self):
        (review.BANK / "items.jsonl").write_text(json.dumps(self.item) + "\n")

    def test_public_catalog_and_detail_do_not_contain_author_labels(self):
        catalog = api_payload("/api/offline-review")
        detail = api_payload("/api/offline-review/q1")
        self.assertEqual(catalog["summary"]["item_count"], 1)
        self.assertEqual(detail["public"]["input"], self.item["input"])
        rendered = json.dumps([catalog, detail])
        for key in ["ground_truth", "authoring", "option_variable_map", "state_after", "target_spec", "HIDDEN_FUTURE_SENTINEL"]:
            self.assertNotIn(key, rendered)
        self.assertIsNone(api_payload("/api/offline-review/missing"))

    def test_reference_retains_provenance_without_exposing_raw_calls_or_future_source(self):
        ref = api_payload("/api/offline-review/q1/reference")
        self.assertEqual(ref["scenario"]["title"], "frozen scenario")
        self.assertEqual(ref["authoring"]["answer"], "A")
        self.assertEqual(ref["source_turns"][0]["state_after"], {"relationship.trust": 6})
        self.assertEqual(len(ref["source_turns"]), 1)
        self.assertNotIn("PRIVATE_API_SENTINEL", json.dumps(ref))
        self.assertNotIn("HIDDEN_FUTURE_SENTINEL", json.dumps(ref))
        self.assertIsNone(self.item["ground_truth"])

    def test_source_hash_mismatch_and_outside_repository_fail_closed(self):
        (self.root / "scenario.json").write_text('{"title":"changed"}')
        ref = review.load_review("q1", reference=True)
        self.assertFalse(ref["source_checks"]["scenario"])
        self.assertIsNone(ref["scenario"])
        with tempfile.TemporaryDirectory() as outside:
            path = Path(outside) / "private.json"
            path.write_text('{"secret":"outside"}')
            self.assertIsNone(review.checked_source(str(path), review.digest(path.read_bytes())))

    def test_item_and_bank_hash_change_on_answer_or_question_edit(self):
        before = review.load_review("q1")
        self.item["question"] += "修订"
        self.save_bank()
        after = review.load_review("q1")
        self.assertNotEqual(before["bank_sha256"], after["bank_sha256"])
        self.assertNotEqual(before["metadata"]["item_sha256"], after["metadata"]["item_sha256"])

    def test_t3_branch_is_reference_only_and_requires_matching_action(self):
        self.item.update(task="T3", subtype="immediate_effect")
        self.item["input"]["candidate_actions"] = [{"action_id": "action_1", "text": "cooperate"}]
        branch = [{"candidate_action": {"text": "cooperate"}, "delayed_horizon": 5,
                   "window_complete": True, "future_turns": [{"turn_id": "t2", "environment_response": "BRANCH_ONLY"}]}]
        self.item["authoring"]["construction_source"].update(
            replay_path="branch.json", replay_sha256=self.write("branch.json", branch))
        self.item["authoring"]["replay_status"] = "validated"
        self.save_bank()
        self.assertNotIn("BRANCH_ONLY", json.dumps(review.load_review("q1")))
        self.assertIn("BRANCH_ONLY", json.dumps(review.load_review("q1", reference=True)))
        branch[0]["candidate_action"]["text"] = "different"
        self.item["authoring"]["construction_source"]["replay_sha256"] = self.write("branch.json", branch)
        self.save_bank()
        ref = review.load_review("q1", reference=True)
        self.assertFalse(ref["source_checks"]["branch_action_match"])
        self.assertEqual(ref["replays"], [])

    def test_paired_video_cannot_survive_answer_drift_or_asset_change(self):
        review.VIDEO_ROOT.mkdir()
        video = review.VIDEO_ROOT / "clip.mp4"
        video.write_bytes(b"video fixture")
        text_item, video_item = deepcopy(self.item), deepcopy(self.item)
        for item in (text_item, video_item):
            item["metadata"]["modality_pair_id"] = "q1"
        video_item.update(instance_id="q1-video", modality="text+video")
        path = review.BANK / "paired.items.jsonl"
        path.write_text("\n".join(json.dumps(i) for i in (text_item, video_item)))
        (review.BANK / "media.json").write_text(json.dumps({"q1-video": [{
            "path": str(video), "sha256": review.digest(video.read_bytes()),
            "source_asset_id": "fixture", "evidence_ids": ["t1"]}]}))
        self.assertTrue(review.load_review("q1")["media"][0]["available"])
        video.write_bytes(b"changed video")
        self.assertFalse(review.load_review("q1")["media"][0]["available"])
        video_item["authoring"]["answer"] = "B"
        path.write_text("\n".join(json.dumps(i) for i in (text_item, video_item)))
        self.assertEqual(review.load_review("q1")["media"], [])


if __name__ == "__main__":
    unittest.main()
