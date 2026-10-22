import json
from pathlib import Path
import unittest

from scripts.evaluate_environment_prompt import environment_config, summarize
from scripts.serve_qwen_local import command

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


if __name__ == '__main__':
    unittest.main()
