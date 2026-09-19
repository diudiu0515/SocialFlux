import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline.constants import ACTIVE_MODEL, ROLLOUTS_PER_SCENARIO
from pipeline.flow import PIPELINE_STAGES, PipelinePreflight
from pipeline.runtime import (
    assert_development_role_partitioned_rollout_config,
    assert_fable_rollout_config,
    assert_single_model_rollout_config,
)
from providers.model_routes import ModelRoutes
from rollout.configuration import load_rollout_config, public_rollout_config
from scripts.generate_long_rollout_pool import run_slot


class CanonicalPipelineTest(unittest.TestCase):
    def test_consumed_single_first_pass_cannot_create_replacement(self):
        config = load_rollout_config(
            "configs/gpt50_experiment/rollout.hybrid.single.json"
        )
        slot = {
            "config": config,
            "scenario_directory": "scenario_001",
        }
        with TemporaryDirectory() as directory:
            trajectory, attempts = run_slot(
                slot, {}, Path(directory), retry_limit=1, attempt_offset=1
            )
        self.assertIsNone(trajectory)
        self.assertEqual(attempts, [])

    def test_gpt_policy_claude_environment_partition_is_explicit(self):
        config = load_rollout_config(
            "configs/gpt50_experiment/rollout.hybrid.single.json"
        )
        assert_development_role_partitioned_rollout_config(config)
        self.assertEqual(
            config["policies"][0]["provider"]["model"], "gpt-6-astra"
        )
        self.assertEqual(
            config["environment"]["provider"]["model"], "claude-fable-5"
        )
        self.assertEqual(
            public_rollout_config(config)["development_role_assignment"],
            config["development_role_assignment"],
        )

    def test_gpt_authoring_uses_autodl_streaming_chat_completions(self):
        routes = ModelRoutes.load(
            "configs/gpt50_experiment/model_routes.astra.json"
        )
        route = routes.provider_config("scenario_authoring")
        self.assertEqual(
            route["endpoint"],
            "https://www.autodl.art/api/v1/chat/completions",
        )
        self.assertTrue(route["stream"])
        self.assertEqual(route["model"], "gpt-6-astra")

    def test_experimental_single_model_accepts_exactly_one_seed(self):
        config = load_rollout_config(
            "configs/gpt50_experiment/rollout.single.json"
        )
        assert_single_model_rollout_config(
            config,
            expected_model="gpt-6-astra",
            expected_seed_slots=1,
            context="test",
        )

    def test_archived_scale300_catalog_is_not_active(self):
        self.assertFalse(Path("configs/scale300_v1/scenarios").exists())
        self.assertTrue(Path("configs/scale300_v1/CLAUDE_AUTHORING.md").is_file())
        self.assertEqual(ROLLOUTS_PER_SCENARIO, 1)

    def test_preflight_blocks_when_no_active_catalog_is_promoted(self):
        with self.assertRaisesRegex(ValueError, "no scenarios found"):
            PipelinePreflight().run()
        self.assertEqual(
            [stage.value for stage in PIPELINE_STAGES],
            ["gate1", "rollout", "gate2", "gate3", "tasks", "t4", "gate4"],
        )

    def test_active_runtime_rejects_non_fable_or_environment_override(self):
        config = load_rollout_config("configs/formal_rollout_pool.json")
        assert_fable_rollout_config(config)

        wrong_model = copy.deepcopy(config)
        wrong_model["policies"][0]["provider"]["model"] = "another-model"
        with self.assertRaises(ValueError):
            assert_fable_rollout_config(wrong_model)

        overridden_environment = copy.deepcopy(config)
        overridden_environment["policies"][0]["environment_provider_override"] = {
            "model": ACTIVE_MODEL
        }
        with self.assertRaises(ValueError):
            assert_fable_rollout_config(overridden_environment)


if __name__ == "__main__":
    unittest.main()
