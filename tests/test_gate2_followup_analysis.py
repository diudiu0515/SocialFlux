import unittest
import json
import tempfile
from pathlib import Path
from evaluation.gate2_followup_analysis import matched_controls, audit_repeat_inputs


class MatchedControlTests(unittest.TestCase):
    def test_common_denominator_includes_variable_active_in_either_variant(self):
        original = {'x': 1, 'y': 0, 'z': 0}
        row = dict(scenario_id='scene', comparisons={
            'repeat': {'overall': {'left_numeric_delta': original, 'right_numeric_delta': {'x': 1, 'y': 1, 'z': 0}}},
            'paraphrase': {'overall': {'left_numeric_delta': original, 'right_numeric_delta': {'x': -1, 'y': 0, 'z': 0}}}})
        r = matched_controls([row, dict(scenario_id='missing', comparisons={})])
        self.assertEqual(r['matched_scenarios'], 1)
        self.assertEqual(r['active_dimensions'], 2)
        self.assertEqual(r['repeat_direction_agreement'], .5)
        self.assertEqual(r['paraphrase_direction_agreement'], .5)
        self.assertEqual(r['paraphrase_reversal_rate'], .5)

    def test_no_valid_triplet_is_unknown(self):
        r = matched_controls([])
        self.assertIsNone(r['repeat_direction_agreement'])
        self.assertIsNone(r['paraphrase_minus_repeat'])

    def test_input_audit_catches_changed_sampling(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            for condition in ('original', 'repeat'):
                for stage in ('state', 'interaction'):
                    p = root/'calls'/'scene'/condition/stage/'one.json'; p.parent.mkdir(parents=True)
                    p.write_text(json.dumps(dict(started_at_unix=1, messages=[{'content':'same'}], generation={'seed':1})))
            records = [dict(scenario_id='scene', comparisons={'repeat':{}})]
            self.assertTrue(audit_repeat_inputs(root, records)['all_checked_inputs_identical'])
            p = root/'calls'/'scene'/'repeat'/'state'/'one.json'; row = json.loads(p.read_text()); row['generation']['seed'] = 2; p.write_text(json.dumps(row))
            self.assertFalse(audit_repeat_inputs(root, records)['all_checked_inputs_identical'])


if __name__ == '__main__': unittest.main()
