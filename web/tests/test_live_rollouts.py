import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from web import live_rollouts as live


class LiveRolloutsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.active = self.root / 'active'
        self.source = self.root / 'scenarios'
        self.history = self.root / 'history'
        self.write(self.source / 'manifest.json', {'cases': [
            {'scenario_id': 'GPT50_001', 'candidate': 'scenario.json'},
        ]})
        self.write(self.root / 'scenario.json', {'scenario_id': 'GPT50_001', 'initial_state': {'emotion': {'hope': 4}}})
        for name, value in {'ROOT': self.root, 'ACTIVE': self.active, 'SCENARIOS': self.source,
                            'SOURCES': [('current', 'current', self.active, False),
                                        ('invalid_horizon', 'old', self.history, True)]}.items():
            p = patch.object(live, name, value)
            p.start()
            self.addCleanup(p.stop)

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def test_checkpoint_exposes_completed_turns_without_request_logs(self):
        self.write(self.active / '00_GPT50_001_gpt/checkpoint.json', {
            'turns': [{'turn_id': 't1', 'state_after': {'emotion': {'hope': 5}},
                       'provider_request': {'api_key': 'must-not-be-exposed'}}]})
        detail = live.load_live('GPT50_001')
        self.assertEqual(detail['versions'][0]['turns'][0]['state_after']['emotion']['hope'], 5)
        self.assertNotIn('must-not-be-exposed', json.dumps(detail))
        self.assertNotIn('_path', detail['versions'][0])
        self.assertEqual(live.load_live()['counts']['readable'], 1)
        self.assertEqual(detail['human_review_status'], 'pending')

    def test_history_does_not_count_as_current_completion(self):
        self.write(self.history / '00_GPT50_001_gpt/trajectory.json', {'turns': [{'turn_id': 't1'}]})
        result = live.load_live()
        self.assertEqual(result['counts']['completed'], 0)
        self.assertEqual(result['counts']['readable'], 0)
        self.assertEqual(result['scenarios'][0]['turn_count'], 0)
        self.assertTrue(result['scenarios'][0]['versions'][0]['invalid_configuration'])

    def test_final_trajectory_replaces_checkpoint(self):
        folder = self.active / '00_GPT50_001_gpt'
        self.write(folder / 'checkpoint.json', {'turns': [{'turn_id': 't1'}]})
        self.write(folder / 'trajectory.json', {'turns': [{'turn_id': 't1'}, {'turn_id': 't2'}]})
        self.write(folder / 'result.json', {'status': 'completed', 'turns': 2})
        result = live.load_live()
        self.assertEqual(result['counts']['completed'], 1)
        self.assertEqual(result['scenarios'][0]['turn_count'], 2)
        self.assertEqual(live.load_live('GPT50_001')['versions'][0]['artifact_kind'], 'trajectory.json')

    def test_unknown_id_and_interrupted_json_write(self):
        self.assertIsNone(live.load_live('../scenario.json'))
        folder = self.active / '00_GPT50_001_gpt'
        folder.mkdir(parents=True)
        (folder / 'checkpoint.json').write_text('{')
        self.assertEqual(live.load_live()['counts']['readable'], 0)

    def test_trigger_evidence_is_allowlisted_and_absence_is_not_empty(self):
        folder = self.active / '00_GPT50_001_gpt'
        self.write(folder / 'checkpoint.json', {'turns': [
            {'turn_id': 't1', 'trigger_events': [{'trigger_id': 'trigger_1',
                'media_asset_id': 'exact_asset', 'trigger_variables': {'emotion.hope': 5},
                'video_api_request': {'secret': 'must-not-be-exposed'},
                'asset_path': '/private/path'}]},
            {'turn_id': 't2', 'trigger_events': []}, {'turn_id': 't3'}]})
        detail = live.load_live('GPT50_001')
        turns = detail['versions'][0]['turns']
        self.assertEqual(turns[0]['trigger_events'][0]['media_asset_id'], 'exact_asset')
        self.assertEqual(turns[1]['trigger_events'], [])
        self.assertIsNone(turns[2]['trigger_events'])
        self.assertNotIn('must-not-be-exposed', json.dumps(detail))
        self.assertNotIn('/private/path', json.dumps(detail))

    def test_translation_cannot_replace_original_trigger_evidence(self):
        folder = self.active / '00_GPT50_001_gpt'
        turn = {'turn_id': 't1', 'trigger_events': [{'trigger_id': 'original'}]}
        self.write(folder / 'checkpoint.json', {'trajectory_id': 'same', 'turns': [turn]})
        self.write(folder / 'english/review.json', {'rollout': {
            'trajectory_id': 'same', 'turns': [{**turn, 'trigger_events': [{'trigger_id': 'invented'}]}]}})
        result = live.load_live('GPT50_001')['versions'][0]
        self.assertEqual(result['language'], 'en')
        self.assertEqual(result['turns'][0]['trigger_events'][0]['trigger_id'], 'original')

    def test_english_export_is_same_trajectory_and_prefix_not_another_rollout(self):
        folder = self.active / '00_GPT50_001_gpt'
        turn = {'turn_id': 't1', 'policy_action': {'text': '我会发送。'},
                'environment_response': '好的。', 'state_before': {'hope': 4},
                'state_after': {'hope': 4}}
        self.write(folder / 'checkpoint.json', {'trajectory_id': 'original', 'turns': [turn, {**turn, 'turn_id': 't2'}]})
        self.write(folder / 'english/review.json', {
            'rollout': {'trajectory_id': 'original', 'turns': [{**turn,
                'policy_action': {'text': 'I will send it.'}, 'environment_response': 'Okay.'}]},
            'localization': {'language': 'en', 'semantic_equivalence_review': 'pending'}})
        item = live.load_live('GPT50_001')['versions'][0]
        self.assertEqual(item['language'], 'en')
        self.assertEqual(item['source_turn_count'], 2)
        self.assertEqual(item['turn_count'], 1)
        self.assertEqual(item['turns'][0]['policy_action']['text'], 'I will send it.')
        self.assertEqual(item['translation_review'], 'pending')
        self.assertEqual(live.load_live()['scenarios'][0]['turn_count'], 2)
        self.write(folder / 'english/review.json', {'rollout': {'trajectory_id': 'wrong', 'turns': [turn]}})
        self.assertNotIn('language', live.load_live('GPT50_001')['versions'][0])

    def prepare_gate_review(self, decision='reject', partial=False):
        path=self.active/'00_GPT50_001_gpt/trajectory.json'
        self.write(path, {'trajectory_id':'current-id','turns':[{'turn_id':'t1'}]})
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        self.write(self.active/'gate3_followup/gate3/model_reviews.json', {'records':[{
            'scenario_id':'GPT50_001','trajectory_id':'current-id','source_sha256':digest,
            'decision':decision,'source_status':'generation_error' if partial else 'completed_unreviewed',
            'scores':{'naturalness':3},'hard_reject_reasons':[],
            'rationale':'Repeated acknowledgments.','evidence':{'naturalness':['t1']},
            'private_provider_log':{'api_key':'do-not-expose'},
        }]})
        return path,digest

    def test_gate3_reject_is_visible_in_list_and_details_with_evidence(self):
        self.prepare_gate_review()
        overview=live.load_live()
        self.assertEqual(overview['counts']['gate3_rejected'],1)
        self.assertEqual(overview['scenarios'][0]['gate3']['decision'],'reject')
        detail=live.load_live('GPT50_001')
        review=detail['versions'][0]['gate3']
        self.assertEqual(review['rationale'],'Repeated acknowledgments.')
        self.assertEqual(review['evidence']['naturalness'],['t1'])
        self.assertEqual(review['human_review_status'],'pending')
        self.assertNotIn('do-not-expose',json.dumps(detail))

    def test_gate3_is_not_attached_to_history_or_changed_source(self):
        path,_=self.prepare_gate_review()
        self.write(self.history/'00_GPT50_001_gpt/trajectory.json',
                   {'trajectory_id':'old-id','turns':[{'turn_id':'t1'}]})
        items=live.load_live('GPT50_001')['versions']
        self.assertEqual(items[1]['gate3']['status'],'historical_not_reviewed')
        self.assertNotIn('decision',items[1]['gate3'])
        self.write(path, {'trajectory_id':'current-id','turns':[{'turn_id':'t1','changed':True}]})
        self.assertEqual(live.load_live()['counts']['gate3_rejected'],0)
        self.assertEqual(live.load_live('GPT50_001')['versions'][0]['gate3']['status'],'source_changed')

    def test_partial_approval_is_explicit_and_gate2_errors_are_not_rejections(self):
        _,digest=self.prepare_gate_review('approve',partial=True)
        self.write(self.active/'gate2_followup/gate2/experiments/environment_interventions.json',
                   {'records':[{'scenario_id':'GPT50_001','source_trajectory_id':'current-id',
                     'checkpoint_turn_id':'t1','error':{'type':'ProviderHTTPError',
                     'message':'Unsupported top_p; api_key=do-not-expose'}}]})
        self.write(self.active/'gate2_followup/rollouts/scenario_001/trajectory.json',
                   {'gate2_audit_input':{'source_sha256':digest}})
        overview=live.load_live()
        self.assertEqual(overview['counts']['gate2_errors'],1)
        self.assertEqual(overview['counts']['gate3_rejected'],0)
        item=overview['scenarios'][0]
        self.assertTrue(item['gate3']['partial'])
        self.assertEqual(item['gate2_errors'][0]['message'],'接口不支持 top_p 参数')
        self.assertNotIn('do-not-expose',json.dumps(overview))

    def test_missing_review_does_not_imply_approval(self):
        self.write(self.active/'00_GPT50_001_gpt/trajectory.json',
                   {'trajectory_id':'current-id','turns':[{'turn_id':'t1'}]})
        item=live.load_live()['scenarios'][0]
        self.assertEqual(item['gate3']['status'],'pending')
        self.assertNotIn('decision',item['gate3'])


if __name__ == '__main__':
    unittest.main()
