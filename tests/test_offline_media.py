"""Offline video bindings follow frozen public history, not just scene IDs."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from offline.choice_builder import load, public_turn, save, sha
from offline.choice_media import pair_assets
from scripts.evaluate_offline_choice import call_item
from tests.test_offline_choice import item


class OfflineMediaTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.output = self.root / 'bank'
        self.video = self.root / 'clip.mp4'
        self.video.write_bytes(b'frozen video')
        self.source = self.root / 'trajectory.json'
        self.turn = {'turn_id': 't1', 'policy_action': {'text': '已核对'},
                     'environment_response': '好', 'media': [{'media_asset_id': 's1:cue'}]}
        self.trajectory = {'scenario_id': 's1', 'turns': [self.turn]}
        save(self.source, self.trajectory)
        self.question = item()
        self.question['input']['history'] = [public_turn(self.turn)]
        self.question['authoring']['construction_source'] = {
            'trajectory_path': str(self.source), 'trajectory_sha256': sha(self.source)}
        self.manifest = self.root / 'manifest.json'
        self.record = {'media_asset_id': 's1:cue', 'scenario_id': 's1',
                       'status': 'generated_structural_pass', 'video_file': 'clip.mp4',
                       'video_sha256': sha(self.video), 'response_neutral': True}
        save(self.manifest, {'batch_root': str(self.root), 'requests': [self.record]})

    def pair(self, **kwargs):
        return pair_assets([self.question], self.manifest, self.output, frames=False, **kwargs)

    def test_changed_public_words_or_expression_cannot_keep_source_video(self):
        for field, replacement in [('environment_character', '改写台词'),
                                   ('observable_expression', {'gaze': 'averted'}),
                                   ('evaluated_agent', '尚未核对')]:
            with self.subTest(field=field):
                self.question['input']['history'] = [public_turn(self.turn)]
                self.question['input']['history'][0][field] = replacement
                report = self.pair()
                self.assertEqual(report['logical_pairs'], 0)
                self.assertIn('public_history_changed', {r['reason'] for r in report['gaps']})

    def test_future_video_is_excluded_and_source_hash_is_checked(self):
        self.trajectory['turns'].append({**self.turn, 'turn_id': 't2',
                                         'media': [{'media_asset_id': 'future-only'}]})
        save(self.source, self.trajectory)
        with self.assertRaisesRegex(ValueError, 'trajectory checksum'):
            self.pair()
        self.question['authoring']['construction_source']['trajectory_sha256'] = sha(self.source)
        report = self.pair()
        self.assertEqual(report['logical_pairs'], 1)
        self.assertEqual(report['gaps'], [])
        self.assertEqual(load(self.output / 'media.json')['q1-video'][0]['evidence_ids'], ['t1'])

    def test_t2_only_binds_unchanged_shared_prefix_not_controlled_ending(self):
        self.question.update(task='T2', subtype='history_comparison', pair_id='controlled')
        del self.question['input']['history']
        for key, side in [('history_a', 'A'), ('history_b', 'B')]:
            self.question['input'][key] = [public_turn(self.turn, side + ':'),
                {'turn_id': side + ':t2', 'evaluated_agent': side,
                 'environment_character': '共同回应见 ending'}]
        self.question['input']['shared_ending'] = {'turn_id': 'ending', 'environment_character': '好'}
        self.question['authoring']['evidence_ids'] = ['A:t1', 'B:t1']
        report = self.pair()
        self.assertEqual(report['coverage'][0]['uncovered_evidence_ids'], ['ending'])
        self.assertEqual(load(self.output / 'media.json')['q1-video'][0]['evidence_ids'], ['A:t1', 'B:t1'])
        for key in ('history_a', 'history_b'):
            self.question['input'][key][0]['environment_character'] = '一起改写前史'
        self.assertEqual(self.pair()['logical_pairs'], 0)

    def test_missing_asset_is_reported_but_changed_file_is_rejected(self):
        self.record['status'] = 'request_ready'
        save(self.manifest, {'batch_root': str(self.root), 'requests': [self.record]})
        report = self.pair()
        self.assertEqual(report['coverage_counts'], {'missing': 1})
        self.assertEqual(report['gaps'][0]['source_status'], 'request_ready')
        self.record['status'] = 'generated_structural_pass'
        save(self.manifest, {'batch_root': str(self.root), 'requests': [self.record]})
        self.video.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'hash changed'):
            self.pair()

    def test_pairs_preserve_current_answers_and_frames_reach_model(self):
        before = deepcopy(self.question)
        frame = self.root / 'frame.jpg'
        frame.write_bytes(b'frame fixture')
        frames = [{'path': str(frame), 'sha256': sha(frame), 'timestamp_seconds': .25}]
        with patch('offline.choice_media.extract_frames', return_value=frames) as extract:
            report = pair_assets([self.question], self.manifest, self.output,
                                 frame_root=self.root / 'frames')
        extract.assert_called_once()
        self.assertEqual(self.question, before)
        pairs = [json.loads(line) for line in (self.output / 'paired.items.jsonl').read_text().splitlines()]
        self.assertEqual(pairs[0]['authoring']['answer'], pairs[1]['authoring']['answer'])
        self.assertEqual(pairs[0]['input'], pairs[1]['input'])
        self.assertEqual(report['media_sha256'], sha(self.output / 'media.json'))
        assets = load(self.output / 'media.json')['q1-video']
        with patch('scripts.evaluate_offline_choice.build_provider') as provider:
            provider.return_value.complete.return_value = '{"answer":"A"}'
            result = call_item(pairs[1], {'provider': 'mock'}, media=assets, transport='video_frames')
        self.assertNotIn('call_error', result)
        messages = provider.return_value.complete.call_args.args[0]
        self.assertEqual(sum(b['type'] == 'image_url' for b in messages[0]['content']), 1)
        self.assertNotIn('authoring', messages[0]['content'][0]['text'])
        assets[0]['evidence_ids'] = ['context']
        with patch('scripts.evaluate_offline_choice.build_provider') as provider:
            result = call_item(pairs[1], {'provider': 'mock'}, media=assets, transport='video_frames')
        provider.assert_not_called()
        self.assertIn('frozen question bindings', result['call_error']['message'])


if __name__ == '__main__':
    unittest.main()
