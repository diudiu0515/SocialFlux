import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline.constants import ACTIVE_MODEL
from pipeline.flow import PIPELINE_STAGES, PipelinePreflight
from pipeline.runtime import (
    assert_development_role_partitioned_rollout_config,
    assert_fable_rollout_config,
    assert_single_model_rollout_config,
)
from rollout.configuration import load_rollout_config, public_rollout_config
from scripts.generate_long_rollout_pool import run_slot
from scripts.build_scale300_v1 import build_design_matrix, load_catalog


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

    def test_scale300_catalog_is_direct_and_has_no_parent_catalog(self):
        records = load_catalog("configs/scale300_v1/scenarios")
        matrix = build_design_matrix(records)

        self.assertEqual(len(records), 300)
        self.assertEqual(matrix["scenario_count"], 300)
        self.assertEqual(
            matrix["construction"],
            "direct_claude_authoring_no_parent_catalog",
        )
        self.assertNotIn("parent", matrix)

    def test_scale300_preflight_has_exact_stage_order_and_single_slot(self):
        result = PipelinePreflight().run()
        self.assertEqual(result["scenario_count"], 300)
        self.assertEqual(result["rollout_slots"], 300)
        self.assertEqual(result["stages"], [stage.value for stage in PIPELINE_STAGES])
        self.assertEqual(result["model"], ACTIVE_MODEL)
        self.assertEqual(result["t4_model"], ACTIVE_MODEL)

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
