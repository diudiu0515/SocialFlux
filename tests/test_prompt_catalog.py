import json
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from environment.prompts import build_appraisal_prompt
from policies.model_policy import ModelPolicy
from prompts.loader import get_prompt, prompt_manifest, render_prompt
from scripts.update_prompt_manifest import build_manifest


class RecordingProvider:
    provenance = {"provider": "test-double", "model": "free-form-model"}

    def __init__(self, result="任意自然语言行动"):
        self.result = result
        self.calls = []

    def complete(self, messages, **generation):
        self.calls.append((messages, generation))
        return self.result


class PromptCatalogTest(unittest.TestCase):
    def test_manifest_entries_are_loadable(self):
        manifest = prompt_manifest()
        for prompt_id in manifest["prompts"]:
            self.assertTrue(get_prompt(prompt_id).strip())
        registered = {entry["path"] for entry in manifest["prompts"].values()}
        on_disk = {path.name for path in Path("prompts").glob("*.md")}
        self.assertEqual(registered, on_disk)

    def test_manifest_regeneration_supports_current_descriptive_versions(self):
        self.assertEqual(build_manifest(), prompt_manifest())

    def test_retired_templates_cannot_load_or_be_registered_again(self):
        retired = json.loads(Path("prompts/retired.json").read_text())["prompts"]
        for prompt_id, entry in retired.items():
            with self.subTest(prompt_id=prompt_id):
                self.assertNotIn(prompt_id, prompt_manifest()["prompts"])
                self.assertFalse((Path("prompts") / entry["path"]).exists())
                with self.assertRaisesRegex(KeyError, "retired prompt id"):
                    get_prompt(prompt_id)
        with self.assertRaisesRegex(KeyError, "unknown prompt id"):
            get_prompt("not_a_prompt")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prompt_id = next(iter(retired))
            (root / "retired.json").write_text(json.dumps({"prompts": retired}))
            (root / f"{prompt_id}.md").write_text("obsolete template")
            with patch("scripts.update_prompt_manifest.PROMPT_DIR", root):
                with self.assertRaisesRegex(ValueError, "retired prompt"):
                    build_manifest()

    def test_retired_environment_config_fails_before_provider_construction(self):
        from environment.factory import ModelEnvironmentFactory

        scenario = {"scenario_id": "prompt_preflight", "initial_state": {}}
        configurations = [
            {"appraisal_prompt_id": "environment_appraisal_v13"},
            {"response_prompt_id": "environment_response_v27"},
            {"independent_appraisals": True,
             "state_appraisal_prompt_id": "environment_state_appraisal_v5_immediate_context"},
        ]
        for configuration in configurations:
            with self.subTest(configuration=configuration):
                factory = ModelEnvironmentFactory(scenario, {}, **configuration)
                with patch("environment.factory.build_provider") as build_provider:
                    with self.assertRaisesRegex(KeyError, "retired prompt id"):
                        factory()
                    build_provider.assert_not_called()

    def test_prompt_schema_references_exist(self):
        for path in Path("prompts").glob("*.md"):
            text = path.read_text(encoding="utf-8")
            for schema_path in re.findall(r"schemas\/[A-Za-z0-9_.-]+\.json", text):
                self.assertTrue(Path(schema_path).exists(), f"{path} references missing {schema_path}")
        for path in Path("schemas").glob("*.json"):
            json.loads(path.read_text(encoding="utf-8"))

    def test_render_prompt_rejects_unresolved_placeholders(self):
        with self.assertRaisesRegex(ValueError, "unresolved placeholders"):
            render_prompt("task_rollout_action_v1", payload={})

    def test_model_policy_returns_text_only_and_passes_sampling(self):
        provider = RecordingProvider()
        policy = ModelPolicy(
            "model-a-seed-7",
            provider,
            sampling={"temperature": 0.8, "seed": 7},
        )
        action = policy.generate({"turn_id": 3})
        self.assertEqual(action, {"text": "任意自然语言行动"})
        self.assertEqual(provider.calls[0][1], {"temperature": 0.8, "seed": 7})
        rendered = next(item["content"] for item in provider.calls[0][0] if item["role"] == "user")
        self.assertIn("role_lock", rendered)
        self.assertIn("goal", rendered)
        self.assertIn("evaluated participant", rendered)
        self.assertIn('"turn_id": 3', rendered)

    def test_two_stage_scenario_prompts_replace_direct_json_generation(self):
        script_prompt = get_prompt("scenario_script_generation_v1")
        normalize_prompt = get_prompt("scenario_normalization_v1")
        initialize_prompt = get_prompt("initial_state_configuration_v1")
        self.assertIn("Do not mention JSON schema", script_prompt)
        self.assertIn("Do not produce initial numeric values", normalize_prompt)
        self.assertIn("scenario_blueprint.schema.json", normalize_prompt)
        self.assertNotIn("initial_state", normalize_prompt)
        self.assertIn("candidate initial state", initialize_prompt)

    def test_narrative_source_prompt_enforces_originality_and_variety(self):
        extraction = get_prompt("narrative_structure_extraction_v1")
        script = get_prompt("scenario_script_generation_v1")
        quality = get_prompt("scenario_quality_gate_v1")
        normalization = get_prompt("scenario_normalization_v1")
        initialization = get_prompt("initial_state_configuration_v1")
        self.assertIn("do not reproduce dialogue", extraction)
        self.assertIn("new setting, new characters, new events, new stakes", extraction)
        self.assertIn("narrative_structure.schema.json", extraction)
        self.assertIn("vary domain, relationship, temporal structure", script)
        self.assertIn("reject template artifacts", quality)
        self.assertIn("do not normalize every source into the same state set", normalization)
        self.assertIn("never copy a default state bundle or trigger pair", initialization)

    def test_environment_prompt_rejects_action_taxonomy(self):
        rendered = build_appraisal_prompt(
            persona={"name": "A"},
            background="B",
            explicit_goal="G",
            hidden_intention="H",
            previous_state={"emotion": {"anger": 2}},
            previous_dynamics={"negotiation_open": 5},
            memory={},
            action={"text": "我想核对事实。"},
        )
        self.assertIn("我想核对事实", rendered)
        self.assertIn("environment LLM call 1", rendered)
        self.assertIn("event_features", rendered)
        self.assertIn("sparse candidates", rendered)
        self.assertIn("state_impacts", rendered)
        self.assertIn("Do not write", rendered)
        self.assertIn("newly occurring act is new behavioral evidence", rendered)
        self.assertIn("condition on a commitment made now", rendered)
        self.assertIn("ledger_resolutions", rendered)
        self.assertIn("speaker_report", rendered)

        response = get_prompt("environment_response_v25")
        self.assertIn("environment LLM call 2", response)
        self.assertIn("consequential fact", response)

        rollout_judge = get_prompt("rollout_quality_judge_v2")
        self.assertIn("four top-level fields", rollout_judge)
        self.assertIn('"hard_reject_reasons":[]', rollout_judge)
        self.assertIn('"history_dependence":["t2"]', rollout_judge)
        self.assertIn("future_information_leakage", rollout_judge)

    def test_appraisal_v22_runs_slow_pass_before_relationship_cap(self):
        appraisal = get_prompt("environment_appraisal_v22_slow_first")
        self.assertIn("Slow pass first", appraisal)
        self.assertIn("reserve one of the two", appraisal)
        self.assertIn("If and only if", appraisal)
        self.assertIn("does not itself prove trust changed", appraisal)

    def test_response_v31_uses_grounded_contrast_not_invented_logistics(self):
        response = get_prompt("environment_response_v31_contrastive_event_driven")
        self.assertIn("one unresolved contrast shared", response)
        self.assertIn("Do not invent a room, resource, actor", response)
        self.assertIn("Do not list the two", response)
        self.assertIn("only when that boundary is already present", response)

    def test_appraisal_v36_is_complete_evidence_grounded_rewrite(self):
        appraisal = get_prompt(
            "environment_appraisal_v36_evidence_grounded_state_interpretation"
        )
        self.assertIn("Interpret the current act in context", appraisal)
        self.assertIn("Judge novelty and evidence strength separately", appraisal)
        self.assertIn("Weak but relevant evidence is different", appraisal)
        self.assertIn("Do not impose a one-candidate-per-family limit", appraisal)
        self.assertIn("More candidates do not imply more actual updates", appraisal)


if __name__ == "__main__":
    unittest.main()
