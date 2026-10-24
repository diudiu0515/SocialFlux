"""Candidate registration never promotes or pools short and long stimuli."""
from contextlib import ExitStack
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from web import gate2_human as g
from web import human_gt as h


class CandidateReceiptTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.data = self.root / 'data'
        self.data.mkdir()
        self.store = self.data / 'receipts'
        self.registry = self.data / 'candidate-releases.json'
        self.old_path = self.data / 'old/release.json'
        self.new_path = self.data / 'candidate/release.json'
        self.old_gate_path = self.data / 'old/gate2-release.json'
        self.new_gate_path = self.data / 'candidate/gate2-release.json'
        self.stack.enter_context(patch.multiple(h, ROOT=self.root, STORE=self.store,
            RELEASE=self.old_path, ANNOTATION400_RELEASE=self.old_path,
            ANNOTATION400_FIRST_RELEASE=self.data / 'missing-first.json',
            MEDIA_HISTORY=self.data / 'missing-history.json', CANDIDATE_RELEASE_REGISTRY=self.registry))
        self.stack.enter_context(patch.object(g, 'RELEASE', self.old_gate_path))
        item = {'id': 'fixture-T1-01', 'item_sha256': '1' * 64, 'scene_id': 'scene', 'task': 'T1',
                'public_text': {'modality': 'text', 'question': 'What follows?', 'input': {}, 'options': {'A': 'A', 'B': 'B'}},
                'media': [{'asset_id': 'long-video', 'sha256': '2' * 64}], 'coverage': {}}
        item['public_video'] = {**item['public_text'], 'modality': 'text+video'}
        assignments = [{'id': 'group-' + mode, 'track': mode, 'scene_ids': ['scene'],
                        'item_ids': ['trajectory'] if mode == 't4' else [item['id']]}
                       for mode in ('offline_text', 'offline_video', 't4')]
        self.old = {'release': 'old-long', 'dataset_sha256': 'a' * 64, 'source_bank_sha256': 'f' * 64,
                    'items': [item], 'assignments': assignments, 'sampling': {}, 'rubric': {},
                    't4': [{'id': 'trajectory', 'packet_sha256': '3' * 64, 'machine': None,
                            'packet': {'observable_trajectory': [{'turn_id': 't1'}]}}]}
        self.new = copy.deepcopy(self.old)
        self.new.update(release='candidate-short', dataset_sha256='d' * 64)
        self.new['items'][0]['media'] = [{'asset_id': 'short-video', 'sha256': '4' * 64}]
        self.old_gate = self.packet(self.old, 'b' * 64)
        self.new_gate = self.packet(self.new, 'c' * 64)
        for path, value in ((self.old_path, self.old), (self.new_path, self.new),
                            (self.old_gate_path, self.old_gate), (self.new_gate_path, self.new_gate)):
            self.write(path, value)
        self.register()

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def register(self, **overrides):
        entry = {'dataset_sha256': self.new['dataset_sha256'],
                 'release_path': str(self.new_path.relative_to(self.root)),
                 'release_sha256': hashlib.sha256(self.new_path.read_bytes()).hexdigest(),
                 'gate2_release_path': str(self.new_gate_path.relative_to(self.root)),
                 'gate2_release_sha256': hashlib.sha256(self.new_gate_path.read_bytes()).hexdigest()}
        entry.update(overrides)
        self.write(self.registry, {'format': h.CANDIDATE_REGISTRY_FORMAT, 'releases': [entry]})

    def packet(self, release, digest):
        return {'dataset_sha256': release['dataset_sha256'], 'sha256': digest,
                'tasks': [{'id': 'same-public-task', 'kind': 'scenario', 'scene_id': 'scene',
                           'stage': 'review', 'sha256': '5' * 64,
                           'questions': [{'id': 'quality', 'choices': {'usable': 'usable'}}]}]}

    def record(self, who, data=None, answer='A', track='offline_video', with_gate=False):
        data = data or self.new
        assignment = next(a for a in data['assignments'] if a['track'] == track)
        hashes = {x['id']: x['packet_sha256' if track == 't4' else 'item_sha256']
                  for x in data['t4' if track == 't4' else 'items']}
        blind = {} if track == 't4' else {ident: {'answer': 'A'} for ident in hashes}
        gt = {} if track == 't4' else {ident: {'answer': answer, 'acceptable_answers': [answer],
                                               'decision': 'usable', 'rationale': 'Reviewed source'} for ident in hashes}
        ratings = {ident: {dimension: {'score': 5, 'rationale': 'Observed public turn',
                                       'evidence_turn_ids': ['t1'], 'insufficient_evidence': False}
                           for dimension in h.T4_DIMENSIONS} for ident in hashes} if track == 't4' else {}
        record = {'format': 'socialflux_human_gt_v1', 'dataset_sha256': data['dataset_sha256'],
                  'receipt_id': 'receipt-' + who, 'reviewer_alias': who, 'revision': 2, 'status': 'submitted',
                  'assignment': copy.deepcopy(assignment), 'item_hashes': hashes, 'blind_responses': blind,
                  'machine_assisted_gt': gt, 'independent_t4_ratings': ratings,
                  'workflow': {'phase': 'complete', 'attestedAt': 'now', 'blindLockedAt': 'before',
                               'baselineEligible': True, 'blind': blind, 'gt': gt, 'ratings': ratings}}
        if with_gate:
            packet = self.new_gate if data['dataset_sha256'] == self.new['dataset_sha256'] else self.old_gate
            tasks = g.assigned_tasks(packet, assignment)
            answers = {ident: {'values': {'quality': 'usable'}, 'rationale': 'Reviewed evidence'} for ident in tasks}
            record['workflow']['gate2'] = {'packet_sha256': packet['sha256'], 'answers': answers, 'independentLockedAt': 'before'}
            record['gate2_human_review'] = {'packet_sha256': packet['sha256'], 'answers': answers,
                'task_hashes': {ident: task['sha256'] for ident, task in tasks.items()}, 'independent_locked_at': 'before'}
        return record

    def rows(self, summary, ident):
        return next(t['rows'] for t in summary['tables'] if t['id'] == ident)

    def test_registration_is_required_does_not_promote_and_zero_receipts_are_not_results(self):
        self.registry.unlink()
        with self.assertRaises(ValueError):
            h.validate_receipt(self.record('new'))
        h.validate_receipt(self.record('old', self.old))
        self.register()
        h.validate_receipt(self.record('new', with_gate=True))
        self.assertEqual(h.release()['dataset_sha256'], self.old['dataset_sha256'])
        current = h.load_human_gt()
        candidate = h.load_human_gt(self.new['dataset_sha256'])
        self.assertEqual(current['dataset_sha256'], self.old['dataset_sha256'])
        self.assertTrue(candidate['registered_candidate'])
        self.assertEqual(candidate['sessions'], 0)
        self.assertEqual(candidate['gt_consensus'], 0)
        self.assertEqual(candidate['gate2']['reviewed'], 0)
        self.assertEqual(self.rows(candidate, 'human-blind-baseline'), [])

    def test_explicit_activation_switches_default_without_merging_or_losing_legacy(self):
        h.import_receipt(self.record('old-one', self.old, with_gate=True))
        h.import_receipt(self.record('new-one', with_gate=True))
        registry = json.loads(self.registry.read_text())
        registry['active_dataset_sha256'] = self.new['dataset_sha256']
        self.write(self.registry, registry)
        self.assertEqual(h.release()['dataset_sha256'], self.new['dataset_sha256'])
        self.assertEqual(h.receipt_release(self.old['dataset_sha256']), self.old)
        current = h.load_human_gt()
        self.assertEqual(current['dataset_sha256'], self.new['dataset_sha256'])
        self.assertEqual(current['submitted'], 1)
        self.assertEqual(current['gate2']['packet_sha256'], self.new_gate['sha256'])
        self.assertEqual(h.load_human_gt(self.old['dataset_sha256'])['submitted'], 1)
        self.assertEqual(json.loads(self.old_path.read_text()), self.old)
        self.assertEqual(json.loads(self.old_gate_path.read_text()), self.old_gate)
        registry.pop('active_dataset_sha256')
        self.write(self.registry, registry)
        self.assertEqual(h.release()['dataset_sha256'], self.old['dataset_sha256'])
        h.validate_receipt(self.record('new-after-rollback', with_gate=True))

    def test_unregistered_or_changed_active_release_fails_closed_but_old_receipts_work(self):
        registry = json.loads(self.registry.read_text())
        registry['active_dataset_sha256'] = 'e' * 64
        self.write(self.registry, registry)
        with self.assertRaisesRegex(ValueError, '未显式注册'):
            h.release()
        h.validate_receipt(self.record('old-unregistered-active', self.old, with_gate=True))
        registry['active_dataset_sha256'] = self.new['dataset_sha256']
        self.write(self.registry, registry)
        self.new_path.write_text(self.new_path.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            h.release()
        h.validate_receipt(self.record('old-changed-active', self.old, with_gate=True))

    def test_fake_dataset_packet_and_changed_registered_files_are_rejected(self):
        bad = self.record('fake', with_gate=True)
        bad['dataset_sha256'] = 'e' * 64
        with self.assertRaises(ValueError):
            h.validate_receipt(bad)
        bad = self.record('fake', with_gate=True)
        bad['workflow']['gate2']['packet_sha256'] = 'e' * 64
        bad['gate2_human_review']['packet_sha256'] = 'e' * 64
        with self.assertRaises(ValueError):
            h.validate_receipt(bad)
        self.new_gate_path.write_text(self.new_gate_path.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            h.validate_receipt(self.record('changed-gate', with_gate=True))
        self.register()
        self.new_path.write_text(self.new_path.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            h.validate_receipt(self.record('changed-release'))
        h.validate_receipt(self.record('old-still-readable', self.old, with_gate=True))

    def test_registry_does_not_read_paths_outside_data(self):
        self.register(release_path='../outside.json')
        with self.assertRaisesRegex(ValueError, 'data'):
            h.receipt_release(self.new['dataset_sha256'])

    def test_same_receipt_ids_and_new_revisions_do_not_replace_or_pool_old_video(self):
        for who in ('one', 'two', 'three'):
            h.import_receipt(self.record(who, self.old))
            new = self.record(who, answer='B')
            new['revision'] = 20
            h.import_receipt(new)
        current, candidate = h.load_human_gt(), h.load_human_gt(self.new['dataset_sha256'])
        self.assertEqual(current['total_sessions'], 6)
        self.assertEqual((current['sessions'], candidate['sessions']), (3, 3))
        self.assertEqual((current['gt_consensus'], candidate['gt_consensus']), (1, 1))
        old_rows, new_rows = self.rows(current, 'human-blind-baseline'), self.rows(candidate, 'human-blind-baseline')
        self.assertEqual((old_rows[0][3], old_rows[0][-1]), (3, 1.0))
        self.assertEqual((new_rows[0][3], new_rows[0][-1]), (3, 0.0))
        self.assertEqual([c['submitted'] for c in current['dataset_cohorts']], [3, 3])

    def test_identical_text_and_item_hash_do_not_supply_cross_candidate_gt(self):
        h.import_receipt(self.record('old-one', self.old, track='offline_text'))
        h.import_receipt(self.record('old-two', self.old, track='offline_text'))
        h.import_receipt(self.record('new-one', track='offline_text'))
        current, candidate = h.load_human_gt(), h.load_human_gt(self.new['dataset_sha256'])
        self.assertEqual((current['submitted'], candidate['submitted']), (2, 1))
        self.assertEqual((current['gt_consensus'], candidate['gt_consensus']), (1, 0))
        self.assertEqual(self.rows(current, 'human-blind-baseline'), [])
        self.assertEqual(self.rows(candidate, 'human-blind-baseline'), [])

    def test_matching_t4_packets_remain_separate_by_candidate_dataset(self):
        h.import_receipt(self.record('new-t4', track='t4'))
        current, candidate = h.load_human_gt(), h.load_human_gt(self.new['dataset_sha256'])
        self.assertTrue(all(row[2] == 0 for row in self.rows(current, 'human-t4-pairs')))
        self.assertTrue(all(row[2] == 1 for row in self.rows(candidate, 'human-t4-pairs')))

    def test_adjudications_and_legacy_unscoped_decisions_do_not_cross_candidate(self):
        for data in (self.old, self.new):
            h.import_receipt(self.record('one', data, 'A'))
            h.import_receipt(self.record('two', data, 'B'))
        dispute = h.load_human_gt()['disputes'][0]
        decision = {**dispute, 'reviewer': 'independent', 'rationale': 'Reviewed the dispute',
                    'decision': 'usable', 'answer': 'A', 'human_attestation': True}
        h.adjudicate(decision)
        self.assertEqual(h.load_human_gt()['gt_consensus'], 1)
        self.assertEqual(h.load_human_gt(self.new['dataset_sha256'])['gt_disputed'], 1)
        legacy = {k: v for k, v in decision.items() if k != 'dataset_sha256'}
        self.write(self.store / 'adjudications/legacy.json', legacy)
        candidate_dispute = h.load_human_gt(self.new['dataset_sha256'])['disputes'][0]
        h.adjudicate({**decision, **candidate_dispute, 'answer': 'B'})
        self.assertEqual(self.rows(h.load_human_gt(), 'human-gt-coverage')[0][3], 'A')
        self.assertEqual(self.rows(h.load_human_gt(self.new['dataset_sha256']), 'human-gt-coverage')[0][3], 'B')

    def test_gate2_common_task_hashes_do_not_pool_candidate_votes(self):
        old, new = self.record('old-vote', self.old, with_gate=True), self.record('new-vote', with_gate=True)
        h.import_receipt(old)
        h.import_receipt(new)
        self.assertEqual(g.gate2_coverage([old, new])['rows'][0][3], 1)
        self.assertEqual(g.gate2_coverage([old, new], data=self.new_gate)['rows'][0][3], 1)
        self.assertEqual(h.load_human_gt(self.new['dataset_sha256'])['gate2']['packet_sha256'], self.new_gate['sha256'])
        self.assertFalse((self.old_gate_path.parent / 'versions').exists())


if __name__ == '__main__':
    unittest.main()
