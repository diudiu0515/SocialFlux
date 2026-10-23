"""Version boundaries and shortened speech must not change questions or old reviews."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from scripts import build_gate2_annotation as gate2
from scripts import export_checkpoint_annotation as export


class CheckpointAnnotationExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.site = self.root / 'build/site'
        self.media_path = self.site / 'public/media/clip.mp4'
        self.media_path.parent.mkdir(parents=True)
        self.media_path.write_bytes(b'new checkpoint video')
        sha = gate2.file_sha(self.media_path)
        self.full = 'I will check the record before proceeding. Approval remains pending.'
        self.short = 'I will check the record before proceeding.'
        public = dict(instance_id='item', modality='text', question='What remains uncertain?',
            input={'history': [{'turn_id': 't1', 'environment_character': self.full,
                                'observable_expression': {'gaze': 'steady'}}]})
        self.old_asset = dict(asset_id='old', sha256='f' * 64, url='/media/old.mp4',
                              spoken_text=self.full, evidence_ids=['t1'])
        self.asset = dict(asset_id='new', node_id='scene-t1', sha256=sha, url='/media/clip.mp4',
            spoken_scope='checkpoint_sentence', spoken_text=self.short, full_public_response=self.full,
            source_quote=self.short, human_review='pending', duration_seconds=4.6)
        self.research = dict(release='old', dataset_sha256='old-dataset', source_bank_sha256='bank',
            items=[dict(id='item', scene_id='scene', item_sha256='item-hash', public_text=public,
                        public_video=public | {'modality': 'text+video'}, media=[self.old_asset],
                        coverage={'complete': True, 'covered_evidence_ids': ['t1']})],
            assignments=[dict(id='offline_video-01', scene_ids=['scene'], item_ids=['item'])],
            private={'item': 'PRIVATE_PACKET_UNCHANGED'}, evidence_blobs={'blob': 'PRIVATE_BLOB_UNCHANGED'},
            t4=[dict(id='t4-frozen', packet={'trajectory': ['unchanged']})], media_readiness={})
        self.node = dict(node_id='scene-t1', scenario_id='scene', speaker={'name': 'A'}, location='t1',
            source_public_response=self.full, source_observable_expression={'gaze': 'steady'},
            bindings=[dict(instance_id='item', item_sha256='item-hash', evidence_ids=['t1'])])
        self.request = {k: deepcopy(v) for k, v in self.node.items() if k not in ('bindings', 'source_public_response')}
        self.request.update(source_public_response=self.short, full_public_response=self.full,
                            source_spec_sha256='original-spec', checkpoint_line={
                                'checkpoint_text': self.short, 'original_response': self.full,
                                'source_quote': self.short, 'verbatim_excerpt': True})
        self.row = {'node_id': 'scene-t1', 'scenario_id': 'scene'}

    def revised(self):
        return export.replace_media(self.research, [self.node], {'scene-t1': self.asset})

    def registry(self):
        tasks = []
        for kind in ('scenario', 'E8', 'T4-trigger', 'media-quality'):
            task = dict(id=kind, kind=kind, scene_id='scene', evidence={'old': 'frozen'}, stage='review')
            task['sha256'] = gate2.digest(task)
            tasks.append(task)
        bundle = dict(format='socialflux_gate2_review_v1', dataset_sha256='old-dataset', tasks=tasks)
        bundle['sha256'] = gate2.digest(bundle)
        return gate2.compact_registry(dict(current=bundle['sha256'], versions=[bundle]))

    def test_new_media_version_preserves_complete_questions_and_private_packets(self):
        before = deepcopy(self.research)
        result = self.revised()
        self.assertEqual(self.research, before)
        for key in ('source_bank_sha256', 'private', 'evidence_blobs', 't4', 'assignments'):
            self.assertEqual(result[key], before[key])
        for key in ('id', 'scene_id', 'item_sha256', 'public_text', 'public_video'):
            self.assertEqual(result['items'][0][key], before['items'][0][key])
        self.assertNotEqual(result['dataset_sha256'], before['dataset_sha256'])
        self.assertFalse(result['items'][0]['coverage']['complete_spoken_response'])
        self.assertEqual(result['items'][0]['media'][0]['spoken_text'], self.short)
        self.assertNotIn('frame_review', result['items'][0]['media'][0])
        snapshot = export.media_snapshot(before)
        self.assertEqual(snapshot['items'][0]['media'], [self.old_asset])

    def test_media_cannot_attach_to_wrong_question_hash(self):
        self.node['bindings'][0]['item_sha256'] = 'other-item'
        with self.assertRaisesRegex(ValueError, 'question binding mismatch'):
            self.revised()

    def test_lineage_checks_original_full_response_and_frozen_spec(self):
        export.validate_lineage(self.row, self.request, self.node, {'spec_sha256': 'original-spec'})
        for field, value in [('full_public_response', self.full.replace('pending', 'confirmed')),
                             ('source_spec_sha256', 'different-original'),
                             ('speaker', {'name': 'B'}), ('source_observable_expression', {'gaze': 'down'})]:
            with self.subTest(field=field):
                request = deepcopy(self.request)
                request[field] = value
                with self.assertRaisesRegex(ValueError, 'lineage mismatch'):
                    export.validate_lineage(self.row, request, self.node, {'spec_sha256': 'original-spec'})

    def test_source_quote_must_be_exact_and_verbatim_claim_true(self):
        for quote in ('Approval is confirmed.', 'Approval remains pending.'):
            with self.subTest(quote=quote):
                request = deepcopy(self.request)
                request['checkpoint_line']['source_quote'] = quote
                with self.assertRaisesRegex(ValueError, 'source quote mismatch'):
                    export.validate_lineage(self.row, request, self.node, {'spec_sha256': 'original-spec'})

    def test_gate2_appends_version_and_retains_every_non_media_task(self):
        registry = self.registry()
        before = deepcopy(registry)
        frame = {'findings': {'cue_visibility': {'finding': 'Needs full playback'}},
                 'priority': 'priority_visual_rewatch'}
        revised = self.revised()
        result, bundle, coverage, retained = export.replace_media_reviews(registry, revised, self.site,
            [{'node_id': 'scene-t1', 'frame_review': frame}])
        self.assertEqual(registry, before)
        self.assertEqual(result['versions'][0], gate2.expand_registry(before)['versions'][0])
        self.assertEqual(retained, 3)
        for old in result['versions'][0]['tasks'][:-1]:
            self.assertEqual(next(t for t in bundle['tasks'] if t['id'] == old['id']), old)
        task = next(t for t in bundle['tasks'] if t['kind'] == 'media-quality')
        self.assertEqual(task['stage'], 'review')
        self.assertEqual(task['tracks'], ['offline_video'])
        self.assertEqual(task['evidence']['public_turns'][0]['environment_character'], self.full)
        self.assertEqual(task['evidence']['spoken_text'], self.short)
        self.assertEqual(task['evidence']['frame_review']['human_review'], 'pending')
        self.assertNotIn('frame_review', revised['items'][0]['media'][0])
        self.assertEqual(task['sha256'], gate2.digest({k:v for k,v in task.items() if k != 'sha256'}))
        self.assertEqual(coverage['review_tasks'], 1)
        self.assertEqual(gate2.expand_registry(gate2.compact_registry(result)), result)

    def test_gate2_rejects_wrong_full_dialogue_quote_and_turn_id(self):
        for field, value in [('full_public_response', 'Approval is now confirmed.'),
                             ('source_quote', 'A fabricated quote.'), ('evidence_ids', ['t2'])]:
            with self.subTest(field=field):
                revised = self.revised()
                revised['items'][0]['media'][0][field] = value
                with self.assertRaises(ValueError):
                    export.replace_media_reviews(self.registry(), revised, self.site)

    def test_old_full_dialogue_gate2_behavior_is_unchanged(self):
        revised = self.revised()
        media = revised['items'][0]['media'][0]
        for key in ('spoken_scope', 'full_public_response', 'source_quote', 'node_id'):
            media.pop(key)
        media['spoken_text'] = self.full
        _, bundle, _, _ = export.replace_media_reviews(self.registry(), revised, self.site)
        task = next(t for t in bundle['tasks'] if t['kind'] == 'media-quality')
        self.assertEqual(task['evidence']['spoken_text'], self.full)
        self.assertNotIn('spoken_scope', task['evidence'])

    def test_export_refuses_production_site_or_frozen_output(self):
        with self.assertRaisesRegex(ValueError, 'isolated build'):
            export.export(self.root / 'web/participant_demo', self.root / 'data/offline_checkpoint_annotation_test', root=self.root)
        with self.assertRaisesRegex(ValueError, 'isolated build'):
            export.export(self.site, self.root / 'data/offline_annotation400_en_20261022', root=self.root)


if __name__ == '__main__':
    unittest.main()
