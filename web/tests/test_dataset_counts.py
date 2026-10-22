"""Inventory boundaries: failures, unique questions, and independent T4 runs."""
import json
import hashlib
from pathlib import Path
import tempfile
import unittest

from web.dataset_counts import (BANK, ANNOTATION_BANK, CF_SCENARIOS, GPT_ACTIVE, GPT_SCENARIOS,
                                inspect_trajectory, load_dataset_counts, summarize_offline)
from web.experiment_tables import dataset_tables


class DatasetCountsTests(unittest.TestCase):
    def test_complete_prefix_and_generation_error_are_distinct(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'trajectory.json'
            value = dict(scenario_id='GPT50_001', turns=[{'turn_id': 't1'}],
                         ending={'turn_id': 1, 'reason': 'natural_completion'})
            def inspect():
                path.write_text(json.dumps(value))
                stat = path.stat()
                return inspect_trajectory(str(path), stat.st_mtime_ns, stat.st_size, 'GPT50_001')[0]
            self.assertEqual(inspect(), 'usable')
            value['ending'] = None
            self.assertEqual(inspect(), 'invalid')
            value['generation_error'] = {'message': 'PRIVATE PROVIDER CONTENT'}
            self.assertEqual(inspect(), 'failed')
            self.assertNotIn('PRIVATE', str(inspect_trajectory(str(path), path.stat().st_mtime_ns,
                                                             path.stat().st_size, 'GPT50_001')))

    def test_pending_is_not_a_failed_hard_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def write(path, value):
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(value))
            members = []
            for i in range(1, 4):
                identity = f'GPT50_{i:03}'
                scenario = GPT_SCENARIOS / f'scenarios/gpt_{i:03}.json'
                write(scenario, {'scenario_id': identity})
                members.append({'scenario_id': identity, 'candidate': str(scenario)})
            write(GPT_SCENARIOS / 'manifest.json', {'cases': members})
            write(CF_SCENARIOS / 'manifest.json', {'results': []})
            write(GPT_ACTIVE / '00_GPT50_001_gpt/trajectory.json',
                  dict(scenario_id='GPT50_001', turns=[{'turn_id': 't1'}],
                       ending={'turn_id': 1, 'reason': 'natural_completion'}))
            write(GPT_ACTIVE / '01_GPT50_002_gpt/result.json', {'status': 'call_or_validation_failure'})
            result = load_dataset_counts(root)
            cohort = result['cohorts'][0]
            self.assertEqual([cohort[k] for k in ('scenarios', 'usable', 'failed', 'pending')], [3, 1, 1, 1])
            self.assertEqual([x['scenario_id'] for x in result['t4hard_candidates']], ['GPT50_002'])
            self.assertIsNone(result['offline'])
            self.assertTrue(result['read_errors'])

    def test_modalities_do_not_double_questions_and_pairs_require_both(self):
        items = [dict(instance_id=str(i), story_id='GPT50_001', task='T1',
                      analysis={'design_difficulty': difficulty})
                 for i, difficulty in enumerate(('ordinary', 'hard', None))]
        variants = [dict(metadata={'modality_pair_id': identity}, modality=modality)
                    for identity, modality in [('0', 'text'), ('0', 'text+video'), ('1', 'text'),
                                               ('2', 'text'), ('2', 'text+video'), ('2', 'text+video')]]
        data = summarize_offline(items, variants)
        self.assertEqual([data[k] for k in ('total', 'ordinary', 'hard', 'unknown', 'pairs')], [3, 1, 1, 1, 1])
        self.assertEqual(data['cohorts']['CF150']['total'], 0)
        with self.assertRaises(ValueError):
            summarize_offline(items + items, variants)

    def test_stale_pairing_cannot_appear_as_zero_or_current(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bank = root / BANK
            bank.mkdir(parents=True)
            (bank / 'items.jsonl').write_text(json.dumps(dict(instance_id='one', task='T1',
                story_id='GPT50_001', analysis={'design_difficulty': 'ordinary'})))
            (bank / 'paired.items.jsonl').write_text('')
            (bank / 'pairing_report.json').write_text('{"items_sha256":"stale"}')
            data = load_dataset_counts(root)
            self.assertIsNone(data['offline']['pairs'])
            self.assertIsNone(data['cohorts'][0]['scenarios'])
            overview = dataset_tables({'dataset_counts': data})[0]
            self.assertEqual(overview['rows'][-1][1], 'N/A')

    def test_annotation_release_supersedes_old_bank_and_stale_manifest_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for path, size in [(BANK, 3), (ANNOTATION_BANK, 4)]:
                bank = root / path
                bank.mkdir(parents=True)
                rows = [dict(instance_id=str(i), task='T1', story_id='GPT50_001',
                             analysis={'design_difficulty': 'ordinary'}) for i in range(size)]
                raw = '\n'.join(map(json.dumps, rows)).encode()
                (bank / 'items.jsonl').write_bytes(raw)
                digest = hashlib.sha256(raw).hexdigest()
                (bank / 'manifest.json').write_text(json.dumps({'items_sha256': digest, 'release': 'test'}))
                (bank / 'paired.items.jsonl').write_text('')
                (bank / 'pairing_report.json').write_text(json.dumps({'items_sha256': digest}))
            current = load_dataset_counts(root)
            self.assertEqual(current['offline']['total'], 4)
            self.assertEqual(current['offline']['bank_path'], str(ANNOTATION_BANK))
            (root / ANNOTATION_BANK / 'manifest.json').write_text('{"items_sha256":"wrong"}')
            invalid = load_dataset_counts(root)
            self.assertIsNone(invalid['offline'])
            self.assertTrue(any(e['error'] == 'AnnotationBankHashMismatch' for e in invalid['read_errors']))

    def test_t4_continuations_stay_separate_and_missing_condition_is_na(self):
        model = dict(conditions={'text_only': {'n': 4}}, matched_scenarios=2,
                     status_counts={'failed': 3, 'delegated_to_run': 9})
        runs = [dict(id=identity, kind=kind, models={'gpt': model}) for identity, kind in
                [('first', 'reliable_cohort'), ('continued', 'full_cohort_continuation'),
                 ('original', 'historical_scoring')]]
        table = next(t for t in dataset_tables({'dataset_counts': {'generated_at': 'now'}, 't4_runs': runs})
                     if t['id'] == 't4-counts')
        self.assertEqual(len(table['rows']), 2)
        self.assertEqual([r[0] for r in table['rows']], ['first', 'continued'])
        self.assertEqual(table['rows'][1][2:], [4, 'N/A', 2, 3, 0, 0, 9])


if __name__ == '__main__':
    unittest.main()
