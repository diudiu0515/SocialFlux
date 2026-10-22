import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import scripts.complete_gpt50_videos as completion
from evaluation.t4_asset_coverage import audit_asset_coverage

from scripts.complete_gpt50_videos import publish_complete_scenarios


class VideoPublicationTest(unittest.TestCase):
    def test_partial_or_hash_mismatched_bundle_never_replaces_current_identity(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            current = {'requests': [
                {'request_id': 's-a', 'scenario_id': 's', 'video_file': 'old.mp4', 'status': 'generated_structural_pass'},
                {'request_id': 's-b', 'scenario_id': 's', 'video_file': 'missing.mp4', 'status': 'request_ready'}]}
            (base / 'old.mp4').write_bytes(b'old identity')
            manifest = base / 'manifest.json'
            manifest.write_text(json.dumps(current))
            bundle = {'requests': []}
            for key in ['a', 'b']:
                data = ('new identity ' + key).encode()
                bundle['requests'].append({'request_id': 's-' + key, 'scenario_id': 's', 'event_family': key,
                    'video_file': key + '.mp4', 'video_sha256': hashlib.sha256(data).hexdigest(),
                    'status': 'generated_structural_pass'})
                if key == 'a': (base / (key + '.mp4')).write_bytes(data)
            self.assertEqual(publish_complete_scenarios(bundle, base, manifest), [])
            self.assertEqual(json.loads(manifest.read_text()), current)
            (base / 'b.mp4').write_bytes(b'wrong bytes')
            self.assertEqual(publish_complete_scenarios(bundle, base, manifest), [])
            self.assertEqual(json.loads(manifest.read_text()), current)
            (base / 'b.mp4').write_bytes(b'new identity b')
            identity = {'identity_id': 's:approved_replacement', 'appearance': 'original adult'}
            for r in bundle['requests']:
                r['request_file'] = r['request_id'] + '.json'
                (base / r['request_file']).write_text(json.dumps({'identity': identity}))
            identities = base / 'identities.json'
            identities.write_text(json.dumps({'identities': {'s': {'identity_id': 'old'}}}))
            self.assertEqual(publish_complete_scenarios(bundle, base, manifest, identities), ['s'])
            self.assertEqual(json.loads(identities.read_text())['identities']['s'], identity)
            self.assertEqual(len(json.loads(identities.read_text())['revision_history']), 1)
            published = json.loads(manifest.read_text())
            self.assertEqual(published['requests'], bundle['requests'])
            self.assertEqual(published['generated_count'], 2)
            self.assertEqual((base / 'old.mp4').read_bytes(), b'old identity')
            publish_complete_scenarios(bundle, base, manifest, identities, base / 'public_assets')
            published = json.loads(manifest.read_text())
            for row in published['requests']:
                target = base / row['video_file']
                self.assertEqual(target.parent, base / 'public_assets')
                self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), row['video_sha256'])
                self.assertIn('generation_video_file', row)
            self.assertEqual(len(json.loads(identities.read_text())['revision_history']), 1)


    def test_last_anchor_completion_rescans_dependents_before_stopping(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'requests').mkdir()
            (base / 'assets').mkdir()
            records = []
            for index, family in enumerate(['anchor', 'dependent']):
                request = {'prompt': 'A fictional adult in a plain room.', 'duration_seconds': 4,
                           'generate_audio': True, 'ratio': '16:9',
                           'reference_video_file': 'assets/anchor.mp4' if index else None}
                (base / 'requests' / (family + '.json')).write_text(json.dumps(request))
                records.append({'request_id': family, 'scenario_id': 's', 'event_family': family,
                    'dependency_phase': index, 'request_file': 'requests/' + family + '.json',
                    'video_file': 'assets/' + family + '.mp4', 'status': 'request_ready'})
            manifest = base / 'manifest.json'
            manifest.write_text(json.dumps({'requests': records}))
            config = {'batch_root': str(base), 'manifest': str(manifest), 'model': 'doubao-seedance-2-0-260128',
                      'replacement_scenarios': [], 'workers': 2, 'max_generation_attempts': 2,
                      'maximum_wait_hours': 0, 'pilot_scenarios': ['s'], 'reference_policy': 'fresh_provider',
                      'reference_urls': str(base / 'urls.json'), 'key_file': str(base / 'unused_key')}
            config_path = base / 'config.json'
            config_path.write_text(json.dumps(config))
            calls = []
            def generate(args):
                calls.append(args.output.name)
                args.output.write_bytes(b'generated video fixture')
            with patch('sys.argv', ['complete', '--config', str(config_path), '--output', str(base / 'run')]), \
                 patch.object(completion, 'generate', generate), \
                 patch.object(completion, 'check_video', return_value={}), \
                 patch.object(completion, 'provider_reference_url', return_value='https://example.test/anchor.mp4'), \
                 patch.object(completion, 'audit_asset_coverage', side_effect=lambda d, b: audit_asset_coverage(d, b, expected_scenarios=1)):
                completion.main()
            self.assertEqual(calls, ['anchor.mp4', 'dependent.mp4'])
            self.assertTrue(json.loads((base / 'run' / 'coverage.json').read_text())['generation_complete'])


if __name__ == '__main__':
    unittest.main()
