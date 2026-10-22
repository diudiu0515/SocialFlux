"""Source-language speech, shared T2 endings, and zero-network queue preparation."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
import shutil
import subprocess
from tempfile import TemporaryDirectory
from unittest.mock import patch

from offline.talking_head import BANK, PROFILE, public_nodes, split_line, spoken_units, generate, publish, trim_boundary_silence, concatenate_spoken_segments
from scripts.run_autodl_seedance_video import validate_payload
from scripts.run_multimodal_video_queue import seedance_payload


class OfflineTalkingHeadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = [json.loads(line) for line in (BANK / 'items.jsonl').read_text().splitlines()]

    def test_segmentation_preserves_every_original_character(self):
        lines = [n['source_public_response'] for n in public_nodes(self.items)]
        lines += ['First check attributed read-back; 然后确认二楼216房间。' * 7]
        for line in lines:
            parts = split_line(line)
            self.assertEqual(''.join(parts), line)
            self.assertTrue(all(part.strip() and spoken_units(part) <= 42 for part in parts))
        with self.assertRaisesRegex(ValueError, 'empty source'):
            split_line(' ')

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'local ffmpeg is required')
    def test_mixed_audio_sample_rates_keep_speech_and_video_duration_aligned(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);files=[]
            for index,rate in enumerate((32000,44100)):
                path=root/f'{index}.mp4';files.append(path)
                subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error',
                    '-f','lavfi','-i','color=c=gray:s=128x72:r=24:d=2',
                    '-f','lavfi','-i',f'sine=frequency=440:sample_rate={rate}:duration=2',
                    '-c:v','libx264','-c:a','aac','-shortest',str(path)],check=True)
            target=root/'combined.mp4';concatenate_spoken_segments(files,target)
            probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries',
                'stream=codec_type,duration,sample_rate','-of','json',str(target)]))
            streams={s['codec_type']:s for s in probe['streams']}
            self.assertEqual(streams['audio']['sample_rate'],'48000')
            self.assertLess(abs(float(streams['video']['duration'])-float(streams['audio']['duration'])),.1)
            self.assertAlmostEqual(float(streams['audio']['duration']),4,delta=.15)

    def test_full_bank_deduplicates_shared_prefix_and_controlled_ending(self):
        nodes = public_nodes(self.items)
        self.assertEqual(len(nodes), 150)
        self.assertEqual({n['location'] for n in nodes}, {'t1', 't2', 'ending'})
        for node in nodes:
            if node['location'] == 'ending':
                self.assertEqual(len(node['bindings']), 2)
                for binding in node['bindings']:
                    self.assertEqual(binding['evidence_ids'], ['ending'])
            elif node['location'] == 't1':
                self.assertEqual(len(node['bindings']), 6)
                for binding in node['bindings']:
                    if '-T2-' in binding['instance_id']:
                        self.assertEqual(binding['evidence_ids'], ['A:t1', 'B:t1'])
        original = next(i for i in self.items if i['task'] == 'T2')
        ending = next(n for n in nodes if n['scenario_id'] == original['story_id'] and n['location'] == 'ending')
        self.assertEqual(ending['source_public_response'], original['input']['shared_ending']['current_response'])

    def test_all_profiles_require_english_prompts(self):
        request = {'profile': PROFILE, 'prompt': 'Speak exactly: 我会先核对资料。',
                   'duration_seconds': 5, 'generate_audio': True}
        with self.assertRaisesRegex(ValueError, 'entirely English'):
            seedance_payload(request)
        del request['profile']
        with self.assertRaisesRegex(ValueError, 'entirely English'):
            seedance_payload(request)
        request.update(profile='offline_english_preview_v1', prompt='Say exactly: I will check the details first.')
        self.assertEqual(seedance_payload(request)['content'][0]['text'], request['prompt'])

    def test_english_preview_retains_original_bindings_and_blocks_publication(self):
        from tempfile import TemporaryDirectory
        from offline import english_preview
        from offline.talking_head import ROOT
        original = (BANK / 'items.jsonl').read_bytes()
        with TemporaryDirectory(dir=ROOT / 'data') as directory:
            path = Path(directory) / 'manifest.json'
            manifest = english_preview.prepare(output=Path(directory))
            self.assertEqual(manifest['node_count'], 7)
            source_nodes = {n['node_id']: n for n in public_nodes(self.items)}
            for node in manifest['nodes']:
                source = source_nodes[node['source_node_id']]
                self.assertEqual(node['bindings'], source['bindings'])
                self.assertEqual(node['source_public_response'], source['source_public_response'])
                self.assertEqual(node['spoken_text'], node['localization']['text'])
                self.assertEqual(node['speech_language'], 'en')
                self.assertIsNone(node['continuity_reference'])
            with self.assertRaisesRegex(ValueError, 'preview-only'):
                publish(path)
            self.assertEqual((BANK / 'items.jsonl').read_bytes(), original)

    def test_english_preview_rejects_stale_translation_source(self):
        from tempfile import TemporaryDirectory
        from offline import english_preview
        from offline.talking_head import ROOT
        with TemporaryDirectory(dir=ROOT / 'data') as directory:
            config = json.loads(english_preview.CONFIG.read_text())
            config['translations'][0]['source_text'] += 'Changed'
            path = Path(directory) / 'translations.json'
            path.write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError, 'different public source line'):
                english_preview.prepare(path, output=Path(directory) / 'preview')

    def test_source_words_change_node_identity_and_do_not_touch_answers(self):
        item = deepcopy(self.items[0])
        before = deepcopy(item)
        nodes = public_nodes([item])
        self.assertEqual(item, before)
        item['input']['history'][0]['environment_character'] += ' Please wait.'
        changed = public_nodes([item])
        self.assertNotEqual(nodes[0]['node_id'], changed[0]['node_id'])
        self.assertEqual(nodes[1]['node_id'], changed[1]['node_id'])

    def test_boundary_trim_retains_voiced_interior_and_original_file(self):
        import shutil
        import subprocess
        from tempfile import TemporaryDirectory
        from offline.choice_builder import sha
        from scripts.finalize_multimodal_video_queue import probe
        if not shutil.which('ffmpeg'):
            self.skipTest('ffmpeg required')
        with TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / 'source.mp4'
            subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                '-f', 'lavfi', '-i', 'color=c=gray:s=160x90:r=10:d=6',
                '-f', 'lavfi', '-i', 'aevalsrc=if(between(t\\,1.5\\,3.5)\\,0.2*sin(2*PI*440*t)\\,0):s=32000:d=6',
                '-c:v', 'libx264', '-threads', '1', '-c:a', 'aac', '-shortest', str(original)],
                check=True, timeout=30)
            before = sha(original)
            target, edit = trim_boundary_silence(original, probe(original), root / 'trimmed')
            self.assertNotEqual(target, original)
            self.assertEqual(sha(original), before)
            self.assertLess(edit['start_seconds'], 1.5)
            self.assertGreater(edit['end_seconds'], 3.5)
            self.assertLess(probe(target)['duration_seconds_actual'], 4)
            self.assertEqual(trim_boundary_silence(original, probe(original), root / 'trimmed'), (target, edit))

    def test_incomplete_generation_cannot_replace_existing_media(self):
        from tempfile import TemporaryDirectory
        from offline.choice_builder import save
        with TemporaryDirectory() as directory:
            manifest = Path(directory) / 'manifest.json'
            save(manifest, {'node_count': 150})
            with patch('offline.talking_head.current_bank', return_value=BANK), \
                 patch('offline.talking_head.finalize', return_value={'assembled_nodes': 0}):
                before = (BANK / 'media.json').read_bytes()
                with self.assertRaisesRegex(ValueError, 'generation incomplete'):
                    publish(manifest)
                self.assertEqual((BANK / 'media.json').read_bytes(), before)

    def test_relative_manifest_assembles_multiple_trimmed_segments(self):
        import shutil
        import subprocess
        from tempfile import TemporaryDirectory
        from offline.choice_builder import save, sha, load
        from offline.talking_head import finalize
        if not shutil.which('ffmpeg'):
            self.skipTest('ffmpeg required')
        with TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            (root / 'bank').mkdir()
            source = root / 'source.mp4'
            subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                '-f', 'lavfi', '-i', 'color=c=gray:s=1280x720:r=5:d=4',
                '-f', 'lavfi', '-i', 'aevalsrc=if(lt(t\\,2)\\,0.2*sin(2*PI*440*t)\\,0):s=32000:d=4',
                '-c:v', 'libx264', '-preset', 'ultrafast', '-threads', '1', '-c:a', 'aac', '-shortest', str(source)],
                check=True, timeout=30)
            records = [{'request_id': 's1', 'video_file': 'source.mp4', 'source_public_response': 'hello '},
                       {'request_id': 's2', 'video_file': 'source2.mp4', 'source_public_response': 'world'}]
            shutil.copyfile(source, root / 'source2.mp4')
            for record in records:
                save(root / 'provider_states' / (record['request_id'] + '.json'),
                     {'status': 'downloaded', 'video_sha256': sha(source)})
            save(root / 'manifest.json', {'requests': records,
                'provider': {'model': 'fixture', 'resolution': '720p'},
                'nodes': [{'node_id': 'joined', 'segment_request_ids': ['s1', 's2'],
                           'source_public_response': 'hello world', 'bindings': []}]})
            with patch('offline.talking_head.ROOT', root), \
                 patch('offline.talking_head.current_bank', return_value=root / 'bank'), \
                 patch('offline.talking_head.progress', return_value={}), \
                 patch('scripts.run_multimodal_video_queue.ensure_state'):
                result = finalize(root.relative_to(Path.cwd()) / 'manifest.json')
            self.assertEqual(result['assembled_nodes'], 1)
            asset = load(root / 'completed_nodes.json')[0]['asset']
            self.assertEqual(asset['spoken_text'], 'hello world')
            self.assertLess(asset['structural_metadata']['duration_seconds_actual'], 7)
            self.assertGreater(asset['structural_metadata']['duration_seconds_actual'], 4)
            self.assertTrue(Path(asset['path']).is_absolute())

    def test_generation_bootstraps_one_identity_before_its_other_segments(self):
        from tempfile import TemporaryDirectory
        from offline.choice_builder import load, save, sha
        with TemporaryDirectory() as directory:
            root = Path(directory)
            records = [{'request_id': name, 'scenario_id': 'scene',
                        'request_file': 'requests/' + name + '.json',
                        'video_file': 'segments/' + name + '.mp4'} for name in ('anchor', 'dependent')]
            for record in records:
                save(root / record['request_file'], {'reference_video_file': None})
            manifest_path = root / 'manifest.json'
            save(manifest_path, {'requests': records, 'missing_reference_scenes': ['scene'],
                'provider': {'model': 'fixture', 'resolution': '720p'},
                'nodes': [{'scenario_id': 'scene', 'continuity_reference': None}]})
            calls = []
            def fake_run(batch, record, **kwargs):
                calls.append(record['request_id'])
                request = load(root / record['request_file'])
                if record['request_id'] == 'dependent':
                    self.assertEqual(request['reference_video_file'], 'segments/anchor.mp4')
                target = root / record['video_file']
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(b'fixture')
                return {'request_id': record['request_id'], 'status': 'downloaded'}
            with patch('offline.talking_head.ROOT', root), \
                 patch('offline.talking_head.current_bank', return_value=BANK), \
                 patch('offline.talking_head.progress'), \
                 patch('offline.talking_head.finalize', return_value={'assembled_nodes': 1}), \
                 patch('scripts.run_multimodal_video_queue.run_record', side_effect=fake_run):
                with self.assertRaisesRegex(ValueError, 'selection must include'):
                    generate(manifest_path, submit_new=True, request_ids=['dependent'])
                self.assertEqual(calls, [])
                self.assertEqual(generate(manifest_path, submit_new=True), {'assembled_nodes': 1})
            self.assertEqual(calls, ['anchor', 'dependent'])
            self.assertEqual(load(manifest_path)['nodes'][0]['continuity_reference']['sha256'], sha(root/'segments/anchor.mp4'))

    def test_provider_policy_failure_stops_further_requests_in_same_scene(self):
        from tempfile import TemporaryDirectory
        from offline.choice_builder import save
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / 'manifest.json'
            records = [{'request_id': rid, 'scenario_id': scene} for rid, scene in
                       [('blocked-1', 'a'), ('blocked-2', 'a'), ('safe-1', 'b')]]
            save(manifest, {'requests': records, 'missing_reference_scenes': [],
                            'provider': {'model': 'fixture', 'resolution': '720p'}, 'nodes': []})
            calls = []
            def fake_run(batch, record, **kwargs):
                calls.append(record['request_id'])
                return {'status': 'error', 'error': {'message': 'OutputVideoSensitiveContentDetected.PolicyViolation'}} if record['scenario_id'] == 'a' else {'status': 'downloaded'}
            with patch('offline.talking_head.current_bank', return_value=BANK), \
                 patch('offline.talking_head.finalize', return_value={}), \
                 patch('scripts.run_multimodal_video_queue.run_record', side_effect=fake_run):
                generate(manifest, submit_new=True, workers=1)
            self.assertEqual(calls, ['blocked-1', 'safe-1'])


if __name__ == '__main__':
    unittest.main()
