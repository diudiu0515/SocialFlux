import copy
import unittest

from pipeline.constants import ACTIVE_MODEL
from pipeline.flow import PIPELINE_STAGES, PipelinePreflight
from pipeline.runtime import assert_fable_rollout_config
from rollout.configuration import load_rollout_config
from scripts.build_scale300_v1 import build_design_matrix, load_catalog


class CanonicalPipelineTest(unittest.TestCase):
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

    def test_scale300_preflight_has_exact_stage_order_and_slot_count(self):
        result = PipelinePreflight().run()
        self.assertEqual(result["scenario_count"], 300)
        self.assertEqual(result["rollout_slots"], 900)
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
