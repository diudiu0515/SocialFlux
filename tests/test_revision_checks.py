"""CPU regressions for stable inputs, real face coverage and per-track scores."""
from contextlib import ExitStack, redirect_stdout
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from offline.revision_checks import (ASR_SCREEN_VERSION, SYNC_SCREEN_VERSION,
    audio_evidence_valid, sync_evidence_valid, sync_coverage, sync_window_evidence)
from scripts import render_annotation400_revision as revision


def track(frames=None, offset=0, confidence=4.0, missing=()):
    frames = list(range(115)) if frames is None else frames
    return {'track_id': '00000', 'frame_indices': frames,
            'detected_frame_indices': [f for f in frames if f not in missing],
            'interpolated_frame_indices': list(missing), 'crop_frame_count': len(frames),
            'crop_sha256': 'b' * 64, 'input_sha256_before': 'b' * 64,
            'input_sha256_after': 'b' * 64, 'input_stable': True,
            'offset_frames': offset, 'confidence': confidence,
            'model_window': sync_window_evidence(frames, len(frames), len(frames))}


def receipt(tracks=None):
    tracks = [track()] if tracks is None else tracks
    detected = sorted({f for t in tracks for f in t['detected_frame_indices']})
    coverage = sync_coverage(115, 115, detected, tracks)
    return {'version': SYNC_SCREEN_VERSION, 'video_sha256': 'a' * 64,
            'input_sha256_before': 'a' * 64, 'input_sha256_after': 'a' * 64,
            'request_sha256_before': 'c' * 64, 'request_sha256_after': 'c' * 64,
            'input_stable': True, 'tracks': tracks, 'coverage': coverage,
            'complete_clip': coverage['fully_detected'] and coverage['fully_tracked'],
            'machine_screen_passed': True, 'confidence': min(t['confidence'] for t in tracks),
            'offset_frames': max(tracks, key=lambda t: abs(t['offset_frames']))['offset_frames']}


class RevisionEvidenceTest(unittest.TestCase):
    def test_full_crop_discloses_model_edge_without_inventing_frame_scores(self):
        evidence = receipt()
        self.assertTrue(sync_evidence_valid(evidence))
        window = evidence['tracks'][0]['model_window']
        self.assertEqual(window['window_count'], 110)
        self.assertEqual(window['feature_input_frame_indices'], list(range(114)))
        self.assertEqual(window['unscored_frame_indices'], [114])
        self.assertEqual(evidence['coverage']['missing_track_frame_indices'], [])

    def test_opposite_bad_offsets_cannot_cancel(self):
        left, right = track(list(range(58)), offset=4), track(list(range(58, 115)), offset=-4)
        right['track_id'] = '00001'
        evidence = receipt([left, right])
        self.assertTrue(evidence['complete_clip'])
        self.assertFalse(sync_evidence_valid(evidence))
        evidence.update(offset_frames=0, confidence=4.0)
        self.assertFalse(sync_evidence_valid(evidence))

    def test_track_and_detection_holes_are_not_model_edge_allowances(self):
        for missing_track in ([114], list(range(51, 115))):
            frames = [f for f in range(115) if f not in missing_track]
            evidence = receipt([track(frames)])
            self.assertEqual(evidence['coverage']['missing_track_frame_indices'], missing_track)
            evidence['complete_clip'] = True
            self.assertFalse(sync_evidence_valid(evidence))
        evidence = receipt([track(missing=(57,))])
        self.assertTrue(evidence['coverage']['fully_tracked'])
        self.assertFalse(evidence['coverage']['fully_detected'])
        self.assertEqual(evidence['coverage']['interpolated_frame_indices'], [57])
        evidence['complete_clip'] = True
        self.assertFalse(sync_evidence_valid(evidence))

    def test_forged_coverage_changed_inputs_and_nonfinite_scores_fail_closed(self):
        for change in ({'version': 'old'}, {'input_sha256_after': 'f' * 64},
                       {'request_sha256_after': 'f' * 64}, {'input_stable': False}):
            evidence = receipt()
            evidence.update(change)
            self.assertFalse(sync_evidence_valid(evidence))
        for confidence in (float('nan'), float('inf'), True, 2.9):
            self.assertFalse(sync_evidence_valid(receipt([track(confidence=confidence)])))
        evidence = receipt()
        evidence['coverage']['detected_frame_indices'] = list(range(114))
        self.assertFalse(sync_evidence_valid(evidence))
        evidence = receipt()
        evidence['tracks'][0]['model_window']['audio_frame_count'] = 114
        self.assertFalse(sync_evidence_valid(evidence))
        for malformed in (None, [], {}, {'version': SYNC_SCREEN_VERSION}):
            self.assertFalse(sync_evidence_valid(malformed))

    def test_audio_requires_stable_versioned_input_and_original_quality_checks(self):
        evidence = {'version': ASR_SCREEN_VERSION, 'sha256': 'a' * 64,
                    'input_sha256_before': 'a' * 64, 'input_sha256_after': 'a' * 64,
                    'request_sha256_before': 'c' * 64, 'request_sha256_after': 'c' * 64,
                    'input_stable': True, 'machine_screen_passed': True, 'language': 'en',
                    'unprompted': True, 'critical_content_match': True, 'normalized_similarity': 1.0}
        self.assertTrue(audio_evidence_valid(evidence))
        for field, value in (('version', 'old'), ('input_sha256_after', 'f' * 64),
                             ('request_sha256_after', 'f' * 64), ('input_stable', False),
                             ('critical_content_match', False), ('normalized_similarity', .97),
                             ('normalized_similarity', float('nan'))):
            self.assertFalse(audio_evidence_valid({**evidence, field: value}))


