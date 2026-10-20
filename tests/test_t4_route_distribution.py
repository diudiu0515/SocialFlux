import unittest
from scripts.run_t4_multimodal_experiment import environment_for_episode


class RouteDistributionTest(unittest.TestCase):
    def test_routes_change_only_credentials_and_preserve_original(self):
        base = {key: {"model": "claude" if key == "response_provider" else "gpt",
                      "provider": "fixture", "api_key_env": "OLD", "api_key_file": "old",
                      "stream": True, "max_tokens": 6500}
                for key in ("provider", "state_appraisal_provider", "interaction_appraisal_provider", "response_provider")}
        config = {"environment_credential_routes": {
            "appraisal": [{"api_key_file": "a"}, {"api_key_file": "b"}, {"api_key_file": "c"}],
            "response": [{"api_key_file": "r1"}, {"api_key_file": "r2"}]}}
        result, slots = environment_for_episode(base, config, 4)
        self.assertEqual(slots, {"appraisal": 1, "response": 0})
        self.assertEqual(result['state_appraisal_provider']['api_key_file'], 'b')
        self.assertEqual(result['interaction_appraisal_provider']['api_key_file'], 'b')
        self.assertEqual(result['response_provider']['api_key_file'], 'r1')
        self.assertNotIn('api_key_env', result['provider'])
        self.assertEqual(base['provider']['api_key_env'], 'OLD')
        for key in base:
            for field in ['model', 'provider', 'stream', 'max_tokens']:
                self.assertEqual(result[key][field], base[key][field])
        self.assertEqual(environment_for_episode(base, config, 4), (result, slots))

    def test_route_cannot_silently_replace_model(self):
        with self.assertRaises(ValueError):
            environment_for_episode({}, {'environment_credential_routes': {
                'appraisal': [{'model': 'different'}]}}, 0)


if __name__ == '__main__':
    unittest.main()
