"""Public motion cues respect negation and the two-cue visual limit."""
import json
import math
from pathlib import Path
import unittest

from scripts.animate_annotation400_local import controls, public_motion_cues, affirmed


class PublicMotionTest(unittest.TestCase):
    def request(self, face='neutral', gaze='', behavior=()):
        return {'source_observable_expression': {'facial_expression': face,
                'gaze': gaze, 'behavioral_cues': list(behavior)}}

    def test_no_noticeable_relaxation_does_not_create_relief(self):
        request = self.request('Calm expression, with no noticeable relaxation or displeasure')
        self.assertNotIn('facial_expression', public_motion_cues(request)['selected_cues'])
        for t in (0, .7, 1.2, 4):
            self.assertEqual(controls(request, t)['eyebrow'], 0)

    def test_local_negation_does_not_hide_a_later_positive_clause(self):
        self.assertFalse(affirmed(r'\bnod\b', 'Does not nod.'))
        self.assertFalse(affirmed(r'\bhead tilt\b', 'Without a head tilt.'))
        self.assertTrue(affirmed(r'\bnod\b', 'Not tense, but gives a brief nod.'))
        request = self.request('Not tense, but slightly relieved')
        self.assertEqual(public_motion_cues(request)['eyebrow'], 'relaxing')

    def test_neutral_face_allows_nod_and_downward_glance(self):
        request = self.request(gaze='steady, brief downward glance toward workstation',
                               behavior=['slight nod on first clause'])
        self.assertEqual(public_motion_cues(request)['selected_cues'], ['nod', 'gaze'])
        self.assertGreater(controls(request, 1.2)['pitch'], 1)
        self.assertLess(controls(request, 4)['gaze_y'], -2)

    def test_nod_in_face_description_and_head_tilt_are_supported(self):
        request = self.request('steady, with a brief relieved nod')
        self.assertEqual(public_motion_cues(request)['selected_cues'], ['facial_expression', 'nod'])
        tilted = self.request('attentive, concerned', behavior=['slight head tilt', 'hands gesture toward papers'])
        self.assertEqual(public_motion_cues(tilted)['selected_cues'], ['facial_expression', 'head_tilt'])
        self.assertGreater(controls(tilted, 1.4)['roll'], 1)

    def test_material_gaze_in_behavior_is_used_but_hand_actions_are_not(self):
        request = self.request(behavior=['Slight nod', 'Brief glance toward the workbench'])
        self.assertEqual(public_motion_cues(request)['selected_cues'], ['nod', 'gaze'])
        request = self.request(behavior=['Looks toward the agenda materials'])
        self.assertEqual(public_motion_cues(request)['selected_cues'], ['gaze'])
        request = self.request(behavior=['Pen poised above the notes', 'Hands gesture toward papers'])
        self.assertEqual(public_motion_cues(request)['selected_cues'], [])
        request = self.request(gaze='Briefly looks at the record, then back at the other person',
                               behavior=['Briefly pauses writing and shifts attention back to the record'])
        self.assertTrue(public_motion_cues(request)['look_down'])
        self.assertFalse(public_motion_cues(request)['look_away'])

    def test_negative_nod_tilt_and_gaze_do_not_create_those_actions(self):
        request = self.request(gaze='Does not look down at the notes',
                               behavior=['No nod', 'Without a head tilt'])
        self.assertEqual(public_motion_cues(request)['selected_cues'], [])
        for t in (.7, 1.2, 4):
            c = controls(request, t)
            self.assertEqual(c['gaze_y'], 0)
            self.assertEqual(c['pitch'], .15 * math.sin(t * 1.1))
            self.assertEqual(c['roll'], .1 * math.sin(t * .5))

    def test_three_explicit_actions_select_only_two_supported_classes(self):
        request = self.request('slightly tense', 'brief downward glance',
                               ['brief nod', 'slight head tilt', 'leans forward'])
        cues = public_motion_cues(request)
        self.assertEqual(cues['selected_cues'], ['facial_expression', 'nod'])
        self.assertFalse(cues['head_tilt'])
        self.assertFalse(cues['look_down'])

    def test_all_150_public_requests_respect_the_two_cue_limit(self):
        root = Path(__file__).resolve().parents[1] / 'data/offline_annotation400_en_20261022/local_av'
        paths = sorted(root.glob('GPT50_*/*/request.json'))
        self.assertEqual(len(paths), 150)
        for path in paths:
            request = json.loads(path.read_text())
            with self.subTest(node_id=request['node_id']):
                cues = public_motion_cues(request)
                self.assertLessEqual(len(cues['selected_cues']), 2)
                self.assertLessEqual(sum([bool(cues['eyebrow']), cues['nod'], cues['head_tilt'],
                                          cues['look_down'] or cues['look_away']]), 2)
                # Only the public projection affects motion, irrespective of
                # any unrelated fields that might appear in a future request.
                public_only = {'source_observable_expression': request['source_observable_expression']}
                self.assertEqual(controls(request, 1.2), controls(public_only, 1.2))


if __name__ == '__main__':
    unittest.main()
