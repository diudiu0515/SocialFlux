import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from providers.factory import build_provider
from providers.model_routes import ModelRoutes
from evaluation.review_configuration import load_review_config
from evaluation.t4_configuration import load_t4_config


class ModelRoutesTest(unittest.TestCase):
    def test_loads_board_specific_routes_without_inline_secrets(self):
        routes = ModelRoutes.load("configs/model_routes.frontier_api.json")
        expected = [
            "scenario_authoring", "scenario_normalization", "scenario_initialization",
            "policy", "appraisal", "response", "t2_branch_authoring",
            "t2_spec_authoring",
            "t2_pair_review", "t2_answer", "t2_answer_review",
            "task_extraction", "t1_answer", "t3_action_authoring",
            "t3_answer", "t4_judge", "quality_review",
        ]
        routes.require(expected)
        for route in expected:
            config = routes.provider_config(route)
            self.assertEqual(
                config["endpoint"],
                "https://www.autodl.art/api/v1/anthropic/v1/messages",
            )
            self.assertEqual(config["provider"], "anthropic")
            self.assertEqual(config["auth_scheme"], "bearer")
            self.assertEqual(config["api_key_env"], "AUTODL_API_KEY")
            self.assertFalse(config["stream"])
            self.assertFalse(config["use_proxy"])
        for route in expected:
            self.assertEqual(routes.provider_config(route)["model"], "claude-fable-5")
        for removed in ("task_construction", "task_answer", "semantic_judge"):
            with self.assertRaisesRegex(ValueError, "unknown model route"):
                routes.provider_config(removed)
        self.assertEqual(len(routes.sha256), 64)

    def test_route_copy_cannot_mutate_owner(self):
        routes = ModelRoutes.load("configs/model_routes.frontier_api.json")
        first = routes.provider_config("policy")
        first["model"] = "changed"
        self.assertEqual(routes.provider_config("policy")["model"], "claude-fable-5")

    def test_t4_uses_separate_claude_appraisal_and_response_bindings(self):
        config = load_t4_config("configs/t4_evaluation.json")
        self.assertEqual(config["model_assignment"]["model"], "claude-fable-5")
        self.assertIsNot(
            config["environment"]["provider"],
            config["environment"]["response_provider"],
        )
        self.assertEqual(
            config["model_routes_provenance"]["bindings"],
            {
                "evaluated_model.policy": "policy",
                "environment.appraisal": "appraisal",
                "environment.response": "response",
                "judge.t4": "t4_judge",
            },
        )

    def test_review_profiles_are_all_claude_and_seeded_independently(self):
        config = load_review_config("configs/review_models.json")
        profiles = config["profiles"]
        self.assertEqual(
            {profile["provider"]["model"] for profile in profiles.values()},
            {"claude-fable-5"},
        )
        self.assertNotEqual(
            profiles["rollout_primary"]["sampling"]["seed"],
            profiles["rollout_secondary"]["sampling"]["seed"],
        )

    def test_inline_secret_is_rejected(self):
        document = {
            "format": "socialflux_model_routes_v1",
            "routes": {
                "policy": {
                    "provider": "openai_compatible",
                    "endpoint": "https://example.invalid/v1/chat/completions",
                    "model": "model",
                    "api_key": "forbidden",
                }
            },
        }
        with self.assertRaisesRegex(ValueError, "inline secrets"):
            ModelRoutes(document)

    def test_inline_secret_in_shared_defaults_is_rejected(self):
        document = {
            "format": "socialflux_model_routes_v1",
            "provider_defaults": {"api_key": "forbidden"},
            "routes": {"policy": {"provider": "x", "endpoint": "x", "model": "x"}},
        }
        with self.assertRaisesRegex(ValueError, "secret reference"):
            ModelRoutes(document)

    def test_factory_resolves_endpoint_and_key_from_environment(self):
        config = {
            "provider": "openai_compatible",
            "endpoint_env": "SOCIALFLUX_TEST_ENDPOINT",
            "api_key_env": "SOCIALFLUX_TEST_KEY",
            "model": "model",
        }
        environment = {
            "SOCIALFLUX_TEST_ENDPOINT": "https://example.invalid/v1/chat/completions",
            "SOCIALFLUX_TEST_KEY": "test-only",
        }
        with patch.dict(os.environ, environment, clear=False):
            provider = build_provider(config)
        self.assertEqual(provider.endpoint, environment["SOCIALFLUX_TEST_ENDPOINT"])
        self.assertEqual(provider.api_key, "test-only")

    def test_factory_fails_before_network_when_endpoint_missing(self):
        config = {
            "provider": "openai_compatible",
            "endpoint_env": "SOCIALFLUX_MISSING_ENDPOINT",
            "model": "model",
        }
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "endpoint is not set"):
                build_provider(config)

    def test_factory_uses_private_file_when_environment_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            secret_path = Path(directory) / "api_key"
            secret_path.write_text("test-file-key\n", encoding="utf-8")
            config = {
                "provider": "openai_compatible",
                "endpoint": "https://example.invalid/v1/chat/completions",
                "api_key_env": "SOCIALFLUX_MISSING_KEY",
                "api_key_file": str(secret_path),
                "model": "model",
            }
            with patch.dict(os.environ, {}, clear=True):
                provider = build_provider(config)
            self.assertEqual(provider.api_key, "test-file-key")
            self.assertNotIn("api_key_file", provider.provenance)


if __name__ == "__main__":
    unittest.main()
