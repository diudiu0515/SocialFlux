import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from web import gate2_human as g
from web.gate2_human import RELEASE, assigned_tasks, validate_gate2, gate2_coverage


class Gate2HumanTests(unittest.TestCase):
    def record(self, data=None, track='offline_text'):
        data = data or json.loads(RELEASE.read_text())
        scene = next(t['scene_id'] for t in data['tasks'] if t['kind'] == ('T4-trigger' if track == 't4' else 'E1'))
        assignment = dict(track=track, scene_ids=[scene])
        tasks = list(assigned_tasks(data, assignment).values())
        answers = {t['id']: {'values': {q['id']: next(iter(q['choices'])) for q in t['questions']}, 'rationale': 'Reviewed exact evidence'} for t in tasks}
        state = dict(packet_sha256=data['sha256'], answers=answers, independentLockedAt='earlier')
        record = dict(dataset_sha256=data['dataset_sha256'], assignment=assignment,
                    reviewer_alias='one', status='submitted', workflow=dict(phase='complete', gate2=state, attestedAt='now', baselineEligible=True),
                    gate2_human_review=dict(packet_sha256=data['sha256'], answers=answers, independent_locked_at='earlier',
                                           task_hashes={t['id']: t['sha256'] for t in tasks}))
        if track == 't4':
            record['workflow']['ratingsLockedAt'] = 'earlier'
            state.pop('independentLockedAt')
            record['gate2_human_review'].pop('independent_locked_at')
        return record

    def expanded_bundle(self):
        tasks = [dict(id=kind, scene_id='scene-1', kind=kind, stage='review' if kind != 'E1' else 'independent', sha256=kind,
                      questions=[dict(id='quality', choices=dict(usable='usable', revise='revise', uncertain='uncertain'))], machine=dict(quality='usable'))
                 for kind in ('E1', 'scenario', 'media-quality', 'T4-trigger', 'T4-video')]
        return dict(sha256='f' * 64, dataset_sha256='frozen-dataset', tasks=tasks)

    def test_bound_completed_receipt_and_legacy(self):
        validate_gate2(self.record())
        validate_gate2(dict(workflow=dict(phase='complete')))

    def test_archived_packets_remain_valid_after_material_expansion(self):
        current = json.loads(RELEASE.read_text())
        archives = [json.loads(p.read_text()) for p in (RELEASE.parent / 'versions').glob('*.json')]
        for data in archives:
            if data['sha256'] != current['sha256']:
                validate_gate2(self.record(data))

    def test_no_foreign_task_no_hash_substitution_no_missing_vote(self):
        for mutation in ('foreign', 'hash', 'missing', 'unlocked'):
            with self.subTest(mutation=mutation):
                r = self.record()
                if mutation == 'foreign': r['workflow']['gate2']['answers']['foreign'] = {'values': {}, 'rationale': 'x'}
                if mutation == 'hash': r['gate2_human_review']['task_hashes'][next(iter(r['gate2_human_review']['task_hashes']))] = 'bad'
                if mutation == 'missing': r['workflow']['gate2']['answers'].pop(next(iter(r['workflow']['gate2']['answers'])))
                if mutation == 'unlocked': r['workflow']['gate2'].pop('independentLockedAt')
                with self.assertRaises(ValueError): validate_gate2(r)

    def test_unique_reviewer_and_conflicting_repeats(self):
        r = self.record(); one = gate2_coverage([r]); repeated = gate2_coverage([r, copy.deepcopy(r)])
        self.assertEqual(one['rows'], repeated['rows'])
        conflict = copy.deepcopy(r)
        for answer in conflict['gate2_human_review']['answers'].values(): answer['rationale'] = 'conflict'
        result = gate2_coverage([r, conflict])
        self.assertEqual(result['reviewed'], 0)
        self.assertGreater(sum(row[5] for row in result['rows']), 0)
        self.assertFalse(result['formal_admission'])

    def test_t4_score_lock_and_modality_task_boundaries(self):
        data = self.expanded_bundle()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'release.json'; path.write_text(json.dumps(data))
            with patch.object(g, 'RELEASE', path):
                for track, expected in [('offline_text', {'E1', 'scenario'}),
                                        ('offline_video', {'E1', 'scenario', 'media-quality'}),
                                        ('t4', {'T4-trigger', 'T4-video'})]:
                    record = self.record(data, track)
                    validate_gate2(record)
                    self.assertEqual(set(record['gate2_human_review']['answers']), expected)
                t4 = self.record(data, 't4')
                t4['workflow'].pop('ratingsLockedAt')
                with self.assertRaisesRegex(ValueError, '锁定'): validate_gate2(t4)
                t4 = self.record(data, 't4'); t4['status'] = 'in_progress'; t4['workflow']['phase'] = 'blind'
                with self.assertRaises(ValueError): validate_gate2(t4)
                t4['workflow']['phase'] = 't4_review'
                t4['workflow']['gate2']['answers'].clear()
                validate_gate2(t4)
                t4['status'] = 'submitted'; t4['workflow']['phase'] = 'complete'
                with self.assertRaisesRegex(ValueError, '尚未完成'): validate_gate2(t4)

    def test_coverage_reports_two_people_disagreements_and_never_admission(self):
        data = self.expanded_bundle()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'release.json'; path.write_text(json.dumps(data))
            with patch.object(g, 'RELEASE', path):
                one = self.record(data, 't4')
                two = copy.deepcopy(one); two['reviewer_alias'] = 'two'
                summary = gate2_coverage([one, two])
                self.assertEqual(summary['two_reviewers'], 2)
                self.assertFalse(summary['formal_admission'])
                self.assertTrue(all(row[4] == '待审核' for row in summary['status_rows'] if not row[1].startswith('T4-')))
                two['gate2_human_review']['answers']['T4-video']['values']['quality'] = 'revise'
                summary = gate2_coverage([one, two])
                status = next(row for row in summary['status_rows'] if row[0] == 'T4-video')
                self.assertIn('分歧', status[4]); self.assertIn('revise=1', status[5])
                two['gate2_human_review']['task_hashes']['T4-video'] = 'wrong'
                self.assertEqual(gate2_coverage([one, two])['two_reviewers'], 0)

    def test_final_media_review_rejects_unwatched_or_defective_usable_vote(self):
        data = self.expanded_bundle()
        media = next(t for t in data['tasks'] if t['kind'] == 'media-quality')
        media['questions'] += [dict(id='playback', choices=dict(partial='partial', watched_listened='watched_listened')),
                               dict(id='usability', choices=dict(usable='usable', revise='revise'))]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'release.json'; path.write_text(json.dumps(data))
            with patch.object(g, 'RELEASE', path):
                record = self.record(data, 'offline_video')
                with self.assertRaisesRegex(ValueError, '完整观看'): validate_gate2(record)
                record['status'] = 'in_progress'; record['workflow']['phase'] = 'gt'
                validate_gate2(record)
                record['status'] = 'submitted'; record['workflow']['phase'] = 'complete'
                values = record['gate2_human_review']['answers']['media-quality']['values']
                values['playback'] = 'watched_listened'; values['quality'] = 'uncertain'
                with self.assertRaisesRegex(ValueError, '未确认'): validate_gate2(record)
                values['usability'] = 'revise'; validate_gate2(record)

    def test_missing_trigger_media_cannot_be_marked_available(self):
        data = self.expanded_bundle()
        trigger = next(t for t in data['tasks'] if t['kind'] == 'T4-trigger')
        trigger['evidence'] = dict(media_coverage=dict(missing=4, available_exact_bound=0))
        trigger['questions'].append(dict(id='media_verifiability', choices=dict(complete='complete', partial='partial', missing='missing')))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'release.json'; path.write_text(json.dumps(data))
            with patch.object(g, 'RELEASE', path):
                record = self.record(data, 't4')
                with self.assertRaisesRegex(ValueError, '缺失'): validate_gate2(record)
                values = record['gate2_human_review']['answers']['T4-trigger']['values']
                values['media_verifiability'] = 'partial'
                with self.assertRaisesRegex(ValueError, '没有精确绑定'): validate_gate2(record)
                values['media_verifiability'] = 'missing'; validate_gate2(record)

    def progressive_record(self):
        data = self.expanded_bundle()
        data['tasks'] = [task for task in data['tasks'] if task['kind'] in ('E1', 'scenario')]
        data['tasks'] += [{**task, 'id': task['id'] + '-2', 'scene_id': 'scene-2'} for task in data['tasks'][:]]
        record = self.record(data)
        record['assignment']['scene_ids'] = ['scene-1', 'scene-2']
        record['status'] = 'in_progress'
        record['workflow'].update(phase='blind', sceneSequence={
            'version': 1, 'index': 0, 'completed': {},
            'scenes': [{'id': 'scene-1'}, {'id': 'scene-2'}]})
        record['workflow']['gate2']['answers'].clear()
        record['workflow']['gate2'].pop('independentLockedAt')
        record['gate2_human_review'].pop('independent_locked_at')
        return data, record

    def test_progressive_receipt_accepts_only_exact_visible_hashes(self):
        data, record = self.progressive_record()
        with patch.object(g, 'receipt_packet', return_value=data):
            validate_gate2(record)
            for mutation in ('future_hash', 'missing_hash', 'hash', 'order', 'index', 'bool_index', 'future_answer'):
                with self.subTest(mutation=mutation):
                    bad = copy.deepcopy(record)
                    if mutation == 'future_hash': bad['gate2_human_review']['task_hashes']['E1-2'] = 'E1'
                    if mutation == 'missing_hash': bad['gate2_human_review']['task_hashes'].pop('E1')
                    if mutation == 'hash': bad['gate2_human_review']['task_hashes']['E1'] = 'wrong'
                    if mutation == 'order': bad['workflow']['sceneSequence']['scenes'].reverse()
                    if mutation == 'index': bad['workflow']['sceneSequence']['index'] = 2
                    if mutation == 'bool_index': bad['workflow']['sceneSequence']['index'] = False
                    if mutation == 'future_answer': bad['workflow']['gate2']['answers']['E1-2'] = {'values': {}, 'rationale': ''}
                    with self.assertRaises(ValueError): validate_gate2(bad)

    def test_previous_scene_stays_complete_while_current_scene_is_blind(self):
        data, record = self.progressive_record()
        completed = self.record(data)
        record['workflow']['gate2']['answers'].update(completed['workflow']['gate2']['answers'])
        record['workflow']['sceneSequence'].update(index=1, completed={
            'scene-1': {'blindLockedAt': 'earlier', 'independentLockedAt': 'earlier', 'submittedAt': 'earlier'}})
        record['gate2_human_review']['task_hashes'] = {task['id']: task['sha256'] for task in data['tasks']}
        with patch.object(g, 'receipt_packet', return_value=data):
            validate_gate2(record)
            missing = copy.deepcopy(record)
            missing['workflow']['gate2']['answers'].pop('scenario')
            with self.assertRaisesRegex(ValueError, '尚未完成'): validate_gate2(missing)
            record['workflow']['gate2']['answers']['E1-2'] = {'values': {}, 'rationale': ''}
            with self.assertRaisesRegex(ValueError, '未开放'): validate_gate2(record)


if __name__ == '__main__': unittest.main()
