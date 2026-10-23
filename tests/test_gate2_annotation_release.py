"""Check the real frozen release boundaries and prohibit media/source substitution."""
import json
import base64
import gzip
import tempfile
import unittest
from pathlib import Path

from scripts.build_gate2_annotation import (ROOT, REGISTRY_FORMAT, checked_source,
    compact_registry, copy_video, digest, expand_registry, file_sha, unpack)


class Gate2AnnotationReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = ROOT / 'web/participant_demo'
        cls.research = unpack(json.loads((cls.site / 'data/research-server.json').read_text())['gzip_base64'])
        registry = expand_registry(unpack(json.loads((cls.site / 'data/gate2-review-server.json').read_text())['gzip_base64']))
        cls.bundle = next(v for v in registry['versions'] if v['sha256'] == registry['current'])
        cls.tasks = cls.bundle['tasks']

    def test_current_media_is_complete_deduplicated_and_post_vote(self):
        expected = {m['sha256'] for item in self.research['items'] for m in item['media']}
        audits = [t for t in self.tasks if t['kind'] == 'media-quality']
        self.assertEqual(len(expected), self.research['media_readiness']['required_nodes'])
        self.assertEqual(len(audits), len(expected))
        self.assertEqual({t['video']['sha256'] for t in audits}, expected)
        for task in audits:
            self.assertEqual(task['stage'], 'review')
            self.assertEqual(task['tracks'], ['offline_video'])
            self.assertTrue(task['evidence']['spoken_text'])
            self.assertTrue(task['evidence']['public_turns'])
            question_ids = {q['id'] for q in task['questions']}
            self.assertTrue({'playback', 'dialogue', 'lipsync', 'expression', 'identity', 'context', 'audio', 'usability'} <= question_ids)
            path = self.site / 'public' / task['video']['url'].lstrip('/')
            self.assertEqual(file_sha(path), task['video']['sha256'])

    def test_rollout_covers_every_scene_without_relabeling_partial_sources(self):
        expected = {i['scene_id'] for i in self.research['items']}
        rollouts = {t['scene_id']: t for t in self.tasks if t['kind'] == 'rollout'}
        self.assertEqual(set(rollouts), expected)
        for sid in ('GPT50_001', 'GPT50_009', 'GPT50_023', 'GPT50_033'):
            task = rollouts[sid]
            self.assertIs(task['evidence']['source_complete'], False)
            self.assertEqual(task['evidence']['source_status'], 'partial_source_prefix')
            provenance = task['evidence']['provenance']
            self.assertEqual(file_sha(ROOT / provenance['trajectory_path']), task['source_sha256'])

    def test_t4_tasks_use_exact_sampled_sources_and_retain_missing_denominator(self):
        sample = {x['id']: x for x in self.research['t4']}
        triggers = [t for t in self.tasks if t['kind'] == 'T4-trigger']
        videos = [t for t in self.tasks if t['kind'] == 'T4-video']
        self.assertEqual({t['scene_id'] for t in triggers}, set(sample))
        self.assertEqual(len(triggers), 50)
        for task in triggers + videos:
            self.assertEqual(task['tracks'], ['t4'])
            self.assertEqual(task['stage'], 'review')
            self.assertEqual(task['evidence']['trajectory_id'], task['scene_id'])
            self.assertEqual(task['source_sha256'], sample[task['scene_id']]['trajectory_sha256'])
        total_events = total_missing = 0
        for task in triggers:
            evidence = task['evidence']
            self.assertEqual(file_sha(ROOT / evidence['source_path']), task['source_sha256'])
            expected = sample[task['scene_id']]['packet']['observable_trajectory']
            actual = evidence['turns']
            self.assertEqual([t['turn_id'] for t in actual], [t['turn_id'] for t in expected])
            for turn, frozen in zip(actual, expected):
                self.assertEqual(turn['environment_response'], frozen['environment_response'])
                self.assertEqual(turn['evaluated_action'], frozen['evaluated_action'])
            c = evidence['media_coverage']
            self.assertEqual(c['trigger_events'], c['available_exact_bound'] + c['missing'])
            total_events += c['trigger_events']
            total_missing += c['missing']
        self.assertEqual(total_events, 348)
        self.assertEqual(total_events, len(videos) + total_missing)
        self.assertGreater(total_missing, 0)
        for task in videos:
            binding = task['evidence']['binding']
            self.assertTrue(all(binding['rendering_comparison'].values()))
            self.assertEqual(file_sha(ROOT / binding['source_path']), task['source_sha256'])
            self.assertEqual(file_sha(self.site / 'public' / task['video']['url'].lstrip('/')), task['video']['sha256'])

    def test_package_hashes_and_legacy_versions_remain_readable(self):
        bundle = dict(self.bundle)
        self.assertEqual(bundle.pop('sha256'), digest(bundle))
        self.assertEqual(bundle['dataset_sha256'], self.research['dataset_sha256'])
        self.assertEqual(len(self.tasks), len({t['id'] for t in self.tasks}))
        for task in self.tasks:
            value = dict(task)
            self.assertEqual(value.pop('sha256'), digest(value))
        server = unpack(json.loads((self.site / 'data/gate2-review-server.json').read_text())['gzip_base64'])
        self.assertEqual(server['current'], self.bundle['sha256'])
        self.assertGreater(len(server['versions']), 1)
        self.assertEqual(sum(t['kind'] == 'E8' for t in self.tasks), 40)
        self.assertFalse(any(t['kind'].startswith(('S1', 'S2', 'caption')) for t in self.tasks))

    def test_changed_source_and_published_video_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.json'
            path.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'Frozen source changed'):
                checked_source(path, '0' * 64)
            target = Path(directory) / 'site/public/media'
            target.mkdir(parents=True)
            (target / 'clip.mp4').write_bytes(b'wrong-published-bytes')
            with self.assertRaisesRegex(ValueError, 'Published video mismatch'):
                copy_video(Path(directory) / 'site', path, file_sha(path), '/media/clip.mp4')

    def test_compact_registry_preserves_every_archived_version_and_order(self):
        payload = json.loads((self.site / 'data/gate2-review-server.json').read_text())['gzip_base64']
        raw = gzip.decompress(base64.b64decode(payload))
        registry = json.loads(raw)
        self.assertEqual(registry['format'], REGISTRY_FORMAT)
        expanded = expand_registry(registry)
        # Revisions add unique media tasks, while common frozen evidence stays pooled.
        self.assertLess(len(raw), len(json.dumps(expanded).encode()) * .65)
        archived = {p.stem: p for p in (ROOT / 'data/gate2_annotation_20261022/versions').glob('*.json')}
        self.assertTrue(set(archived) <= {v['sha256'] for v in expanded['versions']})
        self.assertGreaterEqual(len(expanded['versions']), 11)
        for packed, version in zip(registry['versions'], expanded['versions']):
            self.assertNotIn('tasks', packed)
            if version['sha256'] in archived:
                self.assertEqual(version, json.loads(archived[version['sha256']].read_text()))
            self.assertEqual(version['sha256'], digest({k: v for k, v in version.items() if k != 'sha256'}))
            for ref, task in zip(packed['task_refs'], version['tasks']):
                self.assertIs(task, registry['task_pool'][ref])
                self.assertEqual(ref, digest({k: v for k, v in task.items() if k != 'sha256'}))
        self.assertEqual(compact_registry(registry), registry)

    def test_registry_deduplicates_content_without_rewriting_bundle_metadata(self):
        task = dict(id='same-task', evidence={'state': 10.0})
        task['sha256'] = digest(task)
        first = dict(format='fixture', dataset_sha256='dataset-a', tasks=[task], note='legacy')
        first['sha256'] = digest(first)
        second = dict(first, dataset_sha256='dataset-b')
        second['sha256'] = digest({k: v for k, v in second.items() if k != 'sha256'})
        legacy = dict(current=second['sha256'], versions=[first, second])
        compact = compact_registry(legacy)
        self.assertEqual(len(compact['task_pool']), 1)
        self.assertEqual(expand_registry(compact), legacy)
        self.assertEqual(legacy['versions'][0]['tasks'], [task])
        self.assertNotIn('task_refs', legacy['versions'][0])

    def test_registry_rejects_conflicting_content_and_invalid_references(self):
        task = dict(id='task', evidence='original')
        task['sha256'] = digest(task)
        collision = dict(task, evidence='changed')
        legacy = dict(current='version', versions=[dict(sha256='version', tasks=[task, collision])])
        with self.assertRaisesRegex(ValueError, 'Conflicting Gate2 task content'):
            compact_registry(legacy)
        legacy['versions'][0]['tasks'] = [collision]
        with self.assertRaisesRegex(ValueError, 'task content hash mismatch'):
            compact_registry(legacy)
        legacy['versions'][0]['tasks'] = [task]
        compact = compact_registry(legacy)
        compact['versions'][0]['task_refs'].append('missing')
        with self.assertRaisesRegex(ValueError, 'Missing or mismatched'):
            expand_registry(compact)
        # Python considers 10 and 10.0 equal, but frozen JSON digests do not.
        numeric = dict(id='numeric', evidence=10.0)
        numeric['sha256'] = digest(numeric)
        legacy['versions'][0]['tasks'] = [numeric, dict(numeric, evidence=10)]
        with self.assertRaisesRegex(ValueError, 'Conflicting Gate2 task content'):
            compact_registry(legacy)


if __name__ == '__main__':
    unittest.main()
