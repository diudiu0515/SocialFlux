"""Portable preview tests: strict source binding, incomplete batches, and public-only output."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts import package_checkpoint_revision as preview


class CheckpointPackageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.revision = self.root / 'revision'
        self.directory = self.revision / 'scene/node/spec'
        self.directory.mkdir(parents=True)
        self.output = self.root / 'preview'
        self.manifest = self.revision / 'manifest.json'
        identity = self.root / 'identity.png'
        identity.write_bytes(b'public identity fixture')
        self.request = {'node_id': 'scene-t1', 'scenario_id': 'scene', 'location': 't1',
                        'method': 'checkpoint_4s5s_v2', 'source_public_response': 'I will check the public record before we proceed.',
                        'full_public_response': 'I will check the public record before we proceed. Nothing is confirmed yet.',
                        'source_observable_expression': {'facial_expression': 'Concerned', 'gaze': 'Steady',
                                                        'private_reason': 'DO_NOT_EXPORT_PRIVATE_EXPRESSION'},
                        'private_evidence': 'DO_NOT_EXPORT_PRIVATE_REQUEST',
                        'credential': 'DO_NOT_EXPORT_CREDENTIAL',
                        'identity': {'identity_path': str(identity), 'identity_sha256': preview.file_sha(identity)}}
        self.request['checkpoint_line'] = {
            'checkpoint_text': self.request['source_public_response'],
            'original_response': self.request['full_public_response'],
            'source_quote': self.request['source_public_response']}
        self.prepare_request()
        (self.directory / 'speech.wav').write_bytes(b'public speech fixture')
        (self.directory / 'motion.mp4').write_bytes(b'public motion fixture')
        (self.directory / 'video.mp4').write_bytes(b'public final candidate fixture')
        audio = preview.file_sha(self.directory / 'speech.wav')
        motion = preview.file_sha(self.directory / 'motion.mp4')
        video = preview.file_sha(self.directory / 'video.mp4')
        speech_generation = {'spec_sha256': self.spec, 'voice_sha256': 'voice-model'}
        self.save('speech.json', {'spec_sha256': self.spec, 'sha256': audio,
                                  'spoken_text': self.request['source_public_response'],
                                  'generation_spec': speech_generation,
                                  'generation_sha256': preview.digest(speech_generation)})
        self.save('audio_screen.json', {'spec_sha256': self.spec, 'sha256': audio,
            'expected': self.request['source_public_response'], 'transcript': self.request['source_public_response'],
            'language': 'en', 'normalized_similarity': 1.0, 'critical_content_match': True,
            'unprompted': True, 'machine_screen_passed': True,
            'credential': 'DO_NOT_EXPORT_CREDENTIAL'})
        self.save('motion.json', {'spec_sha256': self.spec, 'sha256': motion, 'audio_sha256': audio,
                                  'identity_sha256': self.request['identity']['identity_sha256'],
                                  'controls_source_sha256': 'public-controls'})
        generation = {'spec_sha256': self.spec, 'audio_sha256': audio, 'motion_sha256': motion,
                      'motion_source_sha256': 'public-controls'}
        self.save('video.json', {'spec_sha256': self.spec, 'sha256': video, 'audio_sha256': audio,
                                'motion_sha256': motion, 'spoken_text': self.request['source_public_response'],
                                'generation_spec': generation, 'generation_sha256': preview.digest(generation),
                                'structural_metadata': {'duration_seconds_actual': 99}})
        self.save('lipsync_screen.json', {'video_sha256': video, 'complete_clip': True,
                                         'confidence': 4.1, 'offset_frames': 0, 'machine_screen_passed': True})

    def save(self, name, value):
        (self.directory / name).write_text(json.dumps(value))

    def prepare_request(self):
        self.request.pop('spec_sha256', None)
        self.spec = preview.digest(self.request)
        self.request['spec_sha256'] = self.spec
        self.save('request.json', self.request)
        self.manifest.write_text(json.dumps({'version': 'checkpoint_4s5s_v2', 'node_count': 1,
            'private_evidence': 'DO_NOT_EXPORT_PRIVATE_MANIFEST', 'human_review': 'accepted',
            'nodes': [{'node_id': 'scene-t1', 'scenario_id': 'scene', 'spec_sha256': self.spec,
                       'request_path': str(self.directory / 'request.json')}]}))

    def package(self, **kwargs):
        return preview.package(self.manifest, self.output, root=self.root,
            probe=lambda _: {'duration_seconds': 4.6, 'video_seconds': 4.6, 'audio_seconds': 4.6}, **kwargs)

    def card(self):
        return json.loads((self.output / 'package.json').read_text())['nodes'][0]

    def mutate(self, name, **values):
        data = json.loads((self.directory / name).read_text())
        data.update(values)
        self.save(name, data)

    def test_portable_bundle_copies_only_new_video_and_public_data(self):
        zip_path = self.root / 'preview.zip'
        result = self.package(zip_path=zip_path)
        card = self.card()
        self.assertEqual(result['status_counts'], {'passed': 1})
        self.assertEqual(card['duration_seconds'], 4.6)  # ffprobe, never stale metadata's 99 seconds
        self.assertEqual(card['human_review'], 'pending')
        self.assertFalse(result['published'])
        self.assertTrue(card['video'].startswith('videos/'))
        copy_path = self.output / card['video']
        self.assertFalse(copy_path.is_symlink())
        self.assertNotEqual(copy_path.stat().st_ino, (self.directory / 'video.mp4').stat().st_ino)
        self.assertEqual(copy_path.read_bytes(), (self.directory / 'video.mp4').read_bytes())
        text = (self.output / 'index.html').read_text()
        self.assertIn('type="application/json"', text)
        self.assertIn("v.preload='metadata'", text)
        self.assertNotIn('fetch(', text)
        for secret in ('DO_NOT_EXPORT', str(self.root)):
            self.assertNotIn(secret, text)
            self.assertNotIn(secret, (self.output / 'package.json').read_text())
        self.assertNotIn('private_reason', card['expression'])
        self.assertEqual(preview.verify_package(self.output)['videos'], 1)
        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
            self.assertIn('preview/index.html', names)
            self.assertEqual(len(names), 4)
            self.assertFalse(any('request' in n or n.endswith('.wav') for n in names))
        # Rebuilding our own snapshot is supported and remains verifiable.
        self.package()
        preview.verify_package(self.output)

    def test_missing_media_and_checks_remain_explicit_cards(self):
        (self.directory / 'video.mp4').unlink()
        self.package()
        card = self.card()
        self.assertIsNone(card['video'])
        self.assertEqual(card['checks']['video_binding']['status'], 'missing')
        self.assertNotEqual(card['status'], 'passed')
        (self.directory / 'audio_screen.json').unlink()
        (self.directory / 'lipsync_screen.json').unlink()
        self.package()
        card = self.card()
        self.assertEqual(card['checks']['audio']['status'], 'pending')
        self.assertEqual(card['checks']['sync']['status'], 'pending')

    def test_old_video_score_cannot_survive_byte_change(self):
        (self.directory / 'video.mp4').write_bytes(b'replaced candidate')
        self.package()
        card = self.card()
        self.assertEqual(card['checks']['video_binding']['status'], 'invalid')
        self.assertEqual(card['checks']['sync']['status'], 'invalid')
        self.assertIsNone(card['video'])

    def test_replaced_audio_or_motion_invalidates_dependent_scores(self):
        for name, check_name in [('speech.wav', 'audio'), ('motion.mp4', 'motion_binding')]:
            with self.subTest(name=name):
                path = self.directory / name
                original = path.read_bytes()
                path.write_bytes(original + b'changed')
                self.package()
                card = self.card()
                self.assertEqual(card['checks'][check_name]['status'], 'invalid')
                self.assertEqual(card['checks']['sync']['status'], 'invalid')
                self.assertIsNotNone(card['video'])  # failed candidate remains inspectable
                path.write_bytes(original)

    def test_wrong_spec_and_forged_positive_flags_never_show_pass(self):
        self.mutate('audio_screen.json', spec_sha256='old-spec')
        self.package()
        self.assertEqual(self.card()['checks']['audio']['status'], 'invalid')
        self.mutate('audio_screen.json', spec_sha256=self.spec, normalized_similarity=.8)
        self.mutate('lipsync_screen.json', confidence=2.5)
        self.package()
        self.assertEqual(self.card()['checks']['audio']['status'], 'failed')
        self.assertEqual(self.card()['checks']['sync']['status'], 'failed')
        self.mutate('lipsync_screen.json', video_sha256='old-video')
        self.package()
        self.assertEqual(self.card()['checks']['sync']['status'], 'invalid')

    def test_request_tampering_cannot_attach_current_checks(self):
        self.mutate('request.json', source_public_response='Changed without a new version.')
        self.package()
        card = self.card()
        self.assertEqual(card['status'], 'invalid')
        self.assertIsNone(card['video'])
        self.assertEqual(card['checkpoint_text'], '')

    def test_inline_json_cannot_close_script_or_inject_html(self):
        data = {'nodes': [{'checkpoint_text': '</script><script>alert("oops")</script>&\u2028'}]}
        rendered = preview.render_html(data)
        self.assertNotIn('</script><script>alert', rendered)
        embedded = rendered.split('type="application/json">', 1)[1].split('</script>', 1)[0]
        self.assertEqual(json.loads(embedded), data)
        self.assertIn('textContent=text', rendered)

    def test_verification_rejects_changed_copies_extra_files_and_symlinks(self):
        self.package()
        video = self.output / self.card()['video']
        original = video.read_bytes()
        video.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'SHA mismatch'):
            preview.verify_package(self.output)
        video.write_bytes(original)
        extra = self.output / 'private.json'
        extra.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'file list'):
            preview.verify_package(self.output)
        extra.unlink()
        video.unlink()
        video.symlink_to(self.directory / 'video.mp4')
        with self.assertRaisesRegex(ValueError, 'SHA mismatch'):
            preview.verify_package(self.output)

    def test_unsafe_output_and_unowned_directory_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'separate'):
            preview.package(self.manifest, self.revision / 'preview', root=self.root)
        self.output.mkdir()
        (self.output / 'keep.txt').write_text('unrelated user data')
        with self.assertRaisesRegex(ValueError, 'Refusing'):
            self.package()
        self.assertEqual((self.output / 'keep.txt').read_text(), 'unrelated user data')

    def test_malformed_receipts_fail_closed_without_breaking_page(self):
        self.mutate('audio_screen.json', normalized_similarity='unknown')
        self.mutate('video.json', generation_spec=[])
        self.package()
        card = self.card()
        self.assertEqual(card['checks']['audio']['status'], 'failed')
        self.assertNotIn('normalized_similarity', card['checks']['audio'])
        self.assertEqual(card['checks']['video_binding']['status'], 'invalid')
        self.assertEqual(card['checks']['sync']['status'], 'invalid')

    def test_audio_video_duration_is_measured_and_failed_independently(self):
        preview.package(self.manifest, self.output, root=self.root,
            probe=lambda _: {'duration_seconds': 5.5, 'video_seconds': 5.5, 'audio_seconds': 4.6})
        self.assertEqual(self.card()['checks']['duration']['status'], 'failed')
        self.assertEqual(self.card()['duration_seconds'], 5.5)


if __name__ == '__main__':
    unittest.main()
