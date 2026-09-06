from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from scripts.run_history_dependence import (
    _interpret_without_response,
    provider_specs,
    resumable_records,
    resolve_policy_spec,
    write_records,
)


def _config():
    return {
        "policies": [
            {
                "policy_id": "qwen_seed",
                "model_family": "qwen",
                "provider": {"provider": "fake"},
                "sampling": {"seed": 10},
                "runs": 2,
            },
            {
                "policy_id": "qwen_other",
                "model_family": "qwen",
                "provider": {"provider": "fake"},
                "sampling": {"seed": 20},
            },
        ]
    }


class HistoryDependenceTests(unittest.TestCase):
    def test_interpretation_probe_skips_response_generation(self):
        environment = Mock()
        environment.session = {
            "state": {"emotion": {"anger": 4}},
            "dynamics": {"escalation_risk": 3},
            "history": [],
        }
        environment.memory.retrieve.return_value = {
            "events": [],
            "summary": "",
            "relevant_turn_ids": [],
        }
        environment.state_updater.update.return_value = {
            "appraisal": {"intent": "clarify"},
            "evidence_turn_ids": [],
            "state_delta": {"emotion": {"anger": "similar"}},
            "interaction_dynamics_delta": {"escalation_risk": "similar"},
        }
        result = _interpret_without_response(environment, {"text": "请说明依据。"})
        self.assertEqual(result["numeric_state_delta"], {"emotion": {"anger": 0}})
        self.assertEqual(result["numeric_dynamics_delta"], {"escalation_risk": 0})
        environment.response_generator.generate.assert_not_called()

    def test_history_records_round_trip_for_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            records = [{"trajectory_id": "trajectory-a", "passed": True}]
            write_records(path, records)
            self.assertEqual(resumable_records(path, True), records)
            self.assertEqual(resumable_records(path, False), [])

    def test_provider_specs_expand_run_ids_and_seeds(self):
        specs = provider_specs(_config())
        self.assertEqual(sorted(specs), ["qwen_other", "qwen_seed__run_1", "qwen_seed__run_2"])
        self.assertEqual(specs["qwen_seed__run_1"]["sampling"]["seed"], 10)
        self.assertEqual(specs["qwen_seed__run_2"]["sampling"]["seed"], 11)

    def test_resolve_policy_spec_prefers_exact_policy_over_ambiguous_family(self):
        specs = provider_specs(_config())
        policy_id, spec = resolve_policy_spec(
            {
                "trajectory_id": "trajectory-1",
                "policy_id": "qwen_other",
                "policy_provenance": {"model_family": "qwen"},
            },
            specs,
        )
        self.assertEqual(policy_id, "qwen_other")
        self.assertEqual(spec["sampling"]["seed"], 20)

    def test_resolve_policy_spec_rejects_ambiguous_family_fallback(self):
        specs = provider_specs(_config())
        with self.assertRaisesRegex(ValueError, "family_matches=3"):
            resolve_policy_spec(
                {
                    "trajectory_id": "trajectory-2",
                    "policy_id": "missing",
                    "policy_provenance": {"model_family": "qwen"},
                },
                specs,
            )
