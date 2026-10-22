import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.prepare_batch_gate2 import (
    machine_evidence_ready,
    non_video_machine_evidence_ready,
    stable_sample,
)
from scripts.run_environment_interventions import (
    _appraisal_signature,
    _latest_successful_records,
    _load_progress,
    select_intervention_checkpoint,
    write_evidence,
)


class BatchGate2Test(unittest.TestCase):
    def test_stable_samples_obey_gate2_bounds(self):
        items = [{"review_id": f"item-{index}"} for index in range(100)]
        first = stable_sample(items, 40)
        second = stable_sample(list(reversed(items)), 40)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 40)
        self.assertEqual(len(stable_sample(items, 20)), 20)

    def test_intervention_resume_retains_errors_and_uses_latest_success(self):
        with TemporaryDirectory() as directory:
            progress_path = Path(directory) / "progress.json"
            failed = {
                "scenario_id": "GPT50_001",
                "attempt": 1,
                "error": {"type": "TimeoutError", "message": "timed out"},
            }
            first_success = {
                "scenario_id": "GPT50_001",
                "attempt": 2,
                "e3": {}, "e4": {}, "e5": {}, "e7": {},
            }
            latest_success = {
                "scenario_id": "GPT50_001",
                "attempt": 3,
                "e3": {"version": 3}, "e4": {}, "e5": {}, "e7": {},
            }
            progress_path.write_text(
                json.dumps({"records": [failed, first_success, latest_success]}),
                encoding="utf-8",
            )
            loaded = _load_progress(progress_path, resume=True)
            self.assertEqual(loaded, [failed, first_success, latest_success])
            self.assertEqual(
                _latest_successful_records(loaded),
                [latest_success],
            )

    def test_intervention_checkpoint_uses_fixed_horizon_not_terminal_turn(self):
        trajectory = {"turns": [{"turn_id": f"t{index}"} for index in range(1, 11)]}
        self.assertEqual(
            select_intervention_checkpoint(trajectory)["turn_id"], "t7"
        )

    def test_appraisal_signature_tracks_structural_intervention_effect(self):
        output = {"appraisal": {
            "social_act": "request",
            "event_features": {"pressure": 1},
            "state_impacts": [{
                "variable": "emotion.anxiety", "direction": "increase"
            }],
            "dynamics_impacts": [],
        }}
        self.assertEqual(
            _appraisal_signature(output)["impacts"],
            [("state_impacts", "emotion.anxiety", "increase")],
        )

    def test_e4_aggregate_excludes_zero_zero_dimensions(self):
        def output(delta):
            return {
                "numeric_state_delta": {"emotion": delta},
                "numeric_dynamics_delta": {},
            }
        record = {
            "scenario_id": "s1",
            "source_trajectory_id": "t1",
            "checkpoint_turn_id": "t7",
            "e4": {
                "direction_consistency": 0.0,
                "all_dimension_direction_agreement": 0.5,
                "original_output": output({"a": 1, "b": 0}),
                "paraphrase_output": output({"a": 0, "b": 0}),
                "comparison": {
                    "state_direction_agreement": 0.5,
                    "dynamics_direction_agreement": 1.0,
                    "mean_ordinal_delta_distance": 0.5,
                    "legacy_balanced_group_direction_consistency": 0.75,
                },
                "equivalence_precheck": {"passed": True},
            },
        }
        with TemporaryDirectory() as directory:
            payload = write_evidence(Path(directory), [record], {})[
                "paraphrase_robustness.json"
            ]["record"]
        self.assertEqual(payload["all_dimension_direction_agreement"], 0.5)
        self.assertEqual(payload["active_union_direction_agreement"], 0.0)
        self.assertEqual(payload["zero_zero_dimension_fraction"], 0.5)

    def test_versioned_resume_never_falls_back_to_legacy_success(self):
        records = [{
            "scenario_id": "s1", "e3": {}, "e4": {}, "e5": {}, "e7": {}
        }]
        self.assertEqual(
            _latest_successful_records(records, "gate2_interventions_v2"), []
        )

    def test_machine_readiness_separates_text_experiments_from_video(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for filename, field in (
                ("history_intervention.json", "matched_checkpoint_count"),
                ("paraphrase_robustness.json", "pair_count"),
                ("local_counterfactual.json", "checkpoint_count"),
                ("persona_intervention.json", "matched_checkpoint_count"),
            ):
                (root / filename).write_text(
                    json.dumps({"record": {
                        field: 10,
                        "machine_screen_passed": True,
                    }}),
                    encoding="utf-8",
                )
            (root / "backbone_sensitivity.json").write_text(
                json.dumps({
                    "record": {"passed": True, "successful_matched_checkpoint_count": 10},
                    "records": [
                        {"replay_errors": []}
                        for _ in range(10)
                    ]
                }),
                encoding="utf-8",
            )
            ready, checks = machine_evidence_ready(root)
            self.assertFalse(ready)
            self.assertFalse(non_video_machine_evidence_ready(checks))
            (root / "timescale_validity.json").write_text(
                json.dumps({
                    "record": {
                        "candidate_variable_count": 10,
                        "timescale_families": {
                            "fast": 3, "medium": 3, "slow": 3,
                            "context_dependent": 1,
                        },
                    }
                }),
                encoding="utf-8",
            )
            ready, checks = machine_evidence_ready(root)
            self.assertFalse(ready)
            self.assertTrue(non_video_machine_evidence_ready(checks))
            (root / "video_state_consistency.json").write_text(
                json.dumps({
                    "record": {
                        "matched_node_count": 40,
                        "generated_video_count": 40,
                        "request_safety_passed": True,
                    }
                }),
                encoding="utf-8",
            )
            ready, checks = machine_evidence_ready(root)
            self.assertTrue(ready)
            self.assertEqual(
                checks["backbone_sensitivity.json"]["replay_error_count"],
                0,
            )
            (root / "local_counterfactual.json").write_text(
                json.dumps({"record": {
                    "checkpoint_count": 9,
                    "machine_screen_passed": True,
                }}),
                encoding="utf-8",
            )
            self.assertFalse(machine_evidence_ready(root)[0])
            self.assertFalse(
                non_video_machine_evidence_ready(machine_evidence_ready(root)[1])
            )

    def test_machine_readiness_rejects_evidence_from_another_cohort(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            expected = [{"scenario_id": "s1", "trajectory_id": "t1"}]
            for filename, field in (
                ("history_intervention.json", "matched_checkpoint_count"),
                ("paraphrase_robustness.json", "pair_count"),
                ("local_counterfactual.json", "checkpoint_count"),
                ("persona_intervention.json", "matched_checkpoint_count"),
            ):
                (root / filename).write_text(json.dumps({
                    "provenance": {
                        "experiment_version": "gate2_interventions_v2",
                        "input_cohort": {
                            "scenario_ids": ["other"],
                            "trajectory_ids": ["other-trajectory"],
                        },
                    },
                    "record": {field: 10, "machine_screen_passed": True},
                    "records": [{
                        "scenario_id": "other",
                        "source_trajectory_id": "other-trajectory",
                    }],
                }), encoding="utf-8")
            ready, checks = machine_evidence_ready(root, expected)
            self.assertFalse(ready)
            self.assertFalse(
                checks["history_intervention.json"]["cohort_matches"]
            )


if __name__ == "__main__":
    unittest.main()
