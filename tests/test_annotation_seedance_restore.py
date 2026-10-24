"""Small synthetic fixtures: no datasets, credentials, GPUs, or model calls."""
from copy import deepcopy
import unittest

from scripts.build_annotation_seedance_release import merge_media
from scripts.prepare_human_gt_release import digest


def freeze(value):
    value.pop('dataset_sha256', None)
    value['dataset_sha256'] = digest(value)
    return value


def fixture():
    media = dict(node_id='scene-t1', sha256='seedance-bytes', provider='seedance',
                 spoken_text='I will check.', full_public_response='I will check.',
                 source_quote='I will check.', evidence_ids=['t1'])
    def item(task):
        question = dict(instance_id=task, modality='text', input=dict(
            context={'public_situation': {'relationship_structure': ''}},
            history=[{'turn_id': 't1', 'environment_character': 'I will check.'}]))
        return dict(id=task, scene_id='scene', task=task, item_sha256='old-'+task,
                    public_text=question, public_video=None if task == 'T2' else {**deepcopy(question), 'modality': 'text+video'},
                    media=[] if task == 'T2' else [deepcopy(media)], coverage={'mode': 'text_only' if task == 'T2' else 'video'})
    seedance = freeze(dict(release='seedance', source_bank_sha256='original-bank',
        items=[item(t) for t in ('T1', 'T2', 'T3')], private={'T1': 'frozen-private'},
        evidence_blobs={'key': 'frozen-evidence'}, assignments=['unchanged'], media_readiness={'completed_nodes': 1}))
    current = deepcopy(seedance)
    current.update(release='public-context', source_bank_sha256='expanded-bank',
                   public_context_revision={'version': 1, 'source_bank_sha256': 'original-bank'})
    for row in current['items']:
        row['item_sha256'] = 'context-'+row['id']
        row['public_text']['input']['context']['public_situation']['relationship_structure'] = 'Colleagues.'
        row['public_video'] = {**deepcopy(row['public_text']), 'modality': 'text+video'}
        row['media'] = [deepcopy(media) | {'provider': 'local', 'sha256': 'local-bytes'}]
    return freeze(current), seedance


class SeedanceRestoreTests(unittest.TestCase):
    def test_restores_video_without_changing_answers_or_public_context(self):
        current, seedance = fixture()
        before = deepcopy(current)
        seed_before = deepcopy(seedance)
        revised, lineage = merge_media(current, seedance)
        self.assertEqual(current, before)
        self.assertEqual(seedance, seed_before)
        self.assertNotEqual(revised['dataset_sha256'], current['dataset_sha256'])
        for key in ('private', 'evidence_blobs', 'assignments', 'public_context_revision', 'source_bank_sha256'):
            self.assertEqual(revised[key], current[key])
        for old, new in zip(current['items'], revised['items']):
            self.assertEqual(old['public_text'], new['public_text'])
            self.assertEqual(old['item_sha256'], new['item_sha256'])
            if new['task'] == 'T2':
                self.assertIsNone(new['public_video'])
                self.assertEqual(new['media'], [])
            else:
                self.assertEqual(new['public_video']['input'], old['public_text']['input'])
                self.assertEqual(new['media'][0]['provider'], 'seedance')
        self.assertEqual(len(lineage), 3)

    def test_rejects_changed_history_even_when_new_hash_is_valid(self):
        current, seedance = fixture()
        current['items'][0]['public_text']['input']['history'][0]['environment_character'] = 'Different dialogue.'
        with self.assertRaisesRegex(ValueError, 'Question/history changed'):
            merge_media(freeze(current), seedance)

    def test_rejects_changed_scene_binding(self):
        current, seedance = fixture()
        current['items'][0]['scene_id'] = 'other-scene'
        with self.assertRaisesRegex(ValueError, 'Question/history changed'):
            merge_media(freeze(current), seedance)

    def test_rejects_changed_evidence_turn_or_spoken_line(self):
        for key, value in [('evidence_ids', ['future-turn']), ('spoken_text', 'Another line.')]:
            with self.subTest(key=key):
                current, seedance = fixture()
                current['items'][0]['media'][0][key] = value
                with self.assertRaisesRegex(ValueError, 'Checkpoint media binding mismatch'):
                    merge_media(freeze(current), seedance)

    def test_rejects_stale_dataset_hash(self):
        current, seedance = fixture()
        current['items'][0]['public_text']['input']['context'] = {}
        with self.assertRaisesRegex(ValueError, 'Frozen dataset hash mismatch'):
            merge_media(current, seedance)

    def test_rejects_unrelated_context_migration(self):
        current, seedance = fixture()
        current['public_context_revision']['source_bank_sha256'] = 'unrelated-bank'
        with self.assertRaisesRegex(ValueError, 'source bank lineage mismatch'):
            merge_media(freeze(current), seedance)


if __name__ == '__main__':
    unittest.main()
