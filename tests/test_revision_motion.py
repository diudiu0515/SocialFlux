"""Behavioral checks for public-only, reproducible revision motion."""
import copy
import math
import unittest

from offline.revision_motion import revision_controls


def request(node='sample-a', face='neutral', gaze='', behavior=()):
    return {'node_id': node, 'source_observable_expression': {
        'facial_expression': face, 'gaze': gaze, 'behavioral_cues': list(behavior)}}


def curve(value, duration=24, boundaries=(), fps=100):
    return [revision_controls(value, i / fps, duration, boundaries)
            for i in range(round(duration * fps) + 1)]


def active_runs(values, threshold):
    count = 0
    active = False
    for value in values:
        above = value > threshold
        count += above and not active
        active = above
    return count


class RevisionMotionTest(unittest.TestCase):
    def test_private_fields_spec_and_global_randomness_do_not_affect_motion(self):
        public = request(face='slightly tense', behavior=['slight nod'])
        enriched = copy.deepcopy(public)
        enriched.update(private_state={'anger': 10}, machine={'answer': 'B'},
                        initial_state={'trust': -100}, spec_sha256='changed',
                        source_public_response='The words do not add visual emotions.')
        before = copy.deepcopy(enriched)
        expected = curve(public, 7, (2, 4))
        self.assertEqual(expected, curve(enriched, 7, (2, 4)))
        self.assertEqual(enriched, before)
        # Frame requests may arrive out of order or on another worker.
        for i in (567, 6, 320, 0, 700, 89):
            self.assertEqual(expected[i], revision_controls(public, i / 100, 7, (2, 4)))

    def test_each_node_has_distinct_nonperiodic_blinks(self):
        a, b = curve(request('a'), 30), curve(request('b'), 30)
        blink_a = [row['blink'] for row in a]
        self.assertNotEqual(blink_a, [row['blink'] for row in b])
        peaks = [i / 100 for i in range(1, len(a) - 1)
                 if blink_a[i] > .9 and blink_a[i] >= blink_a[i - 1]
                 and blink_a[i] > blink_a[i + 1]]
        self.assertGreaterEqual(len(peaks), 4)
        gaps = [right - left for left, right in zip(peaks, peaks[1:])]
        self.assertGreater(max(gaps) - min(gaps), .25)
        self.assertFalse(all(abs(gap - 4.1) < .1 for gap in gaps))
        self.assertEqual(blink_a[0], 0)
        self.assertEqual(blink_a[-1], 0)

    def test_no_cue_or_negated_cue_never_adds_emotion_gaze_or_large_actions(self):
        neutral = request()
        negated = request(face='Calm, no noticeable relaxation', gaze='Does not look down at notes',
                          behavior=['No nod', 'Without a head tilt'])
        for source in (neutral, negated):
            rows = curve(source, 12)
            for row in rows:
                self.assertEqual((row['eyebrow'], row['gaze_x'], row['gaze_y']), (0, 0, 0))
                self.assertLessEqual(abs(row['pitch']), .22)
                self.assertLessEqual(abs(row['yaw']), .35)
                self.assertLessEqual(abs(row['roll']), .16)
            self.assertGreater(max(abs(row['yaw']) for row in rows), .01)

    def test_explicit_actions_are_single_events_during_speech_not_looped(self):
        source = request(gaze='brief downward glance toward the documents', behavior=['a slight nod'])
        rows = curve(source, 24, (5, 9, 14, 18))
        self.assertEqual(active_runs([-row['gaze_y'] for row in rows], .5), 1)
        self.assertEqual(active_runs([row['pitch'] for row in rows], .6), 1)
        nod_peak = max(range(len(rows)), key=lambda i: rows[i]['pitch']) / 100
        gaze_peak = max(range(len(rows)), key=lambda i: -rows[i]['gaze_y']) / 100
        self.assertGreater(nod_peak, 2)
        self.assertGreater(gaze_peak, 2)
        self.assertLess(nod_peak, 22)
        self.assertLess(gaze_peak, 22)
        for row in (rows[0], rows[-1]):
            self.assertAlmostEqual(row['pitch'], 0)
            self.assertAlmostEqual(row['gaze_y'], 0)
        tilted = curve(request(behavior=['slight head tilt']), 12)
        self.assertEqual(active_runs([row['roll'] for row in tilted], .5), 1)

    def test_only_explicit_brief_or_relaxing_states_release_tension(self):
        for face in ('briefly tense', 'relaxing'):
            source = request(face=face)
            for duration in (6, 24):
                rows = curve(source, duration)
                self.assertLess(min(row['eyebrow'] for row in rows), -3)
                self.assertAlmostEqual(rows[-1]['eyebrow'], 0)
                self.assertTrue(all(row['eyebrow'] <= 0 for row in rows))
        # Neither a short nor a long tense state licenses an invented recovery.
        for duration in (4.6, 24):
            sustained = curve(request(face='slightly tense'), duration)
            self.assertAlmostEqual(sustained[0]['eyebrow'], 0)
            for row in sustained[len(sustained) // 2:]:
                self.assertLess(row['eyebrow'], -3)
            relaxed = curve(request(face='relaxing'), duration)
            self.assertLess(relaxed[0]['eyebrow'], -3)
            self.assertTrue(all(a['eyebrow'] <= b['eyebrow']
                                for a, b in zip(relaxed, relaxed[1:])))
            self.assertLess(relaxed[len(relaxed) // 4]['eyebrow'], -2)
            self.assertGreater(relaxed[len(relaxed) * 3 // 4]['eyebrow'], -.2)

    def test_curves_are_continuous_bounded_and_keep_two_cue_limit(self):
        source = request(face='slightly tense', gaze='looks down at notes', behavior=['slight nod', 'head tilt'])
        rows = curve(source, 16)
        limits = {'eyebrow': (-4.0, 0), 'blink': (0, 1), 'gaze_x': (0, 2.2),
                  'gaze_y': (-2.2, 0), 'pitch': (-.22, 2.02), 'yaw': (-.35, .35), 'roll': (-.16, 1.31)}
        for row in rows:
            self.assertEqual(set(row), set(limits))
            for key, (low, high) in limits.items():
                self.assertTrue(math.isfinite(row[key]))
                self.assertGreaterEqual(row[key], low - 1e-12)
                self.assertLessEqual(row[key], high + 1e-12)
            # Facial state + nod consume the parser's two cue slots.
            self.assertEqual(row['gaze_x'], 0)
            self.assertEqual(row['gaze_y'], 0)
            self.assertLessEqual(abs(row['roll']), .16)
        for previous, current in zip(rows, rows[1:]):
            for key in limits:
                self.assertLess(abs(current[key] - previous[key]), .26, key)

    def test_phrase_hints_are_order_independent_and_outside_clip_are_ignored(self):
        source = request(gaze='briefly looks down at the notes')
        clean = curve(source, 8, (2, 4, 6))
        self.assertEqual(clean, curve(source, 8, (6, 4, 2, 2, -3, 0, 8, 99)))
        self.assertNotEqual(clean, curve(source, 8, ()))

    def test_sentence_checkpoints_have_at_most_one_blink_and_visible_restrained_cues(self):
        for duration in (4, 4.725, 5):
            for node in range(12):
                rows = curve(request(str(node)), duration, fps=25)
                self.assertLessEqual(active_runs([row['blink'] for row in rows], .15), 1)
                self.assertGreater(max(row['blink'] for row in rows), .7)
            rows = curve(request(gaze='brief downward glance', behavior=['a slight nod']), duration, fps=25)
            self.assertGreater(max(row['pitch'] for row in rows), 1.4)
            self.assertGreater(max(-row['gaze_y'] for row in rows), 1.8)
            self.assertEqual(active_runs([row['pitch'] for row in rows], .6), 1)
            self.assertEqual(active_runs([-row['gaze_y'] for row in rows], .5), 1)
            face = curve(request(face='briefly tense'), duration, fps=25)
            self.assertLess(min(row['eyebrow'] for row in face), -3.8)
            self.assertGreater(sum(row['eyebrow'] < -2 for row in face), 14)
            self.assertAlmostEqual(face[-1]['eyebrow'], 0)

    def test_visual_calibration_requires_exact_node_and_public_brief_tension(self):
        calibrated = 'GPT50_001-t1-e30dc6556d3865ac'
        rows = curve(request(calibrated, face='briefly tense'), 4.6)
        self.assertAlmostEqual(min(row['eyebrow'] for row in rows), -8, delta=.01)
        self.assertTrue(all(-8 <= row['eyebrow'] <= 0 for row in rows))
        self.assertEqual(rows[-1]['eyebrow'], 0)
        for face in ('neutral', 'No brief tension', 'Not briefly tense'):
            rows = curve(request(calibrated, face=face), 4.6)
            self.assertTrue(all(row['eyebrow'] == 0 for row in rows), face)
        # Same identity with a different cue retains that cue's default profile.
        sustained = curve(request(calibrated, face='slightly tense'), 4.6)
        self.assertAlmostEqual(sustained[-1]['eyebrow'], -3.2)
        # A different checkpoint, even in scene 001, gets no inherited override.
        for node in ('another-node', 'GPT50_001-t2-5d18d259564c3313'):
            rows = curve(request(node, face='briefly tense'), 4.6)
            self.assertAlmostEqual(min(row['eyebrow'] for row in rows), -4, delta=.01)

    def test_short_clips_and_out_of_range_time_remain_safe(self):
        source = request(face='brief tension', behavior=['slight nod'])
        for duration in (.05, .3, 1, 4.725):
            start = revision_controls(source, 0, duration)
            end = revision_controls(source, duration, duration)
            self.assertEqual(start, revision_controls(source, -1, duration))
            self.assertEqual(end, revision_controls(source, duration + 1, duration))
            self.assertTrue(all(math.isfinite(v) for v in end.values()))
        for duration in (0, -1, math.inf, math.nan):
            with self.assertRaises(ValueError):
                revision_controls(source, 0, duration)
        with self.assertRaises(ValueError):
            revision_controls(source, math.nan, 5)
        with self.assertRaises(ValueError):
            revision_controls(source, 0, 5, (math.nan,))


if __name__ == '__main__':
    unittest.main()
