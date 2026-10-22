import json
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from scripts.evaluate_environment_prompt import environment_config, summarize
from scripts.serve_qwen_local import command
from scripts.deploy_qwen_local import available_gpus
from scripts.install_qwen_runtime import compatible_wheel
from packaging.tags import Tag

ROOT = Path(__file__).resolve().parents[1]


class EnvironmentPromptDiagnosticTests(unittest.TestCase):
    def test_all_environment_stages_are_local_and_current_prompts_are_kept(self):
        deployment = json.loads((ROOT / 'configs/qwen_local_deployment.json').read_text())
        original = json.loads((ROOT / deployment['environment_source_config']).read_text())['environment']
        env = environment_config(deployment)
        for role in ('provider', 'state_appraisal_provider', 'interaction_appraisal_provider', 'response_provider'):
            self.assertEqual(env[role]['provider'], 'local_vllm')
            self.assertEqual(env[role]['model'], deployment['model'])
            self.assertNotIn('candidates', env[role])
        for key in ('state_appraisal_prompt_id', 'response_prompt_id', 'state_calibration_profile'):
            self.assertEqual(env[key], original[key])
        self.assertTrue(env['independent_appraisals'])
        self.assertNotEqual(original['provider']['provider'], 'local_vllm')

    def test_failures_remain_in_denominator_and_are_not_agreement(self):
        rows = [
            {'case_id': 'a', 'kind': 'neutral_control', 'status': 'completed', 'first_pass': True,
             'request_count': 3, 'seconds': 4, 'changed_state_variables': {}},
            {'case_id': 'b', 'kind': 'matched_checkpoint', 'status': 'failed', 'first_pass': False,
             'request_count': 3, 'seconds': 6},
        ]
        result = summarize(rows)
        self.assertEqual(result['completion_rate'], 0.5)
        self.assertEqual(result['failed'], 1)
        self.assertEqual(result['request_count'], 6)
        self.assertIsNone(result['source_model_active_direction_agreement'])
        self.assertFalse(result['human_correctness_measured'])

    def test_server_is_local_and_uses_explicit_model_identity(self):
        deployment = json.loads((ROOT / 'configs/qwen_local_deployment.json').read_text())
        args = command(deployment)
        self.assertEqual(args[args.index('--host') + 1], '127.0.0.1')
        self.assertEqual(args[args.index('--served-model-name') + 1], deployment['model'])

    def test_existing_gpu_workload_delays_start(self):
        config = {'tensor_parallel_size': 4, 'gpu_memory_utilization': 0.9}
        with patch('scripts.deploy_qwen_local.subprocess.run', return_value=SimpleNamespace(
                stdout='0, 30000, 49140\n1, 49139, 49140\n2, 49139, 49140\n3, 49139, 49140\n')):
            ready, cards = available_gpus(config)
        self.assertFalse(ready)
        self.assertEqual(len(cards), 4)
        with patch('scripts.deploy_qwen_local.subprocess.run', return_value=SimpleNamespace(
                stdout='0, 49139, 49140\n1, 49139, 49140\n2, 49139, 49140\n3, 49139, 49140\n')):
            self.assertTrue(available_gpus(config)[0])

    def test_wheel_selection_rejects_wrong_architecture_and_yanked_release(self):
        files = [
            {'filename': 'sample-1.0-py3-none-any.whl', 'packagetype': 'bdist_wheel', 'yanked': False},
            {'filename': 'sample-1.0-cp312-cp312-manylinux_2_28_x86_64.whl', 'packagetype': 'bdist_wheel', 'yanked': True},
            {'filename': 'sample-1.0-cp312-cp312-manylinux_2_28_aarch64.whl', 'packagetype': 'bdist_wheel', 'yanked': False},
        ]
        tags = [Tag('cp312', 'cp312', 'manylinux_2_28_x86_64'), Tag('py3', 'none', 'any')]
        self.assertEqual(compatible_wheel(files, tags)['filename'], files[0]['filename'])


if __name__ == '__main__':
    unittest.main()
