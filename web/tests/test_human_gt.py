import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from web import human_gt as h
from web import gate2_human as g


class HumanGTTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.release = h.release()
        cls.group_count = len(next(a for a in cls.release['assignments'] if a['track']=='offline_text')['item_ids'])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = patch.object(h, 'STORE', Path(self.tmp.name))
        self.patch.start()

    def tearDown(self):
        self.patch.stop(); self.tmp.cleanup()

    def receipt(self, reviewer, answer='A', data=None, track='offline_text'):
        data = data or self.release
        a = next(a for a in data['assignments'] if a['track'] == track)
        rows = [x for x in data['items'] if x['id'] in a['item_ids']]
        blind = {x['id']: {'answer': 'A', 'confidence': 'medium', 'rationale': '', 'issue': 'none'} for x in rows}
        gt = {x['id']: {'answer': answer, 'acceptable_answers': [answer], 'decision': 'usable', 'rationale': 'observed private state'} for x in rows}
        return {'format': 'socialflux_human_gt_v1', 'dataset_sha256': data['dataset_sha256'], 'receipt_id': 'receipt-' + reviewer,
            'reviewer_alias': reviewer, 'revision': 4, 'status': 'submitted', 'assignment': a,
            'item_hashes': {x['id']: x['item_sha256'] for x in rows}, 'blind_responses': blind, 'machine_assisted_gt': gt,
            'independent_t4_ratings': {}, 'workflow': {'phase': 'complete', 'attestedAt': 'now', 'blindLockedAt': 'before',
                                                    'baselineEligible': True, 'blind': blind, 'gt': gt}}

    def t4_receipt(self, reviewer='t4-one'):
        assignment = next(a for a in self.release['assignments'] if a['track'] == 't4')
        rows = [x for x in self.release['t4'] if x['id'] in assignment['item_ids']]
        ratings = {x['id']: {dimension: dict(score=5, evidence_turn_ids=[x['packet']['observable_trajectory'][0]['turn_id']],
                                              rationale='Observed turn supports this rating', insufficient_evidence=False)
                             for dimension in h.T4_DIMENSIONS} for x in rows}
        return dict(format='socialflux_human_gt_v1', dataset_sha256=self.release['dataset_sha256'], receipt_id='receipt-' + reviewer,
                    reviewer_alias=reviewer, revision=1, status='submitted', assignment=assignment,
                    item_hashes={x['id']: x['packet_sha256'] for x in rows}, blind_responses={}, machine_assisted_gt={},
                    independent_t4_ratings=ratings, workflow=dict(phase='complete', attestedAt='now', ratings=ratings, baselineEligible=True))

    def test_two_distinct_reviewers_and_leave_self_out(self):
        r = self.receipt('one'); h.import_receipt(r); h.import_receipt(r)
        self.assertEqual(h.load_human_gt()['gt_consensus'], 0)
        h.import_receipt(self.receipt('two'))
        summary = h.load_human_gt(); self.assertEqual(summary['gt_consensus'], self.group_count)
        self.assertFalse(next(x for x in summary['tables'] if x['id'] == 'human-blind-baseline')['rows'])
        h.import_receipt(self.receipt('three'))
        rows = next(x for x in h.load_human_gt()['tables'] if x['id'] == 'human-blind-baseline')['rows']
        self.assertEqual(sum(x[3] for x in rows), self.group_count * 3)
        self.assertTrue(all(x[-1] == 1 for x in rows))
        repeated = self.receipt('one'); repeated['receipt_id'] = 'receipt-one-again'; h.import_receipt(repeated)
        rows = next(x for x in h.load_human_gt()['tables'] if x['id'] == 'human-blind-baseline')['rows']
        self.assertEqual(sum(x[3] for x in rows), self.group_count * 3)
        conflicting = self.receipt('one'); conflicting['receipt_id'] = 'receipt-one-conflict'
        for row in conflicting['blind_responses'].values(): row['answer'] = 'B'
        h.import_receipt(conflicting)
        rows = next(x for x in h.load_human_gt()['tables'] if x['id'] == 'human-blind-baseline')['rows']
        self.assertEqual(sum(x[3] for x in rows), self.group_count * 2)

    def test_disagreement_and_repeated_alias_do_not_create_consensus(self):
        h.import_receipt(self.receipt('one'))
        repeated = self.receipt('one'); repeated['receipt_id'] = 'receipt-one-repeat'; h.import_receipt(repeated)
        self.assertEqual(h.load_human_gt()['gt_consensus'], 0)
        h.import_receipt(self.receipt('two', 'B'))
        self.assertEqual(h.load_human_gt()['gt_disputed'], self.group_count)

    def test_alias_whitespace_does_not_create_an_independent_reviewer(self):
        h.import_receipt(self.receipt('one'))
        repeated = self.receipt('one'); repeated['receipt_id'] = 'receipt-one-spaced'; repeated['reviewer_alias'] = ' one '
        h.import_receipt(repeated)
        self.assertEqual(h.load_human_gt()['gt_consensus'], 0)

    def test_wrong_source_and_premature_complete_are_rejected(self):
        bad = self.receipt('one'); bad['item_hashes'][next(iter(bad['item_hashes']))] = 'wrong'
        with self.assertRaises(ValueError): h.import_receipt(bad)

    def test_disagreement_requires_a_distinct_adjudicator_and_preserves_inputs(self):
        h.import_receipt(self.receipt('one')); h.import_receipt(self.receipt('two', 'B'))
        dispute = h.load_human_gt()['disputes'][0]
        value = {**dispute, 'reviewer': 'one', 'rationale': 'reviewed all evidence', 'answer': 'A', 'decision': 'usable', 'human_attestation': True}
        with self.assertRaises(ValueError): h.adjudicate(value)
        value['reviewer'] = 'third'; h.adjudicate(value)
        summary = h.load_human_gt()
        self.assertEqual(summary['gt_consensus'], 1); self.assertEqual(summary['gt_disputed'], self.group_count - 1)
        self.assertEqual(len(list(h.STORE.glob('*.json'))), 2)
        bad = self.receipt('one'); del bad['workflow']['blindLockedAt']
        with self.assertRaises(ValueError): h.import_receipt(bad)

    def test_absent_humans_never_generate_calibration_numbers(self):
        rows = next(x for x in h.load_human_gt()['tables'] if x['id'] == 'human-t4-calibration')['rows']
        self.assertTrue(all(row[1] == 0 and row[2:] == ['N/A'] * 5 for row in rows))

    def test_t4_audit_requires_locked_complete_scores_and_preserves_legacy(self):
        legacy = self.t4_receipt(); h.validate_receipt(legacy)
        record = copy.deepcopy(legacy)
        tasks = [dict(id='T4-trigger-' + scene, scene_id=scene, kind='T4-trigger', stage='review', sha256='task-' + scene,
                      questions=[dict(id='timing', choices=dict(appropriate='appropriate', uncertain='uncertain'))])
                 for scene in record['assignment']['scene_ids']]
        data = dict(dataset_sha256=record['dataset_sha256'], sha256='f' * 64, tasks=tasks)
        path = Path(self.tmp.name) / 'gate2-release.json'; path.write_text(json.dumps(data))
        answers = {t['id']: dict(values=dict(timing='appropriate'), rationale='Reviewed trace') for t in tasks}
        record['workflow'].update(ratingsLockedAt='earlier', gate2=dict(packet_sha256=data['sha256'], answers=answers))
        record['gate2_human_review'] = dict(packet_sha256=data['sha256'], answers=answers, task_hashes={t['id']: t['sha256'] for t in tasks})
        with patch.object(g, 'RELEASE', path):
            h.validate_receipt(record)
            record['status'] = 'in_progress'; record['workflow']['phase'] = 't4_review'
            h.validate_receipt(record)
            bad = copy.deepcopy(record); bad['workflow'].pop('ratingsLockedAt')
            with self.assertRaisesRegex(ValueError, '锁定'): h.validate_receipt(bad)
            bad = copy.deepcopy(record); bad['independent_t4_ratings'].pop(next(iter(bad['independent_t4_ratings'])))
            with self.assertRaisesRegex(ValueError, '整组轨迹'): h.validate_receipt(bad)
            bad = copy.deepcopy(record); bad['workflow']['ratings'] = {}
            with self.assertRaisesRegex(ValueError, '不一致'): h.validate_receipt(bad)
            bad = copy.deepcopy(record); bad.pop('gate2_human_review')
            with self.assertRaises(ValueError): h.validate_receipt(bad)

    def test_old_t4_packet_never_counts_as_current_calibration(self):
        record = self.t4_receipt()
        old = copy.deepcopy(self.release)
        for item in old['t4']:
            if item['id'] in record['item_hashes']:
                item['packet_sha256'] = 'old-' + item['packet_sha256']
                record['item_hashes'][item['id']] = item['packet_sha256']
        with patch.object(h, 'receipt_release', return_value=old):
            h.import_receipt(record)
            summary = h.load_human_gt()
        self.assertEqual(summary['submitted'], 1)
        rows = next(x for x in summary['tables'] if x['id'] == 'human-t4-calibration')['rows']
        self.assertTrue(all(row[1] == 0 and row[2:] == ['N/A'] * 5 for row in rows))

    def test_intermediate_media_release_receipts_remain_importable(self):
        archives = h.media_snapshot_releases(self.release)
        self.assertTrue(archives)
        for index, old in enumerate(archives):
            h.validate_receipt(self.receipt('archive-' + str(index), data=old))
            self.assertEqual(h.receipt_release(old['dataset_sha256'])['assignments'], old['assignments'])

    def test_replaced_media_does_not_mix_historical_video_baseline(self):
        # Media overlays belong to the legacy bank; the active candidate may
        # intentionally forbid combining records across release versions.
        base = h.legacy_release()
        group_count = len(next(a for a in base['assignments'] if a['track'] == 'offline_video')['item_ids'])
        snapshot = {k: copy.deepcopy(base[k]) for k in ('release', 'dataset_sha256', 'source_bank_sha256', 'assignments')}
        snapshot['dataset_sha256'] = 'a' * 64
        snapshot['items'] = [{k: copy.deepcopy(x[k]) for k in ('id', 'item_sha256', 'media', 'coverage')} | {'has_video': x['public_video'] is not None}
                             for x in base['items']]
        first = self.receipt('old-video', data=base, track='offline_video')['assignment']['item_ids'][0]
        next(x for x in snapshot['items'] if x['id'] == first)['media'][0]['sha256'] = 'old-video-hash'
        path = Path(self.tmp.name) / 'snapshots' / 'history.json'; path.parent.mkdir(); path.write_text(json.dumps([snapshot]))
        with patch.object(h, 'MEDIA_HISTORY', path):
            old = h.receipt_release(snapshot['dataset_sha256'])
            h.import_receipt(self.receipt('old-video', data=old, track='offline_video'))
            h.import_receipt(self.receipt('current-two', data=base, track='offline_video'))
            h.import_receipt(self.receipt('current-three', data=base, track='offline_video'))
            rows = next(x for x in h.load_human_gt(base['dataset_sha256'])['tables'] if x['id'] == 'human-blind-baseline')['rows']
        self.assertEqual(sum(x[3] for x in rows), group_count * 3 - 1)

    def test_claude_scores_require_matching_packet_and_valid_citations(self):
        item = copy.deepcopy(next(x for x in self.release['t4'] if x['machine']))
        row = {**item['machine'], 'status': 'completed', 'attempts': [{}]}
        item['machine'] = None
        directory = Path(self.tmp.name)
        target = directory / (item['id'] + '.json')
        machine, _, counts = h.claude_results({'t4': [item]}, directory)
        self.assertEqual(counts, {'pending': 1})
        target.write_text(json.dumps(row))
        machine, _, counts = h.claude_results({'t4': [item]}, directory)
        self.assertIsNotNone(machine[item['id']]); self.assertEqual(counts, {'completed': 1})
        row['packet_sha256'] = 'wrong'; target.write_text(json.dumps(row))
        machine, rows, counts = h.claude_results({'t4': [item]}, directory)
        self.assertIsNone(machine[item['id']]); self.assertEqual(counts, {'failed': 1})
        self.assertIn('不匹配', rows[0][-1])
        row['packet_sha256'] = item['packet_sha256']
        row['judgment']['dimensions']['recovery'].update(score=None, insufficient_evidence=True, evidence_turn_ids=[])
        target.write_text(json.dumps(row))
        machine, rows, counts = h.claude_results({'t4': [item]}, directory)
        self.assertIsNone(machine[item['id']]); self.assertIn('recovery', rows[0][-1])


if __name__ == '__main__': unittest.main()
