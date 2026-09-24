import unittest
import json
from pathlib import Path
import tempfile

from scripts.generate_long_rollout_pool import (
    QUALITY_VERSION,
    TARGET_TURNS,
    _attempt_offset,
    _attempts_end_in_provider_overload,
    _candidate_classification,
    _generation_error_retry_allowed,
    _load_progress,
    _new_progress,
    _retry_filter_matches,
    _technical_retry_allowed,
    _unattempted_filter_matches,
    _update_quality_summary,
    planned_slots,
)
from rollout.configuration import load_rollout_config
from pipeline.scenarios import load_scenario_records
from scripts.requeue_gpt50_short_rollouts import remove_manifest_reference


class LongRolloutBatchTest(unittest.TestCase):
    def test_formal_plan_has_one_natural_horizon_claude_slot_per_scenario(self):
        config = load_rollout_config("configs/formal_rollout_pool.json")
        records = load_scenario_records("data/gpt50/experiment/scenario/scenarios")
        slots = planned_slots(records, config)
        self.assertEqual(config["pilot_limits"]["rollout_turns"], TARGET_TURNS)
        self.assertEqual(len(slots), len(records))
        self.assertEqual(len({item["slot_id"] for item in slots}), len(records))
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

    def test_resume_expands_slot_plan_when_missing_scenario_is_added(self):
        config_path = "configs/formal_rollout_pool.json"
        config = load_rollout_config(config_path)
        original_slots = [{"slot_id": "scenario-1::policy"}]
        expanded_slots = original_slots + [{"slot_id": "scenario-2::policy"}]
        progress = _new_progress(
            config_path, "build/example", original_slots, config
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            path.write_text(json.dumps(progress), encoding="utf-8")
            loaded = _load_progress(
                path, config_path, expanded_slots, config
            )
            persisted = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["expected_slot_count"], 2)
        self.assertEqual(persisted["expected_slot_count"], 2)
        self.assertEqual(
            persisted["slot_plan_history"][-1]["reason"],
            "newly_completed_scenario_added_to_batch",
        )

    def test_explicit_route_migration_preserves_completed_slots(self):
        config_path = "configs/formal_rollout_pool.json"
        config = load_rollout_config(config_path)
        slots = [{"slot_id": "scenario::policy"}]
        progress = _new_progress(
            config_path,
            "build/example",
            slots,
            config,
            retain_all_candidates=True,
        )
        progress["completed_slots"] = {
            "scenario::policy": {"trajectory_id": "kept"}
        }
        progress["quality_fingerprint"] = "old-quality-fingerprint"
        progress["config_sha256"] = "old-config-sha"
        migrated = dict(config)
        migrated["model_routes_provenance"] = {
            **(config.get("model_routes_provenance") or {}),
            "sha256": "new-route-sha",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            path.write_text(json.dumps(progress), encoding="utf-8")
            loaded = _load_progress(
                path,
                config_path,
                slots,
                migrated,
                retain_all_candidates=True,
                allow_config_migration=True,
                allow_route_migration=True,
                allow_quality_migration=True,
            )
            persisted = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            loaded["completed_slots"]["scenario::policy"]["trajectory_id"],
            "kept",
        )
        self.assertEqual(loaded["model_routes_sha256"], "new-route-sha")
        self.assertEqual(
            persisted["model_route_history"][-1]["reason"],
            "explicit_endpoint_protocol_migration",
        )
        self.assertEqual(
            persisted["config_migration_history"][-1]["reason"],
            "explicit_rollout_contract_migration",
        )
        self.assertEqual(
            persisted["quality_migration_history"][-1]["reason"],
            "explicit_runtime_bugfix_migration",
        )

    def test_retry_filter_uses_only_the_latest_failed_attempt(self):
        progress = {
            "attempts": [
                {
                    "slot_id": "fractional",
                    "status": "generation_error",
                    "error_type": "KeyError",
                },
                {
                    "slot_id": "fractional",
                    "status": "generation_error",
                    "error_type": "TimeoutError",
                },
                {
                    "slot_id": "still_fractional",
                    "status": "generation_error",
                    "error_type": "KeyError",
                },
            ]
        }
        self.assertTrue(_retry_filter_matches(progress, "new", None))
        self.assertFalse(_retry_filter_matches(progress, "new", ["KeyError"]))
        self.assertFalse(
            _retry_filter_matches(progress, "fractional", ["KeyError"])
        )
        self.assertTrue(
            _retry_filter_matches(progress, "still_fractional", ["KeyError"])
        )
        self.assertTrue(_unattempted_filter_matches(progress, "new"))
        self.assertFalse(
            _unattempted_filter_matches(progress, "fractional")
        )

    def test_generation_error_retry_is_one_time_and_never_retries_rejections(self):
        progress = {
            "attempts": [
                {"slot_id": "eligible", "status": "generation_error"},
                {"slot_id": "accepted", "status": "accepted"},
                {"slot_id": "rejected", "status": "machine_rejected"},
                {
                    "slot_id": "used",
                    "status": "generation_error",
                    "technical_retry": True,
                },
            ]
        }
        self.assertTrue(
            _generation_error_retry_allowed(progress, "eligible")
        )
        self.assertFalse(
            _generation_error_retry_allowed(progress, "accepted")
        )
        self.assertFalse(
            _generation_error_retry_allowed(progress, "rejected")
        )
        self.assertFalse(
            _generation_error_retry_allowed(progress, "used")
        )
        self.assertFalse(
            _generation_error_retry_allowed(progress, "never_attempted")
        )

    def test_explicit_error_filter_allows_audited_second_technical_retry(self):
        progress = {
            "attempts": [
                {
                    "slot_id": "template_failure",
                    "status": "generation_error",
                    "error_type": "ValueError",
                    "technical_retry": True,
                },
                {
                    "slot_id": "quality_rejection",
                    "status": "machine_rejected",
                },
            ]
        }
        self.assertTrue(_technical_retry_allowed(
            progress, "template_failure", error_types=["ValueError"]
        ))
        self.assertFalse(_technical_retry_allowed(
            progress, "template_failure", error_types=["TimeoutError"]
        ))
        self.assertFalse(_technical_retry_allowed(
            progress, "quality_rejection", error_types=["ValueError"]
        ))

    def test_provider_overload_circuit_break_classification(self):
        self.assertTrue(_attempts_end_in_provider_overload([{
            "status": "generation_error",
            "error": "HTTP 429: overloaded_error",
        }]))
        self.assertTrue(_attempts_end_in_provider_overload([{
            "status": "generation_error",
            "error": "Provider is temporarily overloaded",
        }]))
        self.assertFalse(_attempts_end_in_provider_overload([{
            "status": "generation_error",
            "error": "response schema invalid",
        }]))
        self.assertFalse(_attempts_end_in_provider_overload([{
            "status": "accepted",
            "error": "HTTP 429 from an earlier request",
        }]))

    def test_requeue_removes_archived_trajectory_from_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps({
                "trajectory_count": 1,
                "scenario_ids": ["S1"],
                "policy_ids": ["p1"],
                "trajectory_ids": ["t1"],
                "config": {"generation_status": "completed"},
            }), encoding="utf-8")
            remove_manifest_reference(path.parent, "t1")
            value = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(value["trajectory_count"], 0)
            self.assertEqual(value["trajectory_ids"], [])
            self.assertEqual(value["scenario_ids"], [])
            self.assertEqual(value["policy_ids"], [])
            self.assertEqual(
                value["config"]["generation_status"], "in_progress"
            )




if __name__ == "__main__":
    unittest.main()
