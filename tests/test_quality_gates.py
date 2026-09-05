import json
from pathlib import Path
import unittest
import tempfile

from evaluation.quality_gates import (
    audit_all_gates,
    audit_environment_gate,
    audit_scenario_gate,
    load_rollouts,
)


class FourQualityGatesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = json.loads(
            (Path("configs/scenarios/scenario_002/scenario_002.json")).read_text(encoding="utf-8")
        )

    def test_pending_scenario_review_blocks_gate_one(self):
        result = audit_scenario_gate(self.scenario)
        self.assertEqual(result["status"], "pending")
        self.assertFalse(result["passed"])
        self.assertEqual(result["checks"]["human_approval"]["status"], "pending")

    def test_missing_evidence_cannot_make_four_gate_report_ready(self):
        result = audit_all_gates([self.scenario], [], [])
        self.assertFalse(result["research_ready"])
        self.assertEqual(result["gates"]["gate_2_environment_validity"]["status"], "pending")
        self.assertEqual(result["eligible_trajectory_count"], 0)

    def test_environment_gate_rejects_bare_pass_and_accepts_complete_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bare = {"record": {"passed": True}}
            for name in ("state_transition_agreement.json", "trajectory_plausibility.json", "history_intervention.json", "paraphrase_robustness.json", "local_counterfactual.json", "backbone_sensitivity.json"):
                (root / name).write_text(json.dumps(bare), encoding="utf-8")
            self.assertFalse(audit_environment_gate([self.scenario], root)["passed"])
            values = {
                "state_transition_agreement.json": {"record": {"human_attestation": True, "reviewers": ["h1", "h2", "h3"], "reviewed_at_utc": "2026-09-06T02:00:00Z", "annotator_count": 3, "transition_count": 30, "agreement": 0.7}},
                "trajectory_plausibility.json": {"record": {"human_attestation": True, "reviewers": ["h1", "h2", "h3"], "reviewed_at_utc": "2026-09-06T02:00:00Z", "annotator_count": 3, "trajectory_count": 15, "scores": {"persona_consistency": 3.5, "history_sensitivity": 3.5, "state_continuity": 3.5, "response_state_consistency": 3.5, "overall": 4.0}}},
                "history_intervention.json": {"record": {"passed": True, "human_attestation": True, "reviewers": ["h1"], "reviewed_at_utc": "2026-09-06T02:00:00Z", "matched_checkpoint_count": 10, "same_persona_state_action": True}},
                "paraphrase_robustness.json": {"record": {"passed": True, "human_attestation": True, "reviewers": ["h1"], "reviewed_at_utc": "2026-09-06T02:00:00Z", "pair_count": 10, "direction_consistency": 0.8}},
                "local_counterfactual.json": {"record": {"passed": True, "human_attestation": True, "reviewers": ["h1"], "reviewed_at_utc": "2026-09-06T02:00:00Z", "checkpoint_count": 10, "same_checkpoint_verified": True}},
                "backbone_sensitivity.json": {"format": "socialflux_backbone_sensitivity_v1", "backbones": [{"model_family": "qwen"}, {"model_family": "glm"}], "record": {"passed": True, "matched_checkpoint_count": 10}},
            }
            for name, value in values.items():
                (root / name).write_text(json.dumps(value), encoding="utf-8")
            self.assertTrue(audit_environment_gate([self.scenario], root)["passed"])

    def test_selected_pool_requires_bound_passing_manifest(self):
        trajectory = {
            "trajectory_id": "traj_1",
            "scenario_id": "IA_PIPE_002",
            "turns": [{"turn_id": 1}],
        }
        with tempfile.TemporaryDirectory() as directory:
            scenario_dir = Path(directory) / "scenario_002"
            scenario_dir.mkdir()
            (scenario_dir / "traj_1.json").write_text(
                json.dumps(trajectory), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "missing"):
                load_rollouts(directory, require_selected_manifest=True)
            manifest = {
                "format": "socialflux_rollout_manifest_v2",
                "trajectory_ids": ["traj_1"],
                "config": {
                    "pool_stage": "formal_selected",
                    "quality_audits": [{"trajectory_id": "traj_1", "passed": True}],
                },
            }
            (scenario_dir / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            self.assertEqual(
                load_rollouts(directory, require_selected_manifest=True),
                [trajectory],
            )
            (scenario_dir / "orphan.json").write_text(
                json.dumps({**trajectory, "trajectory_id": "orphan"}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "all-passing"):
                load_rollouts(directory, require_selected_manifest=True)
            self.assertEqual(load_rollouts(directory), [trajectory])


if __name__ == "__main__":
    unittest.main()
