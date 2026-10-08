import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluation.rollout_gate import QUALITY_DIMENSIONS
from scripts import prepare_gate3_audit_inputs as prepare
from scripts import review_active_rollouts as review


class RetainedGate3Test(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.batch = self.root / 'gate3_followup'
        self.scenarios = self.root / 'scenarios'
        records = []
        for index, status in enumerate(('completed', 'call_or_validation_failure', 'no_turns'), 1):
            scenario_id = f'S{index}'
            self.write(self.scenarios / f'scenario_{index:03d}' / f'scenario_{index:03d}.json',
                       {'scenario_id': scenario_id, 'background': 'A meeting.'})
            trajectory = {'scenario_id': scenario_id, 'trajectory_id': f'T{index}',
                          'turns': [{'turn_id': 't1', 'policy_action': {'text': 'Hello.'},
                                     'environment_response': 'Hello.'}]}
            source = self.root / f'trajectory_{index}.json'
            self.write(source, trajectory)
            records.append({'scenario_id': scenario_id, 'included': index != 3,
                            'generation_status': status, 'source_path': str(source),
                            'trajectory_id': f'T{index}', 'turns': 1})
        self.coverage = self.root / 'coverage.json'
        self.write(self.coverage, {'scheduled_scenarios': 3, 'included_count': 2,
                                   'records': records, 'missing_scenarios': ['S3']})
        self.enterContext(patch.object(prepare, 'ROOT', self.root))
        self.enterContext(patch.object(review, 'ROOT', self.root))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def prepare_inputs(self):
        prepare.main(['--batch-root', str(self.batch), '--scenario-root', str(self.scenarios),
                      '--rollout-root', str(self.root), '--expected-count', '2',
                      '--input-coverage', str(self.coverage)])

    def test_partial_and_missing_inputs_stay_visible_and_humans_remain_pending(self):
        self.prepare_inputs()
        rows = review.source_rows(self.batch, 2)
        self.assertEqual([r['source_status'] for r in rows],
                         ['completed_unreviewed', 'generation_error'])
        self.assertEqual(prepare.load(self.batch / 'input_coverage.json')['missing_scenarios'], ['S3'])
        humans = prepare.load(self.batch / 'human_review/gate3_rollouts.json')['records']
        self.assertTrue(all(r['decision'] == 'pending' and not r['human_attestation'] for r in humans))
        self.assertTrue(all(r['human_execution'] == 'pending' for r in humans))
        with self.assertRaises(FileExistsError):
            self.prepare_inputs()

    def test_changed_source_is_rejected_before_judge_calls(self):
        self.prepare_inputs()
        self.write(self.root / 'trajectory_1.json', {'changed': True})
        with self.assertRaisesRegex(ValueError, 'input changed'):
            review.source_rows(self.batch, 2)

    def test_coverage_cannot_silently_rebind_a_trajectory(self):
        data = prepare.load(self.coverage)
        data['records'][0]['trajectory_id'] = 'another'
        self.write(self.coverage, data)
        with self.assertRaisesRegex(ValueError, 'Retained input changed'):
            self.prepare_inputs()

    def test_english_review_resume_preserves_humans_and_does_not_resample(self):
        self.prepare_inputs()
        calls = []

        class Provider:
            audit_records = []

            def complete(self, messages, **kwargs):
                calls.append(messages)
                return json.dumps({'scores': {k: 4 for k in QUALITY_DIMENSIONS},
                                   'evidence': {k: ['t1'] for k in QUALITY_DIMENSIONS},
                                   'hard_reject_reasons': [], 'rationale': 'Consistent exchange.'})

        route_path = self.root / 'routes.json'
        self.write(route_path, {'format': 'socialflux_model_routes_v1', 'routes': {
            'quality_review': {'provider': 'openai_compatible', 'model': 'test',
                               'endpoint': 'https://example.invalid/chat/completions'}}})
        args = ['--batch-root', str(self.batch), '--model-routes', str(route_path),
                '--count', '2', '--workers', '1', '--max-attempts', '1',
                '--request-budget', '2', '--language', 'en', '--resume', '--require-complete']
        with patch.object(review, 'build_provider', return_value=Provider()):
            review.main(args)
            review.main(args)
        self.assertEqual(len(calls), 2)
        self.assertIn('Output language: English', calls[0][0]['content'])
        result = prepare.load(self.batch / 'gate3/model_reviews.json')
        self.assertTrue(result['complete'])
        self.assertEqual(result['human_review_status'], 'pending')
        self.assertEqual(result['decision_counts'], {'approve': 2, 'reject': 0})
        humans = prepare.load(self.batch / 'human_review/gate3_rollouts.json')['records']
        self.assertTrue(all(not r['human_attestation'] and r['decision'] == 'pending' for r in humans))


if __name__ == '__main__':
    unittest.main()