class FakeDetector:
    def __init__(self, tracks, missing=()):
        self.tracks, self.missing = tracks, set(missing)

    def detect_face(self, _):
        return [[] if i in self.missing else [{'frame': i, 'bbox': [0., 0., 200., 200.]}]
                for i in range(115)]

    def crop_video(self, row, cropfile, *args):
        Path(cropfile + '.mp4').write_bytes(b'crop ' + cropfile.encode())

    def __call__(self, **kwargs):
        self.detect_face('frames')
        Path('detect_results/crop').mkdir(parents=True, exist_ok=True)
        for index, frames in enumerate(self.tracks):
            self.crop_video({'frame': frames, 'bbox': [[0., 0., 200., 200.]] * len(frames)},
                            f'detect_results/crop/{index:05d}')


class RevisionCheckRunnerTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(revision, 'REVISION', self.root))
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.directory = self.root / 'node'
        self.directory.mkdir()
        self.path = self.directory / 'request.json'
        self.request = {'node_id': 'fixture', 'source_public_response': 'I will check the record.'}
        self.request['spec_sha256'] = revision.digest(self.request)
        revision.save(self.path, self.request)
        self.audio = self.directory / 'speech.wav'
        self.audio.write_bytes(b'checked audio')
        self.video = self.directory / 'video.mp4'
        self.video.write_bytes(b'checked video')

    def asr(self, change=None):
        worker = revision.ASR.__new__(revision.ASR)
        def transcribe(*args, **kwargs):
            # A lazy segment iterator models replacement after decoding starts.
            def segments():
                if change:
                    change()
                yield SimpleNamespace(text=self.request['source_public_response'])
            return segments(), SimpleNamespace(language='en')
        worker.model = SimpleNamespace(transcribe=transcribe)
        return worker

    def sync(self, frames=None, missing=(), scores=None, change=None):
        frames = [list(range(115))] if frames is None else frames
        worker = revision.Sync.__new__(revision.Sync)
        worker.tool = self.root / 'tool'
        (worker.tool / 'checkpoints').mkdir(parents=True, exist_ok=True)
        worker.weights = worker.tool / 'checkpoints/model'
        worker.weights.write_bytes(b'cpu model fixture')
        worker.detector = FakeDetector(frames, missing)
        scores = iter(scores or [(0, 0., 4.)] * len(frames))
        def evaluate(**kwargs):
            if change:
                change()
            return next(scores)
        worker.model = SimpleNamespace(evaluate=evaluate)
        worker.media_shape = lambda p: (len(frames[int(p.stem)]) if p.stem.isdigit() else 115, 25.)
        worker.audio_frame_count = lambda p: len(frames[int(p.stem)])
        return worker

    def test_asr_rejects_audio_and_request_changes_during_lazy_transcription(self):
        for target in (self.audio, self.path):
            before = target.read_bytes()
            worker = self.asr(lambda: target.write_bytes(b'replacement'))
            with self.assertRaisesRegex(ValueError, 'input changed'):
                worker.render(self.path)
            result = revision.load(self.directory / 'audio_screen.json')
            self.assertFalse(result['input_stable'])
            self.assertFalse(result['machine_screen_passed'])
            self.assertFalse(audio_evidence_valid(result))
            target.write_bytes(before)
        self.asr().render(self.path)
        self.assertTrue(audio_evidence_valid(revision.load(self.directory / 'audio_screen.json')))

    def test_sync_captures_real_detection_hole_separately_from_interpolated_track(self):
        worker = self.sync(missing=(57,))
        original_detect = worker.detector.detect_face
        worker.render(self.path)
        result = revision.load(self.directory / 'lipsync_screen.json')
        self.assertTrue(result['coverage']['fully_tracked'])
        self.assertFalse(result['complete_clip'])
        self.assertEqual(result['coverage']['missing_detection_frame_indices'], [57])
        self.assertFalse(result['machine_screen_passed'])
        self.assertEqual(worker.detector.detect_face, original_detect)

    def test_sync_checks_every_track_without_averaging_offsets(self):
        worker = self.sync([list(range(58)), list(range(58, 115))], scores=[(4, 0., 4.), (-4, 0., 4.)])
        worker.render(self.path)
        result = revision.load(self.directory / 'lipsync_screen.json')
        self.assertTrue(result['complete_clip'])
        self.assertEqual(result['offset_frames'], 4)
        self.assertEqual([t['offset_frames'] for t in result['tracks']], [4, -4])
        self.assertFalse(result['machine_screen_passed'])

    def test_sync_rejects_video_replacement_after_model_read(self):
        old_sha = revision.sha(self.video)
        worker = self.sync(change=lambda: self.video.write_bytes(b'unchecked replacement'))
        with self.assertRaisesRegex(ValueError, 'input changed'):
            worker.render(self.path)
        result = revision.load(self.directory / 'lipsync_screen.json')
        self.assertEqual(result['video_sha256'], old_sha)
        self.assertNotEqual(result['video_sha256'], revision.sha(self.video))
        self.assertFalse(result['machine_screen_passed'])

    def test_sync_full_stable_track_produces_accepted_versioned_evidence(self):
        self.sync().render(self.path)
        result = revision.load(self.directory / 'lipsync_screen.json')
        self.assertTrue(sync_evidence_valid(result))
        self.assertEqual(result['coverage']['source_frame_count'], 115)
        self.assertEqual(result['tracks'][0]['model_window']['unscored_frame_indices'], [114])

    def test_sync_no_tracks_records_failed_coverage_without_claiming_complete(self):
        self.sync(frames=[]).render(self.path)
        result = revision.load(self.directory / 'lipsync_screen.json')
        self.assertEqual(result['tracks'], [])
        self.assertEqual(result['coverage']['missing_track_frame_indices'], list(range(115)))
        self.assertFalse(result['complete_clip'])
        self.assertFalse(result['machine_screen_passed'])

    def test_sync_rejects_request_and_scored_crop_replacement(self):
        original_request = self.path.read_bytes()
        changes = [lambda: self.path.write_bytes(b'changed request'),
                   lambda: Path('detect_results/crop/00000.mp4').write_bytes(b'changed crop')]
        for change in changes:
            worker = self.sync(change=change)
            with self.assertRaisesRegex(ValueError, 'input changed'):
                worker.render(self.path)
            result = revision.load(self.directory / 'lipsync_screen.json')
            self.assertFalse(result['input_stable'])
            self.assertFalse(result['machine_screen_passed'])
            self.path.write_bytes(original_request)


if __name__ == '__main__':
    unittest.main()
