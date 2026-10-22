"""CPU checks for isolated checkpoint preparation and media input contracts.

Models are never constructed. Temporary fixtures represent a frozen source and
an independent revision; video tests stop at the cache boundary before inference.
"""
from contextlib import ExitStack, redirect_stdout
import copy
import io
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from scripts import render_annotation400_revision as revision


class CheckpointRevisionTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.out = self.root / 'frozen'
        self.revisions = self.root / 'revision'
        self.revisions.mkdir()
        self.stack.enter_context(patch.multiple(revision, ROOT=self.root, OUT=self.out,
                                                REVISION=self.revisions))
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.original_path = self.out / 'scene/node/request.json'
        identity = self.out / 'identity.png'
        identity.parent.mkdir(parents=True)
        identity.write_bytes(b'identity fixture')
        self.original = {
            'node_id': 'scene-t1', 'scenario_id': 'scene', 'location': 't1',
            'source_public_response': 'I will check the record. Then we can agree on a time.',
            'source_observable_expression': {'facial_expression': 'briefly tense',
                                             'gaze': 'steady', 'behavioral_cues': []},
            'voice': 'af_fixture', 'identity': {'identity_path': str(identity.relative_to(self.root)),
                                               'identity_sha256': revision.sha(identity)},
        }
        self.original['spec_sha256'] = revision.digest(self.original)
        revision.save(self.original_path, self.original)
        revision.save(self.original_path.with_name('video.json'), {'guidance_scale': 1.5})
        revision.save(self.out / 'local_av/manifest.json', {'nodes': [{
            'node_id': self.original['node_id'],
            'request_path': str(self.original_path.relative_to(self.root))}]})
        (self.out / 'items.jsonl').write_text('{"frozen":true}\n')
        self.line = {'node_id': self.original['node_id'],
                     'original_response': self.original['source_public_response'],
                     'checkpoint_text': 'I will check the record.',
                     'source_quote': 'I will check the record.', 'verbatim_excerpt': True}
        self.line_path = self.root / 'lines.json'
        self.manifest = self.revisions / 'manifest.json'

    def prepare(self, lines=None):
        revision.save(self.line_path, lines if lines is not None else [self.line])
        revision.prepare([self.line_path], self.manifest)
        row = revision.load(self.manifest)['nodes'][0]
        return Path(row['request_path'])

    def test_prepare_preserves_source_and_keeps_full_reply_in_versioned_candidate(self):
        frozen = {p: p.read_bytes() for p in self.out.rglob('*') if p.is_file()}
        path = self.prepare()
        request = revision.load(path)
        self.assertEqual(request['source_public_response'], self.line['checkpoint_text'])
        self.assertEqual(request['full_public_response'], self.original['source_public_response'])
        self.assertEqual(request['source_observable_expression'], self.original['source_observable_expression'])
        self.assertEqual(request['identity'], self.original['identity'])
        self.assertEqual(request['source_spec_sha256'], self.original['spec_sha256'])
        self.assertEqual(request['spec_sha256'], revision.digest({
            k: v for k, v in request.items() if k != 'spec_sha256'}))
        self.assertTrue(path.resolve().is_relative_to(self.revisions))
        manifest = revision.load(self.manifest)
        self.assertFalse(manifest['release_eligible'])
        self.assertFalse(manifest['published'])
        self.assertEqual(manifest['human_review'], 'pending')
        self.assertEqual({p: p.read_bytes() for p in self.out.rglob('*') if p.is_file()}, frozen)
        # Preparation is reproducible; an exact retry has the same request path.
        self.assertEqual(self.prepare(), path)

    def test_prepare_rejects_stale_or_unsupported_lines_and_duplicates(self):
        invalid = [
            {'original_response': 'An unrelated response.'},
            {'source_quote': 'This never occurred.'},
            {'checkpoint_text': 'We should wait for another meeting.'},
            {'checkpoint_text': 'Too short.'},
        ]
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.prepare([{**self.line, **changes}])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.prepare([self.line, self.line])
        self.assertFalse(self.manifest.exists())

    def test_revision_paths_reject_frozen_paths_parent_escape_and_directory_symlink(self):
        for path in (self.original_path, self.revisions / '../frozen/new.json'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                revision.safe_path(path)
        (self.revisions / 'linked').symlink_to(self.out, target_is_directory=True)
        with self.assertRaises(ValueError):
            revision.safe_path(self.revisions / 'linked/new.json')
        self.assertEqual(revision.safe_path(self.revisions / 'new/request.json'),
                         self.revisions / 'new/request.json')

    def test_content_and_quality_changes_invalidate_cache(self):
        directory = self.revisions / 'cache'
        directory.mkdir()
        generation = {'model_sha256': 'model-a', 'source_sha256': 'implementation-a',
                      'audio_sha256': 'audio-a', 'motion_sha256': 'motion-a',
                      'steps': 40, 'deepcache': False, 'guidance_scale': 1.5, 'seed': 123}
        video = directory / 'video.mp4'
        video.write_bytes(b'rendered candidate')
        revision.save(directory / 'video.json', {
            'sha256': revision.sha(video), 'generation_sha256': revision.digest(generation)})
        self.assertTrue(revision.current(directory, 'video', generation))
        for key, value in [('model_sha256', 'model-b'), ('source_sha256', 'implementation-b'),
                           ('audio_sha256', 'audio-b'), ('motion_sha256', 'motion-b'),
                           ('steps', 50), ('deepcache', True), ('guidance_scale', 1), ('seed', 456)]:
            with self.subTest(key=key):
                self.assertFalse(revision.current(directory, 'video', {**generation, key: value}))
        video.write_bytes(b'replaced media without a new receipt')
        self.assertFalse(revision.current(directory, 'video', generation))
        video.unlink()
        self.assertFalse(revision.current(directory, 'video', generation))

    def test_dependency_fingerprints_read_contents_and_fail_on_missing_models(self):
        model = self.root / 'model.bin'
        config = self.root / 'config.json'
        model.write_bytes(b'first checkpoint')
        config.write_text('{"resolution":512}\n')
        before = revision.file_fingerprints([model, config, model])
        self.assertEqual(len(before), 2)
        self.assertEqual(before, revision.file_fingerprints([config, model]))
        model.write_bytes(b'updated checkpoint')
        after = revision.file_fingerprints([model, config])
        self.assertNotEqual(before['model.bin'], after['model.bin'])
        self.assertEqual(before['config.json'], after['config.json'])
        model.unlink()
        with self.assertRaises(FileNotFoundError):
            revision.file_fingerprints([model, config])

    def test_tampered_request_cannot_reach_render(self):
        path = self.prepare()
        request = revision.load(path)
        request['source_public_response'] = 'This line was not approved in preparation.'
        revision.save(path, request)
        worker = SimpleNamespace(render=unittest.mock.Mock())
        with patch.object(revision, 'Speech', return_value=worker) as construct, patch('sys.argv', [
                'revision', 'audio', '--manifest', str(self.manifest)]):
            with self.assertRaisesRegex(ValueError, 'changed'):
                revision.main()
        construct.assert_not_called()
        worker.render.assert_not_called()

    def test_manifest_cannot_relabel_a_valid_checkpoint_as_another_node_or_scene(self):
        path = self.prepare()
        row = revision.load(self.manifest)['nodes'][0]
        self.assertEqual(revision.validate_request(row), path)
        for field in ('node_id', 'scenario_id', 'spec_sha256'):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'changed'):
                revision.validate_request({**row, field: 'another'})

    def test_output_symlinks_cannot_redirect_rendering_to_frozen_files(self):
        path = self.prepare()
        row = revision.load(self.manifest)['nodes'][0]
        frozen = self.original_path.read_bytes()
        for name in ('speech.wav', 'motion.mp4', 'video.mp4', 'runtime'):
            linked = path.parent / name
            target = self.original_path.parent if name == 'runtime' else self.original_path
            linked.symlink_to(target, target_is_directory=name == 'runtime')
            with self.subTest(name=name), self.assertRaises(ValueError):
                revision.validate_request(row)
            linked.unlink()
        self.assertEqual(self.original_path.read_bytes(), frozen)
        # Only the existing upstream model/config targets are allowed outside.
        runtime = path.parent / 'runtime'
        runtime.mkdir()
        for name in ('checkpoints', 'configs'):
            model_directory = self.root / '.local_tools/annotation400-latentsync' / name
            model_directory.mkdir(parents=True)
            (runtime / name).symlink_to(model_directory, target_is_directory=True)
        self.assertEqual(revision.validate_request(row), path)
        (runtime / 'configs').unlink()
        (runtime / 'configs').symlink_to(self.out, target_is_directory=True)
        with self.assertRaises(ValueError):
            revision.validate_request(row)

    def test_trim_keeps_internal_pause_and_quiet_final_syllable(self):
        sample_rate = 24000
        samples = np.zeros(sample_rate * 4, dtype=np.float32)
        samples[12000:24000] = .1 * np.sin(np.arange(12000) * .1)
        # A 1-second pause is part of the utterance, not a trim boundary.
        samples[48000:60000] = .08 * np.sin(np.arange(12000) * .1)
        samples[60000:66000] = .002 * np.sin(np.arange(6000) * .1)
        trimmed, info = revision.trim_edges(samples, sample_rate)
        self.assertLessEqual(info['start_samples'], 12000 - .09 * sample_rate)
        self.assertGreaterEqual(info['end_samples'], 66000 + .15 * sample_rate)
        np.testing.assert_array_equal(trimmed, samples[info['start_samples']:info['end_samples']])
        self.assertTrue(np.all(trimmed[24000-info['start_samples']:48000-info['start_samples']] == 0))
        self.assertGreater(np.max(np.abs(trimmed[60000-info['start_samples']:66000-info['start_samples']])), .0019)
        with self.assertRaisesRegex(ValueError, 'audible'):
            revision.trim_edges(np.zeros(sample_rate, dtype=np.float32), sample_rate)

    def speech_worker(self, samples):
        speech = revision.Speech.__new__(revision.Speech)
        speech.weights = self.root / 'models/kokoro'
        (speech.weights / 'voices').mkdir(parents=True)
        (speech.weights / 'voices/af_fixture.pt').write_bytes(b'voice fixture')
        speech.model_sha, speech.dependencies = 'fixture-model', {'config_sha256': 'fixture-config'}
        speech.torch = SimpleNamespace(load=lambda *args, **kwargs: 'fixture voice')
        audio = SimpleNamespace(cpu=lambda: SimpleNamespace(numpy=lambda: samples.copy()))
        speech.pipeline = unittest.mock.Mock(return_value=[SimpleNamespace(audio=audio)])
        return speech

    @unittest.skipUnless(shutil.which('ffmpeg'), 'CPU ffmpeg is required for audio preservation check')
    def test_speech_render_preserves_final_sound_and_only_pads_to_checkpoint_length(self):
        import soundfile as sf
        path = self.prepare()
        sample_rate = 24000
        samples = np.zeros(round(4.16 * sample_rate), dtype=np.float32)
        first, last = round(.1 * sample_rate), round(4 * sample_rate)
        samples[first:last] = .1 * np.sin(np.arange(last-first) * 2 * np.pi * 440 / sample_rate)
        # Give the final syllable a unique spectrum so a clipped ending fails.
        final_start = round(3.8 * sample_rate)
        samples[final_start:last] = .1 * np.sin(np.arange(last-final_start) * 2 * np.pi * 2000 / sample_rate)
        speech = self.speech_worker(samples)
        speech.render(path)
        output, output_rate = sf.read(path.with_name('speech.wav'))
        self.assertEqual(output_rate, sample_rate)
        self.assertEqual(len(output), round(4.6 * sample_rate))
        ending = output[round(3.91 * sample_rate):round(4.03 * sample_rate)]
        spectrum = np.abs(np.fft.rfft(ending))
        frequency = np.fft.rfftfreq(len(ending), 1 / sample_rate)[np.argmax(spectrum)]
        self.assertAlmostEqual(frequency, 2000, delta=30)
        self.assertGreater(float(np.sqrt(np.mean(ending ** 2))), .04)
        self.assertLess(float(np.max(np.abs(output[round(4.3 * sample_rate):]))), .001)
        receipt = revision.load(path.with_name('speech.json'))
        self.assertEqual(receipt['spoken_text'], self.line['checkpoint_text'])
        self.assertLess(receipt['speech_seconds_before_padding'] + .08, 4.6)
        count = speech.pipeline.call_count
        speech.render(path)
        self.assertEqual(speech.pipeline.call_count, count)
        (speech.weights / 'voices/af_fixture.pt').write_bytes(b'updated voice weights')
        speech.render(path)
        self.assertGreater(speech.pipeline.call_count, count)

    def test_overlong_speech_fails_instead_of_cutting_words_or_creating_final_waveform(self):
        path = self.prepare()
        samples = (.1 * np.sin(np.arange(24000 * 9) * .1)).astype(np.float32)
        speech = self.speech_worker(samples)
        with patch.object(revision, 'run') as encode:
            with self.assertRaisesRegex(ValueError, 'shorter wording'):
                speech.render(path)
            encode.assert_not_called()
        self.assertFalse(path.with_name('speech.wav').exists())
        self.assertFalse(path.with_name('speech.json').exists())

    def test_changed_identity_is_rejected_before_animator_can_reuse_cached_motion(self):
        path = self.prepare()
        motion = revision.Motion.__new__(revision.Motion)
        motion.animator = SimpleNamespace(render=unittest.mock.Mock())
        identity = self.root / self.original['identity']['identity_path']
        identity.write_bytes(b'a different character image')
        with self.assertRaisesRegex(ValueError, 'Identity source changed'):
            motion.render(path)
        motion.animator.render.assert_not_called()

    def test_asr_uses_unprompted_complete_audio_and_binds_screen_to_exact_waveform(self):
        path = self.prepare()
        audio = path.with_name('speech.wav')
        audio.write_bytes(b'entire-waveform-fixture')
        asr = revision.ASR.__new__(revision.ASR)
        asr.model = SimpleNamespace(transcribe=unittest.mock.Mock(return_value=(
            [SimpleNamespace(text=self.line['checkpoint_text'])], SimpleNamespace(language='en'))))
        asr.render(path)
        args, kwargs = asr.model.transcribe.call_args
        self.assertEqual(args, (str(audio),))
        self.assertFalse(kwargs['vad_filter'])
        self.assertFalse(kwargs['condition_on_previous_text'])
        self.assertNotIn('initial_prompt', kwargs)
        screen = revision.load(path.with_name('audio_screen.json'))
        self.assertTrue(screen['machine_screen_passed'])
        self.assertEqual(screen['sha256'], revision.sha(audio))
        self.assertEqual(screen['spec_sha256'], revision.load(path)['spec_sha256'])
        self.assertEqual(screen['expected'], self.line['checkpoint_text'])
        asr.model.transcribe.return_value = ([SimpleNamespace(text='I will change the record.')],
                                           SimpleNamespace(language='en'))
        asr.render(path)
        self.assertFalse(revision.load(path.with_name('audio_screen.json'))['machine_screen_passed'])

    def video_inputs(self):
        path = self.prepare()
        request = revision.load(path)
        directory = path.parent
        (directory / 'speech.wav').write_bytes(b'checked waveform fixture')
        (directory / 'motion.mp4').write_bytes(b'bound motion fixture')
        revision.save(directory / 'audio_screen.json', {
            'spec_sha256': request['spec_sha256'], 'sha256': revision.sha(directory / 'speech.wav'),
            'expected': request['source_public_response'], 'machine_screen_passed': True})
        revision.save(directory / 'motion.json', {
            'spec_sha256': request['spec_sha256'], 'sha256': revision.sha(directory / 'motion.mp4'),
            'audio_sha256': revision.sha(directory / 'speech.wav'),
            'identity_sha256': request['identity']['identity_sha256'],
            'controls_source_sha256': 'public-controls-and-dependencies'})
        tool = self.root / 'tool'
        (tool / 'configs/unet').mkdir(parents=True)
        (tool / 'configs/unet/stage2_512.yaml').write_text('fixture: true\n')
        (tool / 'mask.png').write_bytes(b'mask')
        video = revision.Video.__new__(revision.Video)
        video.base = SimpleNamespace(config=SimpleNamespace(data=SimpleNamespace(mask_image_path='mask.png')),
                                     model_sha256='local-unet')
        video.tool, video.steps, video.guidance = tool, 40, None
        video.dependencies = {'checkpoints/vae/weights': 'vae-model-a',
                              'checkpoints/whisper/tiny.pt': 'audio-model-a'}
        return path, video

    def test_video_rejects_stale_audio_screen_before_cache_or_inference(self):
        path, video = self.video_inputs()
        screen_path = path.with_name('audio_screen.json')
        original = revision.load(screen_path)
        for field, value in [('sha256', 'different-waveform'), ('spec_sha256', 'different-checkpoint'),
                             ('expected', 'A different spoken sentence.'), ('machine_screen_passed', False)]:
            revision.save(screen_path, {**original, field: value})
            with self.subTest(field=field), patch.object(revision, 'current') as current:
                with self.assertRaisesRegex(ValueError, 'speech check'):
                    video.render(path)
                current.assert_not_called()

    def test_video_rejects_wrong_motion_waveform_identity_spec_and_content(self):
        path, video = self.video_inputs()
        receipt_path = path.with_name('motion.json')
        original = revision.load(receipt_path)
        for field in ('audio_sha256', 'identity_sha256', 'spec_sha256', 'sha256'):
            revision.save(receipt_path, {**original, field: 'wrong'})
            with self.subTest(field=field), patch.object(revision, 'current') as current:
                with self.assertRaisesRegex(ValueError, 'Motion is not bound'):
                    video.render(path)
                current.assert_not_called()

    def test_video_cache_spec_tracks_real_input_bytes_and_quality(self):
        path, video = self.video_inputs()
        with patch.object(revision, 'current', return_value=True) as current:
            video.render(path)
        generation = copy.deepcopy(current.call_args.args[2])
        self.assertEqual(generation['audio_sha256'], revision.sha(path.with_name('speech.wav')))
        self.assertEqual(generation['motion_sha256'], revision.sha(path.with_name('motion.mp4')))
        self.assertEqual(generation['guidance_scale'], 1.5)
        self.assertEqual(generation['steps'], 40)
        self.assertFalse(generation['deepcache'])
        # A review note does not alter pixels or warrant another GPU render.
        receipt = revision.load(path.with_name('motion.json'))
        revision.save(path.with_name('motion.json'), {**receipt, 'human_review': 'accepted'})
        with patch.object(revision, 'current', return_value=True) as current:
            video.render(path)
        self.assertEqual(current.call_args.args[2], generation)
        video.dependencies['checkpoints/vae/weights'] = 'vae-model-b'
        with patch.object(revision, 'current', return_value=True) as current:
            video.render(path)
        self.assertNotEqual(revision.digest(current.call_args.args[2]), revision.digest(generation))
        video.steps, video.guidance = 50, 1.0
        with patch.object(revision, 'current', return_value=True) as current:
            video.render(path)
        self.assertNotEqual(revision.digest(current.call_args.args[2]), revision.digest(generation))
        self.assertFalse(path.with_name('runtime').exists())


if __name__ == '__main__':
    unittest.main()
