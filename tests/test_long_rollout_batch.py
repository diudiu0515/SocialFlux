import unittest

from scripts.generate_long_rollout_pool import (
    QUALITY_VERSION,
    TARGET_TURNS,
    _attempt_offset,
    _candidate_classification,
    _new_progress,
    _update_quality_summary,
    planned_slots,
)
from rollout.configuration import load_rollout_config
from pipeline.scenarios import load_scenario_records


class LongRolloutBatchTest(unittest.TestCase):
    def test_formal_plan_has_one_natural_horizon_claude_slot_per_scenario(self):
        config = load_rollout_config("configs/formal_rollout_pool.json")
        records = load_scenario_records("configs/scenarios")
        slots = planned_slots(records, config)
        self.assertEqual(config["pilot_limits"]["rollout_turns"], TARGET_TURNS)
        self.assertEqual(len(slots), 20)
        self.assertEqual(len({item["slot_id"] for item in slots}), 20)
        self.assertEqual({item["spec"]["model_family"] for item in slots}, {"claude"})
        environment_model = config["environment"]["provider"]["model"]
        self.assertTrue(all(
            item["spec"]["provider"]["model"] == environment_model
            for item in slots
        ))
        self.assertEqual(
            {item["scenario_id"] for item in slots},
            {scenario["scenario_id"] for _, scenario in records},
        )

    def test_progress_records_quality_version_attempt_offset_and_rate(self):
        config_path = "configs/formal_rollout_pool.json"
        config = load_rollout_config(config_path)
        progress = _new_progress(
            config_path,
            "build/example",
            [],
            config,
        )
        self.assertEqual(progress["quality_version"], QUALITY_VERSION)
        self.assertEqual(
            progress["model_routes_sha256"],
            (config.get("model_routes_provenance") or {}).get("sha256"),
        )
        progress["attempts"] = [
            {"slot_id": "s", "attempt": 2, "status": "generation_error", "error": "x"},
            {
                "slot_id": "s",
                "attempt": 4,
                "status": "accepted",
                "provider_run_metrics": {
                    "totals": {
                        "request_duration_seconds": 12.5,
                        "failed_request_count": 1,
                        "usage": {"input_tokens": 100, "output_tokens": 20},
                    }
                },
            },
        ]
        passing = {"structure": True, "ending": True}
        self.assertEqual(
            _candidate_classification(14, {"reason": "natural_completion"}, passing),
            "main_candidate",
        )
        self.assertEqual(
            _candidate_classification(8, {"reason": "natural_completion"}, passing),
            "short_natural_trajectory",
        )
        self.assertEqual(
            _candidate_classification(20, {"reason": "max_turns"}, {"ending": False}),
            "budget_truncated",
        )

        self.assertEqual(_attempt_offset(progress, "s"), 4)
        _update_quality_summary(progress)
        self.assertEqual(progress["quality_summary"]["attempt_count"], 2)
        self.assertEqual(progress["quality_summary"]["attempt_pass_rate"], 0.5)
        self.assertEqual(progress["quality_summary"]["residual_reasons"], {"x": 1})
        self.assertEqual(progress["quality_summary"]["provider_failed_requests"], 1)
        self.assertEqual(
            progress["quality_summary"]["provider_usage"],
            {"input_tokens": 100, "output_tokens": 20},
        )


if __name__ == "__main__":
    unittest.main()
