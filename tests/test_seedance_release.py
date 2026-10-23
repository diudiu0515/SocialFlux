"""Real-bank regression: 300 video questions, 100 text-only T2, frozen answers."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from scripts import export_seedance_release as release


class SeedanceReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = release.load(release.ROOT / 'data/offline_checkpoint_annotation_20261023/release.json')
        items = [json.loads(s) for s in release.BANK.read_text().splitlines() if s.strip()]
        cls.nodes = release.public_nodes(items)
        cls.assets = {n['node_id']: dict(node_id=n['node_id'], sha256='test-'+n['node_id'], url='/media/test.mp4')
                      for n in cls.nodes if n['location'] != 'ending'}

    def test_full_question_and_answer_bank_survives_the_media_change(self):
        revised = release.bind_media(self.source, self.nodes, self.assets)
        for key in ('assignments', 'private', 'evidence_blobs', 't4', 'source_bank_sha256'):
            self.assertEqual(revised[key], self.source[key], key)
        for before, after in zip(self.source['items'], revised['items']):
            for key in ('id', 'scene_id', 'task', 'item_sha256', 'public_text'):
                self.assertEqual(before[key], after[key], key)
        self.assertNotEqual(self.source['dataset_sha256'], revised['dataset_sha256'])

    def test_every_t1_t3_history_node_has_video_and_t2_has_none(self):
        revised = release.bind_media(self.source, self.nodes, self.assets)
        self.assertEqual(sum(bool(i['public_video']) for i in revised['items']), 300)
        self.assertEqual(len({v['node_id'] for i in revised['items'] for v in i['media']}), 100)
        for item in revised['items']:
            if item['task'] == 'T2':
                self.assertIsNone(item['public_video'])
                self.assertEqual(item['media'], [])
                self.assertFalse(item['coverage']['video_required'])
            else:
                self.assertEqual({t['turn_id'] for t in item['public_text']['input']['history']},
                                 {e for v in item['media'] for e in v['evidence_ids']})
        groups = [g for g in revised['assignments'] if g['track'] == 'offline_video']
        self.assertEqual(len({i for g in groups for i in g['item_ids']}), 400)
        for group in groups:
            self.assertEqual(len(group['item_ids']), 8 * len(group['scene_ids']))

    def test_e8_rebinds_same_event_without_mutating_frozen_task(self):
        from scripts.refresh_online_state_videos import OLD
        old_rows = [r for r in release.load(OLD)['requests'] if r.get('video_sha256')]
        by_sha = {r['video_sha256']: r for r in old_rows}
        replacements = {r['media_asset_id']: {**r, 'video_sha256': 'new-'+r['video_sha256'],
            'prompt_sha256': 'new-prompt'} for r in old_rows}
        current = release.load(release.ROOT / 'data/offline_checkpoint_annotation_20261023/gate2-release.json')
        tasks = [t for t in current['tasks'] if t['kind'] == 'E8']
        self.assertEqual(len(tasks), 40)
        with patch.object(release.gate2, 'copy_video', side_effect=lambda site, path, sha, url: dict(sha256=sha, url=url)):
            for task in tasks:
                frozen = deepcopy(task)
                revised = release.replace_e8_video(task, by_sha, replacements, None)
                self.assertEqual(task, frozen)
                self.assertNotEqual(revised['id'], task['id'])
                self.assertNotEqual(revised['sha256'], task['sha256'])
                for key in ('scene_id', 'questions', 'source_sha256'):
                    self.assertEqual(revised[key], task[key])
                for key, value in task['evidence'].items():
                    self.assertEqual(revised['evidence'][key], value)
                self.assertEqual(revised['video']['url'], '/media/'+revised['video']['sha256']+'.mp4')
                self.assertEqual(revised['evidence']['media_refresh']['media_asset_id'], by_sha[task['video']['sha256']]['media_asset_id'])

    def test_changed_question_binding_and_missing_history_fail_closed(self):
        nodes = deepcopy(self.nodes)
        node = next(n for n in nodes if n['location'] == 't1')
        node['bindings'][0]['item_sha256'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'binding mismatch'):
            release.bind_media(self.source, nodes, self.assets)
        with self.assertRaisesRegex(ValueError, 'coverage'):
            release.bind_media(self.source, [n for n in self.nodes if n['location'] != 't2'], self.assets)


if __name__ == '__main__':
    unittest.main()
