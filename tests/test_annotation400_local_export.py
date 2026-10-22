"""Reject stale or incorrectly spoken local renders before media publication."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import wave

from offline.talking_head import canonical_sha
from scripts.build_annotation400 import load, save, sha
from scripts.export_annotation400 import LocalAssetError, validate_local_asset, _legacy_asset
from scripts.screen_annotation400_local_av import VERSION


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'local ffmpeg is required')
class LocalExportTest(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self.root / 'local_av/GPT50_003/node-ending'
        self.directory.mkdir(parents=True)
        self.node = {'node_id': 'node-ending', 'scenario_id': 'GPT50_003', 'location': 'ending',
                     'speaker': {'character_id': 'editor', 'name': 'Inez'},
                     'source_public_response': 'Do not release the two records.',
                     'source_observable_expression': {'facial_expression': 'neutral', 'gaze': 'direct'},
                     'bindings': [{'instance_id': 'T2-1', 'evidence_ids': ['ending']},
                                  {'instance_id': 'T2-2', 'evidence_ids': ['ending']}]}
        speech = self.directory / 'speech.wav'
        with wave.open(str(speech), 'wb') as stream:
            stream.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            stream.writeframes(b'\0\0' * 24000)
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=gray:s=64x64:r=25:d=1',
                        '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                        str(self.directory / 'motion.mp4')], check=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(self.directory / 'motion.mp4'),
                        '-i', str(speech), '-c:v', 'copy', '-c:a', 'aac', '-ar', '48000',
                        str(self.directory / 'video.mp4')], check=True)
        # The identity and source hashes are separate frozen inputs. Visual
        # quality remains human-reviewed; these tests exercise file provenance.
        (self.root / 'identity.png').write_bytes(b'original fictional identity fixture')
        shutil.copyfile(self.directory / 'motion.mp4', self.root / 'source.mp4')
        identity = {'scene': 'GPT50_003', 'identity_path': 'identity.png',
                    'identity_sha256': sha(self.root / 'identity.png'), 'source_path': 'source.mp4',
                    'source_sha256': sha(self.root / 'source.mp4'),
                    'source_kind': 'existing_original_nonverbal_video', 'extraction_seconds': .12}
        self.request = {k: deepcopy(v) for k, v in self.node.items() if k != 'bindings'}
        self.request.update(identity=identity, voice='af_sarah', speed=1.0, speech_language='en',
                            motion_source='public_facial_expression_and_gaze_only',
                            method='local_photorealistic_dubbing_v1', human_review='pending')
        self.spec = canonical_sha(self.request)
        self.request['spec_sha256'] = self.spec
        save(self.directory / 'request.json', self.request)
        self.audio_hash = sha(speech)
        self.video_hash = sha(self.directory / 'video.mp4')
        save(self.directory / 'speech.json', {'spec_sha256': self.spec, 'sha256': self.audio_hash,
            'spoken_text': self.node['source_public_response'], 'speech_language': 'en',
            'voice': 'af_sarah', 'speed': 1.0, 'duration_seconds': 1.0, 'model': 'fixture',
            'model_sha256': 'a' * 64, 'voice_sha256': 'b' * 64})
        save(self.directory / 'motion.json', {'spec_sha256': self.spec,
            'sha256': sha(self.directory / 'motion.mp4'), 'audio_sha256': self.audio_hash,
            'identity_sha256': identity['identity_sha256'], 'frames': 25, 'fps': 25,
            'method': 'LivePortrait_public_cues_v1'})
        save(self.directory / 'video.json', {'spec_sha256': self.spec, 'sha256': self.video_hash,
            'audio_sha256': self.audio_hash, 'motion_sha256': sha(self.directory / 'motion.mp4'),
            'identity_sha256': identity['identity_sha256'], 'spoken_text': self.node['source_public_response'],
            'speech_language': 'en', 'model': 'fixture', 'model_sha256': 'c' * 64,
            'structural_metadata': self.probe()})
        for stage, h in [('audio', self.audio_hash), ('video', self.video_hash)]:
            save(self.directory / (stage + '_screen.json'), {'node_id': self.node['node_id'],
                'sha256': h, 'version': VERSION, 'spec_sha256': self.spec,
                'expected': self.node['source_public_response'], 'transcript': self.node['source_public_response'],
                'language': 'en', 'normalized_similarity': 1.0, 'critical_content_match': True,
                'machine_screen_passed': True, 'human_review': 'pending', 'speech_verified': False})

        save(self.directory / 'lipsync_screen.json', {'node_id': self.node['node_id'],
            'version': 'independent_syncnet_v1', 'spec_sha256': self.spec,
            'video_sha256': self.video_hash, 'confidence': 4.2, 'offset_frames': 0,
            'frame_rate': 25, 'machine_screen_passed': True, 'human_review': 'pending'})

    def test_lipsync_measurements_must_match_video_and_pass_frozen_threshold(self):
        original = load(self.directory / 'lipsync_screen.json')
        for values, error in [({'video_sha256': 'd' * 64}, 'lipsync_screen_stale'),
                              ({'confidence': 2.99}, 'lipsync_screen_failed'),
                              ({'offset_frames': 3}, 'lipsync_screen_failed'),
                              ({'machine_screen_passed': False}, 'lipsync_screen_failed'),
                              ({'confidence': float('nan')}, 'lipsync_screen_failed')]:
            with self.subTest(values=values):
                save(self.directory / 'lipsync_screen.json', {**original, **values})
                with self.assertRaisesRegex(LocalAssetError, error):
                    self.validate()

    def probe(self):
        data = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams',
            '-show_format', '-of', 'json', str(self.directory / 'video.mp4')]))
        video = next(s for s in data['streams'] if s['codec_type'] == 'video')
        audio = next(s for s in data['streams'] if s['codec_type'] == 'audio')
        return {'duration_seconds_actual': float(data['format']['duration']),
                'video_duration_seconds': float(video['duration']), 'audio_duration_seconds': float(audio['duration']),
                'audio_stream_count': 1, 'video_stream_count': 1}

    def validate(self):
        return validate_local_asset(self.node, self.directory, expected_spec_sha256=self.spec, root=self.root)

    def change(self, filename, **fields):
        data = load(self.directory / filename)
        data.update(fields)
        save(self.directory / filename, data)

    def test_complete_chain_has_explicit_provenance_and_pending_human_review(self):
        asset = self.validate()
        self.assertEqual(asset['provider'], 'local')
        self.assertEqual(asset['source_asset_id'], self.node['node_id'])
        self.assertEqual(asset['human_review'], 'pending')
        self.assertFalse(asset['speech_verified'])
        self.assertEqual(asset['provenance']['artifact_sha256']['speech.wav'], self.audio_hash)
        self.assertNotIn('segment_request_ids', asset)
        self.assertNotIn('boundary_silence_edits', asset)
        # Both controlled T2 variants retain one shared ending asset.
        bindings = {b['instance_id']: asset['sha256'] for b in self.node['bindings']}
        self.assertEqual(len(set(bindings.values())), 1)

    def test_public_line_expression_speaker_and_location_tampering_is_rejected(self):
        changes = {'source_public_response': 'Release the records.',
                   'source_observable_expression': {'facial_expression': 'angry'},
                   'speaker': {'name': 'Someone else'}, 'location': 't1'}
        for key, value in changes.items():
            with self.subTest(key=key):
                changed = deepcopy(self.request)
                changed[key] = value
                changed['spec_sha256'] = canonical_sha({k: v for k, v in changed.items() if k != 'spec_sha256'})
                save(self.directory / 'request.json', changed)
                with self.assertRaisesRegex(LocalAssetError, 'public_input_mismatch_' + key):
                    validate_local_asset(self.node, self.directory, expected_spec_sha256=changed['spec_sha256'], root=self.root)

    def test_modified_request_cannot_keep_the_old_frozen_spec(self):
        self.change('request.json', speed=.9)
        with self.assertRaisesRegex(LocalAssetError, 'request_spec_mismatch'):
            self.validate()

    def test_changed_audio_bytes_invalidate_the_old_speech_receipt(self):
        path = self.directory / 'speech.wav'
        payload = bytearray(path.read_bytes())
        payload[-1] = 1
        path.write_bytes(payload)
        with self.assertRaisesRegex(LocalAssetError, 'speech_hash_mismatch'):
            self.validate()

    def test_old_motion_or_video_audio_binding_is_rejected(self):
        for filename, error in [('motion.json', 'motion_audio_hash_mismatch'),
                                ('video.json', 'video_audio_hash_mismatch')]:
            with self.subTest(filename=filename):
                self.change(filename, audio_sha256='d' * 64)
                with self.assertRaisesRegex(LocalAssetError, error):
                    self.validate()
                self.change(filename, audio_sha256=self.audio_hash)

    def test_missing_screen_and_old_screen_hash_are_rejected(self):
        self.change('audio_screen.json', sha256='d' * 64)
        with self.assertRaisesRegex(LocalAssetError, 'audio_screen_stale'):
            self.validate()
        (self.directory / 'video_screen.json').unlink()
        with self.assertRaisesRegex(LocalAssetError, 'missing_video_screen.json'):
            self.validate()

    def test_every_media_stage_and_receipt_is_required(self):
        for name in ('speech.wav', 'speech.json', 'motion.mp4', 'motion.json', 'video.mp4', 'video.json'):
            with self.subTest(name=name):
                path = self.directory / name
                archive = self.directory / (name + '.held')
                path.rename(archive)
                with self.assertRaisesRegex(LocalAssetError, 'missing_' + name):
                    self.validate()
                archive.rename(path)

    def test_changed_original_identity_source_is_rejected(self):
        (self.root / 'source.mp4').write_bytes(b'replaced source video')
        with self.assertRaisesRegex(LocalAssetError, 'source_hash_mismatch'):
            self.validate()

    def test_failed_video_asr_cannot_be_exported(self):
        self.change('video_screen.json', machine_screen_passed=False, normalized_similarity=.8)
        with self.assertRaisesRegex(LocalAssetError, 'video_screen_failed'):
            self.validate()

    def test_forged_pass_flags_do_not_hide_missing_negation_in_transcript(self):
        self.change('video_screen.json', transcript='Do release the two records.')
        with self.assertRaisesRegex(LocalAssetError, 'video_screen_failed'):
            self.validate()

    def test_real_video_duration_is_checked_even_with_updated_hash_and_screen(self):
        replacement = self.directory / 'short.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(self.directory / 'video.mp4'), '-t', '0.4',
                        '-c:v', 'libx264', '-c:a', 'aac', str(replacement)], check=True)
        replacement.replace(self.directory / 'video.mp4')
        h = sha(self.directory / 'video.mp4')
        self.change('video.json', sha256=h, structural_metadata=self.probe())
        self.change('video_screen.json', sha256=h)
        self.change('lipsync_screen.json', video_sha256=h)
        self.change('lipsync_screen.json', video_sha256=h)
        with self.assertRaisesRegex(LocalAssetError, 'video_audio_duration_mismatch'):
            self.validate()

    def test_legacy_segment_version_guard_remains_required(self):
        directory = self.root / 'audio_video' / self.node['scenario_id']
        directory.mkdir(parents=True)
        save(directory / 'manifest.json', {'nodes': [{**self.node, 'segment_request_ids': ['current-version']}]})
        save(directory / 'completed_nodes.json', [{'node_id': self.node['node_id'],
             'asset': {'boundary_silence_edits': [{'request_id': 'old-version'}]}}])
        gaps = []
        with patch('scripts.export_annotation400.OUT', self.root):
            self.assertIsNone(_legacy_asset(self.node, gaps))
        self.assertEqual(gaps[0]['reason'], 'current_identity_version_not_assembled')


if __name__ == '__main__':
    unittest.main()
