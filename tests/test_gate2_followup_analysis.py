import unittest
from evaluation.gate2_followup_analysis import matched_controls


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


if __name__ == '__main__': unittest.main()
