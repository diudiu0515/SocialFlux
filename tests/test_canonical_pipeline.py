import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline.constants import ACTIVE_MODEL, ROLLOUTS_PER_SCENARIO
from pipeline.flow import PIPELINE_STAGES, PipelinePreflight
from pipeline.runtime import (
    assert_development_role_partitioned_rollout_config,
    assert_fable_rollout_config,
)
from policies.model_policy import ModelPolicy
from providers.model_routes import ModelRoutes
from prompts.loader import get_prompt
from rollout.configuration import load_rollout_config, public_rollout_config
from scripts.generate_long_rollout_pool import run_slot


class CanonicalPipelineTest(unittest.TestCase):
    def test_consumed_single_first_pass_cannot_create_replacement(self):
        config = load_rollout_config(
            "configs/gpt50_experiment/rollout.json"
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
            "configs/gpt50_experiment/rollout.json"
        )
        assert_development_role_partitioned_rollout_config(config)
        self.assertEqual(
            config["policies"][0]["provider"]["model"], "gpt-6-astra"
        )
        self.assertEqual(
            config["environment"]["provider"]["model"], "claude-fable-5"
        )
        self.assertEqual(
            config["environment"]["response_provider"]["model"],
            "claude-fable-5",
        )
        self.assertEqual(
            public_rollout_config(config)["development_role_assignment"],
            config["development_role_assignment"],
        )

    def test_gpt_authoring_uses_autodl_chat_and_responses_failover(self):
        routes = ModelRoutes.load(
            "configs/gpt50_experiment/model_routes.astra.json"
        )
        route = routes.provider_config("scenario_authoring")
        self.assertEqual(route["provider"], "failover")
        self.assertEqual(
            {
                candidate["provider"]: candidate["endpoint"]
                for candidate in route["candidates"]
            },
            {
                "openai_compatible": (
                    "https://www.autodl.art/api/v1/chat/completions"
                ),
                "openai_responses": "https://www.autodl.art/api/v1/responses",
            },
        )
        self.assertFalse(route["stream"])
        self.assertEqual(route["model"], "gpt-6-astra")

    def test_gpt_rollout_uses_one_offline_policy_slot(self):
        config = load_rollout_config(
            "configs/gpt50_experiment/rollout.json"
        )
        assert_development_role_partitioned_rollout_config(config)
        self.assertEqual(len(config["policies"]), 1)
        self.assertEqual(config["policies"][0]["runs"], 1)
        self.assertEqual(
            config["policies"][0]["prompt_id"],
            "task_rollout_action_v1",
        )
        self.assertEqual(
            config["policies"][0]["minimum_natural_turns"], 10
        )
        self.assertEqual(
            config["environment"]["minimum_natural_turns"], 10
        )
        offline_prompt = get_prompt("task_rollout_action_v1")
        online_prompt = get_prompt("task_t4_action_v21")
        self.assertIn("turn 10", offline_prompt)
        self.assertIn("10–20 effective turns", offline_prompt)
        self.assertIn("one local matter is settled", offline_prompt)
        self.assertIn("timing window, resource", offline_prompt)
        self.assertIn("repeated contact promise", offline_prompt)
        self.assertIn("permits closure but does not require it", offline_prompt)
        self.assertIn("There is no minimum dialogue length", online_prompt)
        policy = ModelPolicy(
            "offline-test",
            None,
            prompt_id="task_rollout_action_v1",
            validation_profile="hard_only",
            minimum_natural_turns=10,
        )
        messages, _ = policy._build_request({
            "history": [],
            "current_response": "我们需要继续处理这个分歧。",
            "role": {
                "name": "甲",
                "role": "负责人",
                "explicit_goal": "达成可执行安排",
            },
            "target_character": {"name": "乙", "role": "协作者"},
            "conversation_progress": {},
        })
        self.assertEqual([item["role"] for item in messages], ["system", "user"])
        self.assertIn("turn 10", messages[1]["content"])
        self.assertIn(
            "before its minimum effective history depth",
            messages[1]["content"],
        )
        self.assertIn("one material advancement", messages[1]["content"])
        self.assertIn(
            "timing window, resource limit, authority boundary",
            messages[1]["content"],
        )
        self.assertIn("bare acknowledgment", messages[1]["content"])

        wrong_prompt = copy.deepcopy(config)
        wrong_prompt["policies"][0]["prompt_id"] = "task_t4_action_v21"
        wrong_prompt.pop("model_routes", None)
        wrong_prompt.pop("model_routes_provenance", None)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "wrong-prompt.json"
            path.write_text(
                json.dumps(wrong_prompt),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError, "minimum-depth offline rollout"
            ):
                load_rollout_config(path)

    def test_archived_scale300_catalog_is_not_active(self):
        self.assertFalse(Path("configs/scale300_v1").exists())
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
