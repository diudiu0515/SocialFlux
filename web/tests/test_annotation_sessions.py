"""Server-side gates, immutable submissions, exposure and independent scoring."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from web import annotation_sessions as sessions


class AnnotationSessionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        items, bank_hash = sessions.current_items("scenarios-v2")
        self.items = [deepcopy(x) for x in items if x["story_id"] == "GPT50_001"][:2]
        self.store_patch = patch.object(sessions, "STORE", Path(self.directory.name))
        self.bank_patch = patch.object(sessions, "current_items", return_value=(self.items, bank_hash))
        self.evidence_patch = patch.object(sessions, "private_evidence", return_value={"private_state": "SECRET_EVIDENCE"})
        for p in (self.store_patch, self.bank_patch, self.evidence_patch):
            p.start()
        self.addCleanup(self.directory.cleanup)
        for p in (self.store_patch, self.bank_patch, self.evidence_patch):
            self.addCleanup(p.stop)

    def start(self, reviewer="person-one", prior=False):
        return sessions.dispatch("start", {"reviewer": reviewer, "scenes": ["GPT50_001"],
                                         "prior_exposure": prior, "modality": "text"})["token"]

    def test_new_default_is_frozen_video_input_with_exported_bindings(self):
        value = sessions.dispatch('start', {'reviewer':'video-person','scenes':['GPT50_001'],'prior_exposure':False})
        self.assertEqual(value['modality'], 'text+video')
        token=value['token'];identity=self.items[0]['instance_id']
        data=self.call('item',token)
        self.assertEqual(data['public']['modality'],'text+video')
        self.assertEqual(data['public']['instance_id'],identity+'-video')
        self.assertEqual(data['public']['input'],self.items[0]['input'])
        self.assertTrue(data['media'])
        self.assertNotIn('authoring',json.dumps(data))
        self.assertNotIn('human_review',json.dumps(data))
        self.items[0]['question']='A later source edit must not change this session'
        self.assertEqual(self.call('item',token)['public'],data['public'])
        self.call('blind',token,answer='A')
        exported=self.call('export',token)
        self.assertEqual(exported['modality'],'text+video')
        self.assertEqual(exported['blind_responses'][identity]['media_hashes'],exported['media_hashes'][identity])
        self.assertEqual(sessions.human_results()['human_baselines'][0]['modality'],'text+video')

    def test_video_assignment_rejects_stale_binding_and_missing_frozen_file(self):
        payload={'reviewer':'video-person','scenes':['GPT50_001'],'prior_exposure':False}
        token=sessions.dispatch('start',payload)['token']
        with patch.object(sessions,'frozen_media_available',return_value=False):
            for action in ('item','blind'):
                with self.assertRaisesRegex(ValueError,'视频缺失或内容发生变化'):
                    self.call(action,token,answer='A')
        self.items[0]['question']='changed source question'
        with self.assertRaisesRegex(ValueError,'缺少与当前题目版本匹配的视频'):
            sessions.dispatch('start',payload)
        catalog=sessions.catalog()
        self.assertFalse(catalog['scenes'][0]['video_available'])
        self.assertEqual(catalog['scenes'][0]['video_questions'],1)

    def test_legacy_text_session_keeps_its_input_without_video(self):
        token=self.start()
        data=self.call('item',token)
        self.assertEqual(data['public']['modality'],'text')
        self.assertEqual(data['media'],[])
        self.assertEqual(self.call('export',token)['media_hashes'],{})

    def call(self, action, token, identity=None, **kwargs):
        return sessions.dispatch(action, {"token": token, "instance_id": identity or self.items[0]["instance_id"], **kwargs})

    def blind_all(self, token):
        for item in self.items:
            self.call("blind", token, item["instance_id"], answer="A")

    def private_all(self, token, answer="A"):
        for item in self.items:
            self.call("evidence", token, item["instance_id"])
            self.call("private", token, item["instance_id"], answer=answer, rationale="独立查看相关私有状态与对话。")

    def final_all(self, token, answer="A"):
        for item in self.items:
            self.call("final", token, item["instance_id"], answer=answer, rationale="人工核验。",
                      human_attestation=True)

    def test_scene_sequence_blocks_skip_and_unlocks_only_after_scene_review(self):
        later = deepcopy(self.items[0])
        later.update(instance_id="scene-two-question", story_id="GPT50_002")
        self.items.append(later)
        value = sessions.dispatch("start", {"reviewer": "sequential", "prior_exposure": False, "modality": "text"})
        token = value["token"]
        self.assertEqual(value["active_scene"], "GPT50_001")
        for action in ("item", "blind", "evidence", "machine", "final"):
            with self.assertRaisesRegex(ValueError, "当前场景"):
                self.call(action, token, later["instance_id"], answer="A")
        for item in self.items[:2]:
            self.call("blind", token, item["instance_id"], answer="A")
        self.assertEqual(self.call("status", token)["stage"], "private_review")
        for item in self.items[:2]:
            self.call("evidence", token, item["instance_id"])
            self.call("private", token, item["instance_id"], answer="B", rationale="private evidence")
        self.call("machine", token)
        for item in self.items[:2]:
            self.call("final", token, item["instance_id"], answer="B", rationale="reviewed", human_attestation=True)
        resumed = self.call("status", token)
        self.assertEqual(resumed["active_scene"], "GPT50_002")
        self.assertEqual(resumed["stage"], "blind")
        with self.assertRaises(ValueError):
            self.call("evidence", token, later["instance_id"])
        # Evidence from scene one must not block blind answers to scene two.
        self.call("blind", token, later["instance_id"], answer="C")
        self.call("evidence", token, later["instance_id"])
        self.call("private", token, later["instance_id"], answer="C", rationale="independent")
        self.call("machine", token, later["instance_id"])
        final = self.call("final", token, later["instance_id"], answer="C", rationale="reviewed", human_attestation=True)
        self.assertEqual(final["stage"], "complete")
        exported = self.call("export", token)
        self.assertEqual(exported["blind_responses"][self.items[0]["instance_id"]]["answer"], "A")
        self.assertEqual(exported["machine_assisted_final_judgments"][self.items[0]["instance_id"]]["answer"], "B")
        self.assertEqual(len(exported["scene_progress"]), 2)

    def test_cannot_choose_a_later_scene_when_starting(self):
        later = deepcopy(self.items[0])
        later.update(instance_id="scene-two-question", story_id="GPT50_002")
        self.items.append(later)
        with self.assertRaisesRegex(ValueError, "固定顺序"):
            sessions.dispatch("start", {"reviewer": "skip", "prior_exposure": False, "modality": "text", "scenes": ["GPT50_002"]})

    def test_no_reference_before_whole_assignment_blind_completion(self):
        token = self.start()
        for action in ("evidence", "private", "machine", "final"):
            with self.assertRaises(ValueError):
                self.call(action, token, answer="A", rationale="test", human_attestation=True)
        self.call("blind", token, answer="A")
        with self.assertRaises(ValueError):
            self.call("evidence", token)
        self.call("blind", token, self.items[1]["instance_id"], answer="B")
        self.assertEqual(self.call("evidence", token)["private_state"], "SECRET_EVIDENCE")
        with self.assertRaises(ValueError):
            self.call("blind", token, answer="B")

    def test_machine_suggestions_wait_for_all_independent_private_judgments(self):
        token = self.start()
        self.blind_all(token)
        self.call("evidence", token)
        self.call("private", token, answer="B", rationale="私有证据依据")
        with self.assertRaises(ValueError):
            self.call("machine", token)
        other = self.items[1]["instance_id"]
        self.call("evidence", token, other)
        self.call("private", token, other, answer="C", rationale="另一题依据")
        self.assertIn("authoring", self.call("machine", token))
        with self.assertRaises(ValueError):
            self.call("private", token, answer="A", rationale="覆盖")
        self.final_all(token, "D")
        exported = sessions.dispatch("export", {"token": token})
        identity = self.items[0]["instance_id"]
        self.assertEqual(exported["blind_responses"][identity]["answer"], "A")
        self.assertEqual(exported["independent_private_judgments"][identity]["answer"], "B")
        self.assertEqual(exported["machine_assisted_final_judgments"][identity]["answer"], "D")
        self.assertFalse(exported["formal_ground_truth"])

    def test_public_input_has_no_authoring_or_difficulty(self):
        token = self.start()
        data = self.call("item", token)
        text = json.dumps(data)
        for key in ("authoring", "target_spec", "analysis", "primary_capability", "design_difficulty", "oracle_reference"):
            self.assertNotIn(key, text)
        self.assertEqual(data["public"], sessions.public_instance(self.items[0]))

    def test_persistence_and_previous_exposure_survive_new_session(self):
        token = self.start()
        self.blind_all(token)
        self.call("evidence", token)
        restored = sessions.load_session(token)
        self.assertEqual(len(restored["blind"]), 2)
        repeated = self.start()
        self.assertFalse(sessions.load_session(repeated)["baseline_eligible"])

    def test_gt_scoring_excludes_own_labels_and_requires_two_others(self):
        one = self.start("one")
        self.blind_all(one); self.private_all(one); self.final_all(one)
        results = sessions.human_results()
        self.assertIsNone(results["human_baselines"][0]["accuracy"])
        two = self.start("two")
        self.blind_all(two); self.private_all(two); self.final_all(two)
        self.assertTrue(all(x["status"] == "independent_human_consensus" for x in sessions.human_results()["ground_truth_candidates"]))
        self.assertTrue(all(x["accuracy"] is None for x in sessions.human_results()["human_baselines"]))
        three = self.start("three")
        self.blind_all(three); self.private_all(three); self.final_all(three)
        self.assertTrue(all(x["accuracy"] == 1 for x in sessions.human_results()["human_baselines"]))

    def test_quality_disagreement_does_not_become_gt(self):
        for name, answer in (("one", "A"), ("two", "B")):
            token = self.start(name)
            self.blind_all(token); self.private_all(token, answer); self.final_all(token, answer)
        self.assertTrue(all(x["status"] == "needs_adjudication" and x["answer"] is None
                            for x in sessions.human_results()["ground_truth_candidates"]))

    def test_unassigned_item_and_path_traversal_rejected(self):
        token = self.start()
        with self.assertRaises(ValueError):
            self.call("blind", token, "SFV2-002-T1-01", answer="A")
        with self.assertRaises(ValueError):
            sessions.dispatch("status", {"token": "../anything"})


if __name__ == "__main__":
    unittest.main()
