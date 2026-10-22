import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import export_shadow_pilot_review as review


class ShadowReviewTest(unittest.TestCase):
    def test_complete_and_unchanged_evidence_is_retained(self):
        with tempfile.TemporaryDirectory(dir=review.ROOT / 'data') as name:
            directory = Path(name)
            turn = {'turn_id': 't1', 'policy_action': {'text': '新的安排'},
                    'environment_response': '回应',
                    'state_before': {'relationship': {'trust': 4, 'respect': 5}},
                    'state_after': {'relationship': {'trust': 5, 'respect': 5}},
                    'numeric_state_delta': {'relationship': {'trust': 1, 'respect': 0}},
                    'state_judgments': [
                        {'variable': 'relationship.trust', 'judgment': 'ordinary_new_evidence',
                         'evidence_span': '新的安排', 'rationale': 'test new'},
                        {'variable': 'relationship.respect', 'judgment': 'repeated_evidence_only',
                         'evidence_span': '', 'rationale': 'test repeat'}]}
            trajectory = {'turns': [turn], 'ending': None}
            (directory / 'checkpoint.json').write_text(json.dumps(trajectory))
            with patch.object(review, 'plot') as draw:
                result = review.export_one(directory, {'initial_observation': {'background': 'shared'}})
            self.assertEqual(result['status'], 'running')
            self.assertEqual(result['findings'], [])
            text = (directory / 'evidence_review.txt').read_text()
            self.assertIn('重复证据', text)
            self.assertIn('5 → 5 (+0)', text)
            self.assertIn('test new', text)
            draw.assert_called_once()
            turn['state_judgments'][0]['judgment'] = 'repeated_evidence_only'
            (directory / 'partial_trajectory.json').write_text(json.dumps(trajectory))
            (directory / 'result.json').write_text(json.dumps({'status': 'call_or_validation_failure'}))
            with patch.object(review, 'plot'):
                result = review.export_one(directory, {'initial_observation': {'background': 'shared'}})
            self.assertEqual(result['status'], 'call_or_validation_failure')
            self.assertEqual(result['findings'], ['t1:relationship.trust:no_new_evidence_but_changed'])

    def test_missing_trajectory_not_counted_complete(self):
        with tempfile.TemporaryDirectory() as name:
            self.assertEqual(review.export_one(Path(name), {})['status'], 'not_yet_available')


if __name__ == '__main__':
    unittest.main()
