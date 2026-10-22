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

    def test_talking_preview_is_bound_to_bank_and_selected_public_nodes(self):
        bank_sha = review.digest((review.BANK / 'items.jsonl').read_bytes())
        prefix = 'data/offline_talking_head_en_v1/' + bank_sha[:16] + '/'
        (self.root / prefix).mkdir(parents=True)
        self.write(prefix + 'preview_selection.json', {'items_sha256': bank_sha,
                   'scene_ids': ['scene'], 'node_ids': ['selected']})
        public_node = {'node_id': 'selected', 'scenario_id': 'scene', 'location': 'ending',
                       'speaker': 'Fictional speaker', 'source_public_response': '中文源记录',
                       'spoken_text': 'Exact public line', 'speech_language': 'en',
                       'source_observable_expression': {}, 'segment_request_ids': ['segment'],
                       'scenario_source': {'private': 'PRIVATE_SOURCE_SENTINEL'}}
        self.write(prefix + 'manifest.json', {'items_sha256': bank_sha,
                   'nodes': [public_node, {**public_node, 'node_id': 'excluded'}]})
        with patch.dict(review.BANK_PATHS, {'scenarios-v2': 'bank'}):
            result = api_payload('/api/offline-talking-preview')
            self.assertEqual(result['node_count'], 1)
            self.assertEqual(result['ready_nodes'], 0)
            self.assertEqual(result['scenes'][0]['nodes'][0]['spoken_text'], 'Exact public line')
            self.assertEqual(result['scenes'][0]['nodes'][0]['source_text'], '中文源记录')
            self.assertNotIn('PRIVATE_SOURCE_SENTINEL', json.dumps(result))
            self.item['question'] += 'changed'
            self.save_bank()
            self.assertEqual(api_payload('/api/offline-talking-preview')['node_count'], 0)

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

    def test_bank_selection_is_allowlisted_and_isolated_across_threads(self):
        from concurrent.futures import ThreadPoolExecutor
        other = deepcopy(self.item)
        other['instance_id'] = 'other-bank'
        directory = self.root / review.BANK_PATHS['gpt50-t1-t3']
        directory.mkdir(parents=True)
        (directory / 'items.jsonl').write_text(json.dumps(other) + '\n')
        (directory / 'manifest.json').write_text(json.dumps({'expected_items':400,'complete':False,'paused_tasks':['T2']}))
        def read(bank):
            return api_payload('/api/offline-review', offline_bank=bank)
        with ThreadPoolExecutor(max_workers=4) as pool:
            rows = list(pool.map(read, [None, 'gpt50-t1-t3'] * 8))
        self.assertEqual([r['items'][0]['instance_id'] for r in rows], ['q1','other-bank'] * 8)
        self.assertEqual(rows[1]['summary']['expected_items'],400)
        self.assertFalse(rows[1]['summary']['generation_complete'])
        self.assertIsNone(read('../../private'))
        self.assertIsNone(api_payload('/api/offline-review/q1', offline_bank='gpt50-t1-t3'))
        self.assertEqual(review.bank_path(), review.BANK)

    def test_t3_branch_is_reference_only_and_requires_matching_action(self):
        self.item.update(task="T3", subtype="immediate_effect")
        self.item["input"]["candidate_actions"] = [{"action_id": "action_1", "text": "cooperate"}]
        branch = [{"candidate_action": {"text": "cooperate"}, "delayed_horizon": 5,
                   "experiment": "observed_prefix_plus_new_continuation", "prefix_reuse": {"environment_responses": 1},
                   "window_complete": True, "future_turns": [{"turn_id": "t2", "environment_response": "BRANCH_ONLY"}]}]
        self.item["authoring"]["construction_source"].update(
            replay_path="branch.json", replay_sha256=self.write("branch.json", branch))
        self.item["authoring"]["replay_status"] = "validated"
        self.save_bank()
        self.assertNotIn("BRANCH_ONLY", json.dumps(review.load_review("q1")))
        self.assertIn("BRANCH_ONLY", json.dumps(review.load_review("q1", reference=True)))
        self.assertEqual(review.load_review("q1", reference=True)["replays"][0]["reused_prefix_responses"], 1)
        self.assertNotIn("reused_prefix_responses", json.dumps(review.load_review("q1")))
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

    def test_media_cannot_be_reassigned_to_another_evidence_position(self):
        review.VIDEO_ROOT.mkdir()
        video = review.VIDEO_ROOT / "clip.mp4"
        video.write_bytes(b"video fixture")
        binding = {"sha256": review.digest(video.read_bytes()), "evidence_ids": ["t1"]}
        text_item, video_item = deepcopy(self.item), deepcopy(self.item)
        for variant in (text_item, video_item):
            variant["metadata"]["modality_pair_id"] = "q1"
        video_item.update(instance_id="q1-video", modality="text+video")
        video_item["authoring"]["matched_assets"] = [binding]
        (review.BANK / "paired.items.jsonl").write_text("\n".join(json.dumps(i) for i in (text_item, video_item)))
        media = {"q1-video": [{**binding, "path": str(video), "source_asset_id": "fixture"}]}
        self.write("bank/media.json", media)
        self.assertEqual(review.load_review("q1")["media_coverage"]["status"], "complete")
        media["q1-video"][0]["evidence_ids"] = ["context"]
        self.write("bank/media.json", media)
        detail = review.load_review("q1")
        self.assertEqual(detail["media"], [])
        self.assertEqual(detail["media_coverage"]["status"], "missing")

    def test_pairing_summary_is_bound_to_current_bank_and_media(self):
        media_sha = self.write("bank/media.json", {})
        self.write("bank/pairing_report.json", {
            "items_sha256": review.load_review()["bank_sha256"], "media_sha256": media_sha,
            "logical_pairs": 0, "coverage_counts": {"missing": 1}})
        self.assertEqual(review.load_review()["summary"]["media_missing"], 1)
        self.item["question"] += "新版"
        self.save_bank()
        self.assertIsNone(review.load_review()["summary"]["media_missing"])

    def test_talking_head_serving_requires_registered_hash_and_exact_public_line(self):
        directory = self.root / "data/offline_talking_head_en_v1" / ("a" * 16)
        assets = directory / "assets"
        assets.mkdir(parents=True)
        video = assets / "node.mp4"
        video.write_bytes(b"talking video fixture")
        asset = {"path": str(video), "sha256": review.digest(video.read_bytes()),
                 "source_asset_id": "node", "media_kind": "talking_head",
                 "spoken_text": self.item["input"]["history"][0]["environment_character"],
                 "evidence_ids": ["t1"]}
        (directory / "completed_nodes.json").write_text(json.dumps([{"node_id": "node", "asset": asset}]))
        self.assertEqual(review.talking_video_target("a" * 16, "node.mp4"), video)
        self.assertIsNone(review.talking_video_target("../outside", "node.mp4"))
        self.assertIsNone(review.talking_video_target("a" * 16, "../node.mp4"))
        pairs = [deepcopy(self.item), deepcopy(self.item)]
        for pair in pairs:
            pair["metadata"]["modality_pair_id"] = "q1"
        pairs[1].update(instance_id="q1-video", modality="text+video")
        pairs[1]["authoring"]["matched_assets"] = [{k: asset[k] for k in ("sha256", "evidence_ids")}]
        (review.BANK / "paired.items.jsonl").write_text("\n".join(json.dumps(pair) for pair in pairs))
        self.write("bank/media.json", {"q1-video": [asset]})
        media = review.load_review("q1")["media"][0]
        self.assertTrue(media["available"])
        self.assertTrue(media["url"].startswith("/offline-talking-video/"))
        self.assertFalse(media["speech_verified"])
        asset["spoken_text"] = "unrelated words"
        self.write("bank/media.json", {"q1-video": [asset]})
        self.assertEqual(review.load_review("q1")["media"], [])
        video.write_bytes(b"changed video")
        self.assertIsNone(review.talking_video_target("a" * 16, "node.mp4"))


if __name__ == "__main__":
    unittest.main()
