import copy
import json
from pathlib import Path
import unittest

from web.gate2_human import RELEASE, validate_gate2, gate2_coverage


class Gate2HumanTests(unittest.TestCase):
    def record(self, data=None):
        data = data or json.loads(RELEASE.read_text())
        scene = next(t['scene_id'] for t in data['tasks'] if t['kind'] == 'E1')
        tasks = [t for t in data['tasks'] if t['scene_id'] == scene]
        answers = {t['id']: {'values': {q['id']: next(iter(q['choices'])) for q in t['questions']}, 'rationale': 'Reviewed exact evidence'} for t in tasks}
        state = dict(packet_sha256=data['sha256'], answers=answers, independentLockedAt='earlier')
        return dict(dataset_sha256=data['dataset_sha256'], assignment=dict(track='offline_text', scene_ids=[scene]),
                    reviewer_alias='one', status='submitted', workflow=dict(phase='complete', gate2=state, attestedAt='now', baselineEligible=True),
                    gate2_human_review=dict(packet_sha256=data['sha256'], answers=answers, independent_locked_at='earlier',
                                           task_hashes={t['id']: t['sha256'] for t in tasks}))

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


if __name__ == '__main__': unittest.main()
