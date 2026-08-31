import unittest

from environment.prompts import build_appraisal_prompt
from prompts.loader import get_prompt, prompt_manifest, render_prompt


class PromptCatalogTest(unittest.TestCase):
    def test_manifest_entries_are_loadable(self):
        manifest = prompt_manifest()
        self.assertGreaterEqual(len(manifest["prompts"]), 12)
        for prompt_id in manifest["prompts"]:
            self.assertTrue(get_prompt(prompt_id).strip())

    def test_rendering_is_versioned_and_payload_bound(self):
        rendered = render_prompt("policy_action_v1", {"turn_id": 3})
        self.assertIn("policy_action_v1", prompt_manifest()["prompts"])
        self.assertIn('"turn_id": 3', rendered)

    def test_environment_prompt_uses_catalog(self):
        rendered = build_appraisal_prompt(
            persona={"name": "A"}, background="B", explicit_goal="G",
            hidden_intention="H", previous_state={}, previous_dynamics={},
            memory={}, action={"text": "hello"},
        )
        self.assertIn("hello", rendered)
        self.assertIn("strong_decrease", rendered)


if __name__ == "__main__":
    unittest.main()
