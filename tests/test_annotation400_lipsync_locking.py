"""SyncNet sees stable renders and never keeps a lock after skipping or failing."""
from contextlib import redirect_stdout
import fcntl
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from scripts.audit_annotation400_lipsync import audit_node, current_snapshot
from scripts.build_annotation400 import load, save, sha


class LipsyncLockingTest(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self.root / 'node'
        self.directory.mkdir()
        self.tool = self.root / 'tool'
        (self.tool / 'checkpoints').mkdir(parents=True)
        self.row = {'node_id': 'node', 'request_path': 'node/request.json', 'spec_sha256': 'current-spec'}
        for name in ('speech.wav', 'motion.mp4', 'video.mp4'):
            (self.directory / name).write_bytes(name.encode())
        save(self.directory / 'request.json', {'spec_sha256': 'current-spec'})
        save(self.directory / 'speech.json', {'spec_sha256': 'current-spec', 'sha256': sha(self.directory / 'speech.wav')})
        save(self.directory / 'motion.json', {'spec_sha256': 'current-spec', 'sha256': sha(self.directory / 'motion.mp4'),
             'audio_sha256': sha(self.directory / 'speech.wav')})
        save(self.directory / 'video.json', {'spec_sha256': 'current-spec', 'sha256': sha(self.directory / 'video.mp4'),
             'audio_sha256': sha(self.directory / 'speech.wav'), 'motion_sha256': sha(self.directory / 'motion.mp4'),
             'structural_metadata': {'duration_seconds_actual': 5.0}})

    def audit(self, evaluate=None, **kwargs):
        with redirect_stdout(io.StringIO()):
            return audit_node(self.row, evaluate=evaluate or (lambda video, temporary: (0, 4)),
                              model_hash='syncnet-model', root=self.root, tool=self.tool, **kwargs)

    def assert_exclusive_available(self):
        with (self.directory / 'render.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(lock, fcntl.LOCK_UN)

    def change_receipt(self, name, **fields):
        path = self.directory / name
        receipt = load(path)
        receipt.update(fields)
        save(path, receipt)

    def test_active_renderer_is_skipped_without_evaluation(self):
        evaluate = Mock()
        with (self.directory / 'render.lock').open('a') as renderer:
            fcntl.flock(renderer, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertIsNone(self.audit(evaluate))
            evaluate.assert_not_called()
        self.assert_exclusive_available()
        self.assertIsNotNone(self.audit())

    def test_shared_lock_is_held_during_evaluation_and_released_afterward(self):
        def evaluate(video, temporary):
            with (self.directory / 'render.lock').open('a') as renderer:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(renderer, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return 0, 4
        self.assertTrue(self.audit(evaluate)['machine_screen_passed'])
        self.assert_exclusive_available()

    def test_evaluation_exception_releases_lock_and_restores_cwd(self):
        previous = Path.cwd()
        with self.assertRaisesRegex(RuntimeError, 'detector failed'):
            self.audit(Mock(side_effect=RuntimeError('detector failed')))
        self.assertEqual(Path.cwd(), previous)
        self.assert_exclusive_available()
        self.assertFalse((self.directory / 'lipsync_screen.json').exists())

    def test_current_spec_audio_and_motion_must_match_before_evaluation(self):
        for key in ('spec_sha256', 'audio_sha256', 'motion_sha256', 'sha256'):
            with self.subTest(key=key):
                path = self.directory / 'video.json'
                original = load(path)
                self.change_receipt('video.json', **{key: 'stale'})
                evaluate = Mock()
                self.assertIsNone(self.audit(evaluate))
                evaluate.assert_not_called()
                self.assert_exclusive_available()
                save(path, original)

    def test_updated_video_during_evaluation_cannot_receive_stale_score(self):
        def evaluate(video, temporary):
            # Simulate a writer that does not honor render.lock, even giving
            # its replacement a valid new receipt. The initial snapshot differs.
            (self.directory / 'video.mp4').write_bytes(b'replacement video')
            self.change_receipt('video.json', sha256=sha(self.directory / 'video.mp4'))
            return 0, 5
        self.assertIsNone(self.audit(evaluate))
        self.assertFalse((self.directory / 'lipsync_screen.json').exists())
        self.assert_exclusive_available()

    def test_audio_changed_after_evaluation_is_rejected_before_write(self):
        def evaluate(video, temporary):
            (self.directory / 'speech.wav').write_bytes(b'replacement waveform')
            return 0, 5
        self.assertIsNone(self.audit(evaluate))
        self.assertFalse((self.directory / 'lipsync_screen.json').exists())
        self.assert_exclusive_available()

    def test_cache_hits_release_lock_and_do_not_accept_stale_sources(self):
        first = self.audit()
        evaluate = Mock()
        self.assertEqual(self.audit(evaluate), first)
        evaluate.assert_not_called()
        self.assert_exclusive_available()
        (self.directory / 'motion.mp4').write_bytes(b'new motion')
        self.assertIsNone(self.audit(evaluate))
        evaluate.assert_not_called()
        self.assert_exclusive_available()

    def test_partial_receipts_are_retried_and_release_lock(self):
        (self.directory / 'video.json').write_text('{')
        self.assertIsNone(self.audit())
        self.assert_exclusive_available()

    def test_eight_second_center_window_and_original_thresholds_are_preserved(self):
        self.change_receipt('video.json', structural_metadata={'duration_seconds_actual': 20.0})
        def create_sample(command, **kwargs):
            self.assertEqual(command[command.index('-ss') + 1], '6.0')
            self.assertEqual(command[command.index('-t') + 1], '8.0')
            Path(command[-1]).write_bytes(b'centered sample')
        with patch('scripts.audit_annotation400_lipsync.subprocess.run', side_effect=create_sample):
            for offset, confidence, passed in [(2, 3.0, True), (0, 2.99, False), (3, 5.0, False)]:
                with self.subTest(offset=offset, confidence=confidence):
                    (self.directory / 'lipsync_screen.json').unlink(missing_ok=True)
                    result = self.audit(lambda video, temporary: (offset, confidence))
                    self.assertEqual(result['machine_screen_passed'], passed)
                    self.assertEqual(result['measurement_window']['start_seconds'], 6)
                    self.assertEqual(result['measurement_window']['duration_seconds'], 8)
                    self.assertFalse(result['measurement_window']['complete_clip'])
                    self.assert_exclusive_available()


if __name__ == '__main__':
    unittest.main()
