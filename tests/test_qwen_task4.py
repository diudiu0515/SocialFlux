from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from environment.calibration import FEATURE_NAMES
from environment.appraisal_context import build_appraisal_context
from environment.delta_mapper import flatten_state
from environment.independent_appraisal import _validate_judgments
from environment.qwen_task4 import (
    DEFAULT_CONFIG, QwenTask4EnvironmentFactory, QwenTask4Provider,
    load_config, load_prompt_profile, request_providers,
)
from environment.qwen_task4_contract import state_schema, response_schema, retry_feedback
from environment.qwen_task4_session import QwenTask4Session, SessionConflict
from environment.unified_appraisal import UnifiedEnvironmentFactory
from pipeline.runtime import build_environment_factory
from providers.local_vllm import LocalVLLMProvider

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "data/gpt50/experiment/scenario/scenarios_state_v3/scenario_003/scenario_003.json"


def no_evidence(variable):
    return {"variable": variable, "judgment": "no_relevant_evidence", "direction": None,
            "evidence_span": "", "directness": None, "evidence_feature": None,
            "rationale": "No new evidence for this construct."}


class QwenTask4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = json.loads(SCENARIO.read_text())

    def test_config_is_local_thinking_bounded_and_independent(self):
        config = load_config()
        prompts, manifest, sha = load_prompt_profile(config)
        self.assertEqual(set(prompts), {"state", "interaction", "response"})
        self.assertEqual(len(sha), 64)
        self.assertEqual(config["environment"]["minimum_natural_turns"], 1)
        env = QwenTask4EnvironmentFactory(self.scenario)()
        self.assertEqual(env.provenance["state_update"], "deterministic")
        self.assertEqual(env.provenance["qwen_task4_profile"], config["profile"])
        state = env.state_updater.state_appraiser.provider.provider
        self.assertIsInstance(state, QwenTask4Provider)
        self.assertIsInstance(env.response_generator.provider, QwenTask4Provider)
        self.assertEqual(env.state_updater.calibrator.profile, config["environment"]["state_calibration_profile"])
        plain = UnifiedEnvironmentFactory(build_environment_factory(self.scenario, config["environment"]))()
        self.assertNotIsInstance(plain.state_updater.state_appraiser.provider.provider, QwenTask4Provider)
        self.assertNotIn("qwen_task4_profile", plain.provenance)

    def test_reject_unbounded_thinking_before_requests(self):
        config = load_config()
        config["environment"]["state_appraisal_sampling"]["thinking_token_budget"] = 6000
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError, "final tokens"):
                load_config(path)

    def test_state_direction_feedback_reaches_the_existing_bounded_retry(self):
        env = QwenTask4EnvironmentFactory(self.scenario)()
        action = "I cannot guarantee that the request will be approved."
        good = {
            "event_features": {name: 0 for name in FEATURE_NAMES},
            "state_judgments": [no_evidence(p) for p in flatten_state(self.scenario["initial_state"])],
            "dynamics_judgments": [no_evidence(p) for p in flatten_state(self.scenario["initial_dynamics"])],
            "evidence_turn_ids": [],
        }
        judgment = good["state_judgments"][0]
        judgment.update(judgment="ordinary_new_evidence", direction="increase",
                        evidence_span=action, directness="direct")
        bad = deepcopy(good)
        bad["state_judgments"][0]["direction"] = "positive"
        calls = []

        def complete(provider, messages, **generation):
            calls.append(deepcopy(messages))
            return json.dumps(bad if len(calls) == 1 else good)

        with patch.object(LocalVLLMProvider, "complete", complete):
            result = env.state_updater.state_appraiser.appraise(
                action={"text": action}, previous_state=self.scenario["initial_state"],
                previous_dynamics=self.scenario["initial_dynamics"], memory={"relevant_turn_ids": []},
                appraisal_context=build_appraisal_context(history=[], turns=[], action={"text": action}, current_turn_id=1))
        self.assertEqual(len(calls), 2)
        self.assertIn("$.state_judgments[0].direction", calls[1][-1]["content"])
        self.assertIn("increase", calls[1][-1]["content"])
        self.assertIn("decrease", calls[1][-1]["content"])
        self.assertEqual(bad["state_judgments"][0]["direction"], "positive")
        self.assertEqual(len(result["request_retry_diagnostics"]), 1)
        self.assertIn("output", calls[0][0]["content"].lower())

    def test_schema_values_match_canonical_direction_acceptance(self):
        item = no_evidence("emotion.anxiety")
        item.update(judgment="ordinary_new_evidence", evidence_span="uncertain", directness="direct")
        for direction in ("increase", "decrease", "positive", "negative", None):
            item["direction"] = direction
            with self.subTest(direction=direction):
                if direction in {"increase", "decrease"}:
                    _validate_judgments([item], [item["variable"]], "uncertain", {}, {}, "state_judgments")
                else:
                    with self.assertRaises(ValueError):
                        _validate_judgments([item], [item["variable"]], "uncertain", {}, {}, "state_judgments")
        payload = {"state_variable_paths": [item["variable"]], "dynamics_variable_paths": [], "memory": {}}
        values = state_schema(payload)["properties"]["state_judgments"]["items"]["properties"]["direction"]["enum"]
        self.assertEqual(set(values), {None, "increase", "decrease"})

    def test_response_feedback_names_length_and_event_status(self):
        raw = {"response_text": "我不能确定结果。", "expression_intent": "a" * 161,
               "observable_behavior": {"facial_expression": "", "gaze": "", "speech_style": "",
                                       "prosody": "", "behavioral_cues": []},
               "ledger_events": [{"event_type": "claim", "owner": "environment_agent",
                                  "action_owner": "environment_agent", "evidence_span": "我不能确定结果",
                                  "status": "firm", "assertion_mode": "asserted"}],
               "reply_obligation": None, "consequential_claims": []}
        feedback = retry_feedback(json.dumps(raw), response_schema())
        self.assertIn("$.expression_intent", feedback)
        self.assertIn("$.ledger_events[0].status", feedback)
        self.assertIn("reported", feedback)

    def test_prompt_adapter_preserves_context_and_source_messages(self):
        env = QwenTask4EnvironmentFactory(self.scenario)()
        provider = env.state_updater.state_appraiser.provider.provider
        payload = {"state_variable_paths": ["emotion.anxiety"], "dynamics_variable_paths": [],
                   "action": {"text": "An exact action"}, "memory": {}}
        messages = [{"role": "system", "content": "original system"},
                    {"role": "user", "content": "original prompt\n## Input\n" + json.dumps(payload)}]
        original = deepcopy(messages)
        prepared = provider.prepare_messages(messages)
        self.assertEqual(messages, original)
        self.assertEqual(prepared[1], original[1])
        self.assertTrue(prepared[0]["content"].startswith(original[0]["content"]))

    def test_public_session_stale_turn_failure_and_private_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            session = QwenTask4Session(QwenTask4EnvironmentFactory(self.scenario), directory)
            result = session.result()
            self.assertIsNone(result["reward"])
            for key in ("state", "dynamics", "appraisal", "hidden_intention", "environment_provenance"):
                self.assertNotIn(key, result["observation"])
                self.assertNotIn(key, result)
            with self.assertRaises(SessionConflict):
                session.step("Hello", expected_turn_id=1)
            with patch.object(session.environment, "step", side_effect=ValueError("private diagnostic")) as step:
                failed = session.step("Hello", expected_turn_id=0)
                self.assertTrue(failed["failed"])
                self.assertFalse(failed["terminated"])
                self.assertFalse(failed["truncated"])
                self.assertNotIn("private diagnostic", json.dumps(failed))
                self.assertTrue((session.output / "failure.json").exists())
                with self.assertRaises(SessionConflict):
                    session.step("Hello", expected_turn_id=0)
                self.assertEqual(step.call_count, 1)

    def test_natural_and_budget_endings_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            session = QwenTask4Session(QwenTask4EnvironmentFactory(self.scenario), directory)
            for reason, terminated, truncated in [("natural_completion", True, False), ("max_turns", False, True)]:
                session.environment.session["ending"] = {"reason": reason, "turn_id": 20}
                result = session.result()
                self.assertEqual((result["terminated"], result["truncated"]), (terminated, truncated))


if __name__ == "__main__":
    unittest.main()
