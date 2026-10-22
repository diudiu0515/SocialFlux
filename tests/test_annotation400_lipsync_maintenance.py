"""Bounded repairs preserve prior decisions and never escalate beyond 1.5."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.audit_annotation400_lipsync import VERSION
from scripts.build_annotation400 import load, save, sha
from scripts.watch_annotation400_lipsync_repairs import append_repair, scan


class LipsyncMaintenanceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self.root / 'local'
        self.node = self.directory / 'node'
        self.node.mkdir(parents=True)
        self.row = {'node_id': 'node', 'spec_sha256': 'spec', 'request_path': 'local/node/request.json'}
        for name in ('speech.wav', 'motion.mp4', 'video.mp4'):
            (self.node / name).write_bytes(name.encode())
        save(self.node / 'request.json', {'spec_sha256': 'spec'})
        save(self.node / 'speech.json', {'spec_sha256': 'spec', 'sha256': sha(self.node / 'speech.wav')})
        save(self.node / 'motion.json', {'spec_sha256': 'spec', 'sha256': sha(self.node / 'motion.mp4'),
            'audio_sha256': sha(self.node / 'speech.wav')})
        save(self.node / 'video.json', {'spec_sha256': 'spec', 'sha256': sha(self.node / 'video.mp4'),
            'audio_sha256': sha(self.node / 'speech.wav'), 'motion_sha256': sha(self.node / 'motion.mp4'),
            'guidance_scale': 1.0, 'structural_metadata': {'duration_seconds_actual': 5.0}})
        self.screen(2.5, 0)
        self.repairs = self.directory / 'lipsync_repairs.json'
        save(self.repairs, {'format': 'local_lipsync_parameter_repairs_v1', 'nodes': {}})
        self.state, self.events = {}, []

    def screen(self, confidence, offset, **fields):
        save(self.node / 'lipsync_screen.json', {'node_id': 'node', 'spec_sha256': 'spec',
            'video_sha256': sha(self.node / 'video.mp4'), 'version': VERSION,
            'confidence': confidence, 'offset_frames': offset, **fields})

    def guidance(self, value):
        video = load(self.node / 'video.json')
        video['guidance_scale'] = value
        save(self.node / 'video.json', video)

    def scan(self):
        return scan([self.row], self.state, self.events.append, directory=self.directory,
                    root=self.root, pilot_sha='pilot-evidence')

    def test_atomic_append_preserves_all_existing_entries_and_metadata(self):
        original = {'format': 'local_lipsync_parameter_repairs_v1', 'audit_note': 'preserve',
                    'nodes': {'existing': {'guidance_scale': 2.0, 'reason': 'human decision'}}}
        save(self.repairs, original)
        self.assertFalse(append_repair(self.repairs, 'existing', {'guidance_scale': 1.5}))
        self.assertEqual(load(self.repairs), original)
        self.assertTrue(append_repair(self.repairs, 'new', {'guidance_scale': 1.5}))
        saved = load(self.repairs)
        self.assertEqual(saved['nodes']['existing'], original['nodes']['existing'])
        self.assertEqual(saved['audit_note'], 'preserve')
        self.assertFalse(list(self.directory.glob('*.tmp')))

    def test_current_failed_one_point_zero_adds_only_one_point_five_with_provenance(self):
        screen_hash = sha(self.node / 'lipsync_screen.json')
        self.assertFalse(self.scan())
        repair = load(self.repairs)['nodes']['node']
        self.assertEqual(repair['guidance_scale'], 1.5)
        self.assertEqual(repair['original_screen_sha256'], screen_hash)
        self.assertEqual(repair['original_video_sha256'], sha(self.node / 'video.mp4'))
        self.assertEqual(repair['original_confidence'], 2.5)
        self.assertEqual(repair['original_offset_frames'], 0)
        self.assertEqual(self.state['counts']['pending_rerender'], 1)

    def test_one_point_five_failure_reports_once_without_upscaling_or_overwrite(self):
        self.guidance(1.5)
        original = {'guidance_scale': 1.5, 'reason': 'original frozen reason'}
        append_repair(self.repairs, 'node', original)
        self.assertFalse(self.scan())
        self.assertEqual(load(self.repairs)['nodes']['node'], original)
        self.assertEqual(len([e for e in self.events if e['event'] == 'guidance1p5_still_failed']), 1)
        self.scan()
        self.assertEqual(len([e for e in self.events if e['event'] == 'guidance1p5_still_failed']), 1)
        self.assertEqual(self.state['counts']['failed_after_guidance1p5'], 1)

    def test_stale_screen_cannot_trigger_repair(self):
        self.screen(1.0, 8, video_sha256='old-video')
        self.scan()
        self.assertEqual(load(self.repairs)['nodes'], {})
        self.assertEqual(self.state['counts']['awaiting_sync_screen'], 1)
        self.assertFalse(any(e['event'] == 'repair_added' for e in self.events))

    def test_excessive_offset_uses_same_bounded_repair(self):
        self.screen(5.0, -3)
        self.scan()
        repair = load(self.repairs)['nodes']['node']
        self.assertEqual(repair['guidance_scale'], 1.5)
        self.assertEqual(repair['original_offset_frames'], -3)

    def test_repaired_pass_requires_current_target_and_reports_completion(self):
        append_repair(self.repairs, 'node', {'guidance_scale': 1.5, 'reason': 'repair'})
        self.screen(4.0, 1)
        self.assertFalse(self.scan())
        self.guidance(1.5)
        self.assertTrue(self.scan())
        self.assertEqual(self.state['counts']['current_sync_passed'], 1)
        self.assertEqual(self.state['counts']['pending_rerender'], 0)


if __name__ == '__main__':
    unittest.main()
