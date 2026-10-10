import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.run_t4_multimodal_experiment import select_cohort, model_configs
from evaluation.t4_asset_coverage import audit_asset_coverage, require_complete_assets


class CohortTest(unittest.TestCase):
    def test_explicit_subset_excludes_other_media_but_keeps_all_selected_branches(self):
        scenarios = [{'scenario_id': x} for x in ['A', 'B']]
        inventory = {'requests': [
            {'scenario_id': 'A', 'event_family': 'anchor'},
            {'scenario_id': 'A', 'event_family': 'relief'},
            {'scenario_id': 'B', 'event_family': 'anchor'}]}
        chosen, media = select_cohort(scenarios, inventory, ['A'])
        self.assertEqual(chosen, scenarios[:1])
        self.assertEqual(len(media['requests']), 2)
        with TemporaryDirectory() as directory:
            Path(directory, 'anchor.mp4').write_bytes(b'anchor')
            for r in media['requests']:
                r.update(request_id=r['event_family'], video_file=r['event_family'] + '.mp4',
                         status='generated_structural_pass', video_sha256=hashlib.sha256(b'anchor').hexdigest())
            report = audit_asset_coverage(media, directory, expected_scenarios=1)
            with self.assertRaises(ValueError):
                require_complete_assets(report)

    def test_subset_rejects_empty_unknown_and_duplicate_ids(self):
        for ids in [[], ['unknown'], ['A', 'A']]:
            with self.assertRaises(ValueError):
                select_cohort([{'scenario_id': 'A'}], {'requests': []}, ids)

    def test_configurable_timeout_preserves_explicit_stream_setting(self):
        config = {'models': [{'id': 'gpt', 'routes': 'unused', 'overrides': {'stream': True}}],
                  'provider_timeout_seconds': 600}
        with patch('scripts.run_t4_multimodal_experiment.ModelRoutes.load') as load:
            load.return_value.provider_config.return_value = {'provider': 'openai_compatible', 'model': 'test', 'stream': False}
            route = model_configs(config)['gpt']
        self.assertEqual(route['timeout'], 600)
        self.assertTrue(route['stream'])
        self.assertEqual(route['max_transport_attempts'], 1)

    def test_default_scope_remains_fifty_scenarios(self):
        with self.assertRaises(ValueError):
            select_cohort([{'scenario_id': 'A'}], {'requests': []})


if __name__ == '__main__':
    unittest.main()
